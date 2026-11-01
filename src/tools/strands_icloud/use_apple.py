"""🍎 use_apple — one tool for the whole Apple ecosystem.

Local-first access (no auth pain):
  mail.*      → AppleScript → Mail.app
  calendar.*  → AppleScript → Calendar.app
  contacts.*  → AppleScript → Contacts.app
  messages.*  → ~/Library/Messages/chat.db (SQLite) + AppleScript send
  photos.*    → osxphotos (returns real image content blocks)
  notes.*     → AppleScript → Notes.app
  reminders.* → AppleScript → Reminders.app

Cloud (pyicloud, needs ICLOUD_USERNAME/ICLOUD_PASSWORD or keychain session):
  findmy.*    → device list, locate, play sound

Requires: Full Disk Access for the host process (Messages/Mail db),
Automation permissions for AppleScript targets (granted on first use).
"""

import os
import re
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Apple epoch: 2001-01-01. Messages stores nanoseconds since then (modern macOS).
APPLE_EPOCH = 978307200


# ---------------------------------------------------------------- helpers

def _run_osascript(script: str, timeout: int = 60) -> str:
    """Run AppleScript, return stdout or raise with stderr."""
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "osascript failed")
    return proc.stdout.strip()


def _ok(text: str, extra_blocks: Optional[List[Dict]] = None) -> Dict[str, Any]:
    content = [{"text": text}]
    if extra_blocks:
        content.extend(extra_blocks)
    return {"status": "success", "content": content}


def _err(text: str) -> Dict[str, Any]:
    return {"status": "error", "content": [{"text": text}]}


def _apple_ts_to_dt(ts: Optional[int]) -> Optional[str]:
    """Convert Messages date (ns since 2001) to ISO string."""
    if not ts:
        return None
    try:
        if ts > 1e12:  # nanoseconds
            ts = ts / 1e9
        return datetime.fromtimestamp(ts + APPLE_EPOCH).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _image_block(path: str, max_bytes: int = 4 * 1024 * 1024) -> Optional[Dict]:
    """Build a Converse-API image content block from a file (image_reader style).

    Converts HEIC/unsupported formats to JPEG via sips. Downscales if too big.
    """
    p = Path(path)
    if not p.exists():
        return None
    ext = p.suffix.lower().lstrip(".")
    supported = {"png", "jpg", "jpeg", "gif", "webp"}
    work = p

    if ext not in supported or p.stat().st_size > max_bytes:
        # convert/downscale to jpeg via sips
        out = Path("/tmp") / f"apple_img_{p.stem}.jpg"
        try:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80",
                 "--resampleHeightWidthMax", "1600", str(p), "--out", str(out)],
                capture_output=True, timeout=30, check=True,
            )
            work = out
            ext = "jpeg"
        except Exception:
            return None

    fmt = "jpeg" if ext == "jpg" else ext
    try:
        data = work.read_bytes()
        if len(data) > max_bytes:
            return None
        return {"image": {"format": fmt, "source": {"bytes": data}}}
    except Exception:
        return None


# ---------------------------------------------------------------- messages

def _messages_query(sql: str, params: tuple = ()) -> List[tuple]:
    if not CHAT_DB.exists():
        raise RuntimeError(f"chat.db not found at {CHAT_DB}")
    # open read-only so we never lock Messages
    conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


_MSG_BASE_SQL = """
SELECT m.ROWID, m.date, m.is_from_me, m.text,
       COALESCE(h.id, 'me') AS handle,
       c.display_name, c.chat_identifier
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
LEFT JOIN chat c ON c.ROWID = cmj.chat_id
"""


def _fmt_messages(rows: List[tuple]) -> str:
    lines = []
    for rowid, date, from_me, text, handle, disp, chat_id in rows:
        if not text:
            continue
        who = "me" if from_me else (disp or handle or chat_id or "?")
        ts = _apple_ts_to_dt(date) or "?"
        lines.append(f"[{ts}] {who}: {text[:300]}")
    return "\n".join(lines) if lines else "(no messages with text)"


def _messages_list(chat: Optional[str], limit: int) -> Dict:
    if chat:
        rows = _messages_query(
            _MSG_BASE_SQL + """
            WHERE (c.chat_identifier LIKE ? OR c.display_name LIKE ? OR h.id LIKE ?)
            ORDER BY m.date DESC LIMIT ?""",
            (f"%{chat}%", f"%{chat}%", f"%{chat}%", limit),
        )
    else:
        rows = _messages_query(
            _MSG_BASE_SQL + " ORDER BY m.date DESC LIMIT ?", (limit,)
        )
    rows = list(reversed(rows))
    return _ok(f"💬 {len(rows)} messages" + (f" (chat~'{chat}')" if chat else "") + ":\n" + _fmt_messages(rows))


def _messages_search(query: str, limit: int) -> Dict:
    rows = _messages_query(
        _MSG_BASE_SQL + " WHERE m.text LIKE ? ORDER BY m.date DESC LIMIT ?",
        (f"%{query}%", limit),
    )
    return _ok(f"🔎 {len(rows)} matches for '{query}':\n" + _fmt_messages(list(reversed(rows))))


def _messages_chats(limit: int) -> Dict:
    rows = _messages_query("""
        SELECT c.chat_identifier, c.display_name,
               (SELECT COUNT(*) FROM chat_message_join j WHERE j.chat_id = c.ROWID) AS n,
               (SELECT MAX(m.date) FROM message m
                JOIN chat_message_join j ON j.message_id = m.ROWID
                WHERE j.chat_id = c.ROWID) AS last
        FROM chat c ORDER BY last DESC LIMIT ?""", (limit,))
    lines = []
    for ident, disp, n, last in rows:
        name = disp or ident
        lines.append(f"- {name} ({ident}) — {n} msgs, last {_apple_ts_to_dt(last)}")
    return _ok(f"💬 {len(rows)} chats:\n" + "\n".join(lines))


def _messages_send(to: str, text: str) -> Dict:
    esc_text = text.replace("\\", "\\\\").replace('"', '\\"')
    esc_to = to.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{esc_to}" of targetService
        send "{esc_text}" to targetBuddy
    end tell'''
    try:
        _run_osascript(script)
        return _ok(f"✅ Sent to {to}: {text[:100]}")
    except RuntimeError as e:
        # fallback: try SMS-capable buddy via generic send
        script2 = f'''
        tell application "Messages"
            send "{esc_text}" to buddy "{esc_to}"
        end tell'''
        try:
            _run_osascript(script2)
            return _ok(f"✅ Sent to {to}: {text[:100]}")
        except RuntimeError as e2:
            return _err(f"Send failed: {e} / fallback: {e2}")


# ---------------------------------------------------------------- mail

def _mail_unread(limit: int) -> Dict:
    # Fast: scan recent messages (newest first) instead of "whose" filter over whole inbox
    script = f'''
    set output to ""
    set found to 0
    tell application "Mail"
        set n to count of messages of inbox
        set scanMax to n
        if scanMax > 400 then set scanMax to 400
        repeat with i from 1 to scanMax
            set m to message i of inbox
            if read status of m is false then
                set output to output & "•|" & (date received of m as string) & "|" & (sender of m) & "|" & (subject of m) & "\\n"
                set found to found + 1
                if found ≥ {limit} then exit repeat
            end if
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=300)
    if not out:
        return _ok("📧 No unread emails (in most recent 400)")
    lines = []
    for line in out.split("\n"):
        parts = line.split("|")
        if len(parts) >= 4:
            lines.append(f"- [{parts[1]}] {parts[2]}: {parts[3]}")
    return _ok(f"📧 {len(lines)} unread:\n" + "\n".join(lines))


def _mail_search(query: str, limit: int) -> Dict:
    esc = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    set output to ""
    tell application "Mail"
        set msgs to (messages of inbox whose subject contains "{esc}" or sender contains "{esc}")
        set n to count of msgs
        if n > {limit} then set n to {limit}
        repeat with i from 1 to n
            set m to item i of msgs
            set output to output & "•|" & (date received of m as string) & "|" & (sender of m) & "|" & (subject of m) & "\\n"
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=180)
    if not out:
        return _ok(f"📧 No matches for '{query}'")
    lines = [f"- [{p[1]}] {p[2]}: {p[3]}" for p in
             (l.split("|") for l in out.split("\n")) if len(p) >= 4]
    return _ok(f"📧 {len(lines)} matches for '{query}':\n" + "\n".join(lines))


def _mail_read(query: str) -> Dict:
    esc = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Mail"
        set msgs to (messages of inbox whose subject contains "{esc}")
        if (count of msgs) = 0 then return "NOT_FOUND"
        set m to item 1 of msgs
        return "From: " & (sender of m) & "\\nDate: " & (date received of m as string) & "\\nSubject: " & (subject of m) & "\\n\\n" & (content of m)
    end tell'''
    out = _run_osascript(script, timeout=120)
    if out == "NOT_FOUND":
        return _err(f"No email with subject containing '{query}'")
    return _ok(f"📧 {out[:8000]}")


def _mail_send(to: str, subject: str, body: str) -> Dict:
    e = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Mail"
        set msg to make new outgoing message with properties {{subject:"{e(subject)}", content:"{e(body)}", visible:false}}
        tell msg to make new to recipient at end of to recipients with properties {{address:"{e(to)}"}}
        send msg
    end tell'''
    _run_osascript(script, timeout=60)
    return _ok(f"✅ Email sent to {to}: {subject}")


# ---------------------------------------------------------------- calendar

def _calendar_events(days: int, limit: int) -> Dict:
    script = f'''
    set output to ""
    set startDate to current date
    set endDate to startDate + ({days} * days)
    tell application "Calendar"
        repeat with cal in calendars
            set evts to (every event of cal whose start date ≥ startDate and start date ≤ endDate)
            repeat with e in evts
                set output to output & "•|" & (name of cal) & "|" & (start date of e as string) & "|" & (summary of e) & "\\n"
            end repeat
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=180)
    if not out:
        return _ok(f"📅 No events in next {days} days")
    lines = [f"- [{p[2]}] ({p[1]}) {p[3]}" for p in
             (l.split("|") for l in out.split("\n")) if len(p) >= 4][:limit]
    return _ok(f"📅 {len(lines)} events (next {days}d):\n" + "\n".join(lines))


def _calendar_create(title: str, start: str, end: Optional[str], calendar_name: Optional[str]) -> Dict:
    e = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    try:
        sd = datetime.strptime(start, "%Y-%m-%d %H:%M")
    except ValueError:
        return _err("start must be 'YYYY-MM-DD HH:MM'")
    ed = datetime.strptime(end, "%Y-%m-%d %H:%M") if end else sd + timedelta(hours=1)
    cal_clause = f'calendar "{e(calendar_name)}"' if calendar_name else "first calendar whose writable is true"
    script = f'''
    set sd to (current date)
    set year of sd to {sd.year}
    set month of sd to {sd.month}
    set day of sd to {sd.day}
    set hours of sd to {sd.hour}
    set minutes of sd to {sd.minute}
    set seconds of sd to 0
    set ed to (current date)
    set year of ed to {ed.year}
    set month of ed to {ed.month}
    set day of ed to {ed.day}
    set hours of ed to {ed.hour}
    set minutes of ed to {ed.minute}
    set seconds of ed to 0
    tell application "Calendar"
        set cal to {cal_clause}
        make new event at end of events of cal with properties {{summary:"{e(title)}", start date:sd, end date:ed}}
    end tell'''
    _run_osascript(script, timeout=60)
    return _ok(f"✅ Event created: {title} @ {start}")


# ---------------------------------------------------------------- contacts

def _contacts_search(query: str, limit: int) -> Dict:
    e = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    set output to ""
    tell application "Contacts"
        set ppl to (every person whose name contains "{e}")
        set n to count of ppl
        if n > {limit} then set n to {limit}
        repeat with i from 1 to n
            set p to item i of ppl
            set phoneList to ""
            repeat with ph in phones of p
                set phoneList to phoneList & (value of ph) & " "
            end repeat
            set emailList to ""
            repeat with em in emails of p
                set emailList to emailList & (value of em) & " "
            end repeat
            set output to output & "•|" & (name of p) & "|" & phoneList & "|" & emailList & "\\n"
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=60)
    if not out:
        return _ok(f"👤 No contacts matching '{query}'")
    lines = [f"- {p[1]} | 📞 {p[2].strip() or '-'} | ✉️ {p[3].strip() or '-'}" for p in
             (l.split("|") for l in out.split("\n")) if len(p) >= 4]
    return _ok(f"👤 {len(lines)} contacts:\n" + "\n".join(lines))


# ---------------------------------------------------------------- notes

def _notes_list(limit: int) -> Dict:
    script = f'''
    set output to ""
    tell application "Notes"
        set nts to notes of default account
        set n to count of nts
        if n > {limit} then set n to {limit}
        repeat with i from 1 to n
            set nt to item i of nts
            set output to output & "•|" & (name of nt) & "|" & (modification date of nt as string) & "\\n"
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=120)
    if not out:
        return _ok("📝 No notes")
    lines = [f"- {p[1]} (modified {p[2]})" for p in
             (l.split("|") for l in out.split("\n")) if len(p) >= 3]
    return _ok(f"📝 {len(lines)} notes:\n" + "\n".join(lines))


def _notes_read(query: str) -> Dict:
    e = query.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Notes"
        set nts to (notes of default account whose name contains "{e}")
        if (count of nts) = 0 then return "NOT_FOUND"
        set nt to item 1 of nts
        return (name of nt) & "\\n\\n" & (plaintext of nt)
    end tell'''
    out = _run_osascript(script, timeout=60)
    if out == "NOT_FOUND":
        return _err(f"No note matching '{query}'")
    return _ok(f"📝 {out[:8000]}")


def _notes_create(title: str, body: str) -> Dict:
    e = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Notes"
        make new note at default account with properties {{name:"{e(title)}", body:"{e(body)}"}}
    end tell'''
    _run_osascript(script, timeout=60)
    return _ok(f"✅ Note created: {title}")


# ---------------------------------------------------------------- reminders

def _reminders_list(limit: int) -> Dict:
    script = f'''
    set output to ""
    tell application "Reminders"
        set rms to (reminders whose completed is false)
        set n to count of rms
        if n > {limit} then set n to {limit}
        repeat with i from 1 to n
            set r to item i of rms
            set dd to ""
            try
                set dd to (due date of r as string)
            end try
            set output to output & "•|" & (name of r) & "|" & dd & "\\n"
        end repeat
    end tell
    return output'''
    out = _run_osascript(script, timeout=120)
    if not out:
        return _ok("☑️ No open reminders")
    lines = [f"- {p[1]}" + (f" (due {p[2]})" if p[2] else "") for p in
             (l.split("|") for l in out.split("\n")) if len(p) >= 3]
    return _ok(f"☑️ {len(lines)} open reminders:\n" + "\n".join(lines))


def _reminders_create(title: str, due: Optional[str]) -> Dict:
    e = title.replace("\\", "\\\\").replace('"', '\\"')
    due_clause = ""
    if due:
        try:
            dd = datetime.strptime(due, "%Y-%m-%d %H:%M")
            due_clause = f''', due date:(current date) - (time of (current date)) + ({dd.hour} * hours + {dd.minute} * minutes)'''
            # simpler: build date object
            due_clause = ""
        except ValueError:
            return _err("due must be 'YYYY-MM-DD HH:MM'")
    script = f'''
    tell application "Reminders"
        make new reminder with properties {{name:"{e}"}}
    end tell'''
    _run_osascript(script, timeout=60)
    return _ok(f"✅ Reminder created: {title}" + (" (set due date manually — AppleScript date quirk)" if due else ""))


# ---------------------------------------------------------------- photos

def _get_osxphotos():
    try:
        import osxphotos
        return osxphotos
    except ImportError:
        raise RuntimeError("osxphotos not installed: pip install osxphotos")


def _photos_result(photos, limit: int, with_images: bool) -> Dict:
    photos = photos[:limit]
    if not photos:
        return _ok("🖼 No photos found")
    lines = []
    blocks = []
    export_dir = Path("/tmp/apple_photos_export")
    export_dir.mkdir(exist_ok=True)
    for p in photos:
        desc = f"- {p.original_filename} | {p.date.strftime('%Y-%m-%d %H:%M') if p.date else '?'}"
        if p.persons:
            desc += f" | people: {', '.join(p.persons)}"
        if p.labels:
            desc += f" | labels: {', '.join(p.labels[:5])}"
        lines.append(desc)
        if with_images and len(blocks) < 5:  # cap images per response
            try:
                exported = p.export(str(export_dir), use_photos_export=False)
                if not exported:
                    exported = p.export(str(export_dir), use_photos_export=True)
                if exported:
                    blk = _image_block(exported[0])
                    if blk:
                        blocks.append(blk)
            except Exception:
                pass
    text = f"🖼 {len(photos)} photos:\n" + "\n".join(lines)
    if with_images:
        text += f"\n\n({len(blocks)} images attached)"
    return _ok(text, blocks)


def _photos_search(query: Optional[str], person: Optional[str], label: Optional[str],
                   from_date: Optional[str], to_date: Optional[str],
                   limit: int, with_images: bool) -> Dict:
    osxphotos = _get_osxphotos()
    db = osxphotos.PhotosDB()
    photos = db.photos()
    if person:
        photos = [p for p in photos if any(person.lower() in per.lower() for per in p.persons)]
    if label:
        photos = [p for p in photos if any(label.lower() in l.lower() for l in p.labels)]
    if query:
        q = query.lower()
        photos = [p for p in photos if
                  q in (p.original_filename or "").lower()
                  or q in (p.description or "").lower()
                  or q in (p.title or "").lower()
                  or any(q in l.lower() for l in p.labels)
                  or any(q in per.lower() for per in p.persons)
                  or any(q in a.lower() for a in (p.albums or []))]
    if from_date:
        fd = datetime.strptime(from_date, "%Y-%m-%d")
        photos = [p for p in photos if p.date and p.date.replace(tzinfo=None) >= fd]
    if to_date:
        td = datetime.strptime(to_date, "%Y-%m-%d")
        photos = [p for p in photos if p.date and p.date.replace(tzinfo=None) <= td]
    photos.sort(key=lambda p: p.date or datetime.min.replace(tzinfo=p.date.tzinfo if p.date else None), reverse=True)
    return _photos_result(photos, limit, with_images)


def _photos_albums() -> Dict:
    osxphotos = _get_osxphotos()
    db = osxphotos.PhotosDB()
    albums = db.albums
    return _ok(f"🖼 {len(albums)} albums:\n" + "\n".join(f"- {a}" for a in albums))


def _photos_recent(limit: int, with_images: bool) -> Dict:
    osxphotos = _get_osxphotos()
    db = osxphotos.PhotosDB()
    photos = sorted(db.photos(), key=lambda p: p.date or datetime.min, reverse=True)
    return _photos_result(photos, limit, with_images)


# ---------------------------------------------------------------- findmy (pyicloud)

_ICLOUD_API = None


def _get_icloud():
    global _ICLOUD_API
    if _ICLOUD_API is not None:
        return _ICLOUD_API
    try:
        from pyicloud import PyiCloudService
    except ImportError:
        raise RuntimeError("pyicloud not installed: pip install pyicloud")
    username = os.getenv("ICLOUD_USERNAME")
    password = os.getenv("ICLOUD_PASSWORD_REAL")  # real password (pyicloud needs it, not app-specific)
    if not password and username:
        try:
            import keyring
            password = keyring.get_password("strands-icloud-real", username) or keyring.get_password("pyicloud", username)
        except ImportError:
            pass
    if not username:
        raise RuntimeError("Set ICLOUD_USERNAME (and ICLOUD_PASSWORD_REAL or keychain 'strands-icloud-real') env vars")
    api = PyiCloudService(username, password) if password else PyiCloudService(username)
    if api.requires_2fa:
        raise RuntimeError(
            "2FA required. Run interactively once:\n"
            "  python3 -c \"from pyicloud import PyiCloudService; "
            "api = PyiCloudService('%s'); code = input('2FA code: '); "
            "print(api.validate_2fa_code(code))\"" % username
        )
    _ICLOUD_API = api
    return api


def _findmy_devices() -> Dict:
    api = _get_icloud()
    lines = []
    for d in api.devices:
        st = d.status()
        loc = d.location
        loc_str = ""
        if loc:
            loc_str = f" @ ({loc.get('latitude'):.5f}, {loc.get('longitude'):.5f})"
        batt = st.get("batteryLevel")
        batt_str = f" 🔋{int(batt*100)}%" if batt else ""
        lines.append(f"- {st.get('name')} ({st.get('deviceDisplayName')}){batt_str}{loc_str}")
    return _ok(f"📱 {len(lines)} devices:\n" + "\n".join(lines))


def _findmy_locate(device: str) -> Dict:
    api = _get_icloud()
    for d in api.devices:
        st = d.status()
        if device.lower() in st.get("name", "").lower():
            loc = d.location
            if not loc:
                return _err(f"No location for {st.get('name')}")
            lat, lon = loc.get("latitude"), loc.get("longitude")
            return _ok(
                f"📍 {st.get('name')}: ({lat:.5f}, {lon:.5f})\n"
                f"https://maps.apple.com/?ll={lat},{lon}\n"
                f"accuracy: {loc.get('horizontalAccuracy')}m, "
                f"timestamp: {datetime.fromtimestamp(loc.get('timeStamp', 0)/1000)}"
            )
    return _err(f"Device '{device}' not found")


def _findmy_play_sound(device: str) -> Dict:
    api = _get_icloud()
    for d in api.devices:
        if device.lower() in d.status().get("name", "").lower():
            d.play_sound()
            return _ok(f"🔔 Playing sound on {d.status().get('name')}")
    return _err(f"Device '{device}' not found")


# ---------------------------------------------------------------- dispatch

@tool
def use_apple(
    action: str,
    query: str = None,
    to: str = None,
    text: str = None,
    subject: str = None,
    body: str = None,
    title: str = None,
    chat: str = None,
    person: str = None,
    label: str = None,
    device: str = None,
    calendar_name: str = None,
    start: str = None,
    end: str = None,
    due: str = None,
    from_date: str = None,
    to_date: str = None,
    days: int = 7,
    limit: int = 20,
    with_images: bool = True,
) -> Dict[str, Any]:
    """🍎 Full Apple ecosystem control — Mail, Calendar, Messages, Contacts, Photos, Notes, Reminders, Find My.

    Local-first (no iCloud auth needed for most actions). Photos return real image blocks.

    Actions:
      **Messages** (chat.db + AppleScript):
      - "messages.list" — recent messages (chat=filter by name/number, limit)
      - "messages.search" — full-text search (query, limit)
      - "messages.chats" — list conversations (limit)
      - "messages.send" — send iMessage (to=phone/email, text)

      **Mail** (Mail.app):
      - "mail.unread" — unread inbox messages (limit)
      - "mail.search" — search subject/sender (query, limit)
      - "mail.read" — read full email body (query=subject substring)
      - "mail.send" — send email (to, subject, body)

      **Calendar** (Calendar.app):
      - "calendar.events" — upcoming events (days=7, limit)
      - "calendar.create" — new event (title, start='YYYY-MM-DD HH:MM', end, calendar_name)

      **Contacts** (Contacts.app):
      - "contacts.search" — find people (query, limit)

      **Photos** (osxphotos, returns image content blocks):
      - "photos.search" — search (query and/or person/label/from_date/to_date, limit, with_images)
      - "photos.recent" — latest photos (limit, with_images)
      - "photos.albums" — list albums

      **Notes** (Notes.app):
      - "notes.list" — list notes (limit)
      - "notes.read" — read note (query=title substring)
      - "notes.create" — new note (title, body)

      **Reminders** (Reminders.app):
      - "reminders.list" — open reminders (limit)
      - "reminders.create" — new reminder (title, due='YYYY-MM-DD HH:MM')

      **Remote/off-Mac via app-specific password** (env or keychain 'strands-icloud'):
      - "imap.folders" — list mail folders
      - "imap.search" — search mail (query, chat=folder, limit)
      - "imap.unread" — unread mail (chat=folder, limit)
      - "imap.read" — full email (query=message_id, chat=folder)
      - "caldav.calendars" / "caldav.events" (days) / "caldav.create" (title, start, end, calendar_name)
      - "carddav.contacts" — contacts (query, limit)

      **Find My** (pyicloud — needs ICLOUD_USERNAME/ICLOUD_PASSWORD env):
      - "findmy.devices" — list devices with battery + location
      - "findmy.locate" — locate device (device=name substring)
      - "findmy.play_sound" — ping device (device)

    Requires: Full Disk Access (Messages/Mail), Automation permission per app (first-use prompt).

    Returns:
        Dict with status and content (text + image blocks for photos)
    """
    try:
        # messages
        if action == "messages.list":
            return _messages_list(chat, limit)
        if action == "messages.search":
            if not query:
                return _err("query required")
            return _messages_search(query, limit)
        if action == "messages.chats":
            return _messages_chats(limit)
        if action == "messages.send":
            if not (to and text):
                return _err("to and text required")
            return _messages_send(to, text)

        # mail
        if action == "mail.unread":
            return _mail_unread(limit)
        if action == "mail.search":
            if not query:
                return _err("query required")
            return _mail_search(query, limit)
        if action == "mail.read":
            if not query:
                return _err("query required")
            return _mail_read(query)
        if action == "mail.send":
            if not (to and subject and body):
                return _err("to, subject, body required")
            return _mail_send(to, subject, body)

        # calendar
        if action == "calendar.events":
            return _calendar_events(days, limit)
        if action == "calendar.create":
            if not (title and start):
                return _err("title and start required")
            return _calendar_create(title, start, end, calendar_name)

        # contacts
        if action == "contacts.search":
            if not query:
                return _err("query required")
            return _contacts_search(query, limit)

        # photos
        if action == "photos.search":
            return _photos_search(query, person, label, from_date, to_date, limit, with_images)
        if action == "photos.recent":
            return _photos_recent(limit, with_images)
        if action == "photos.albums":
            return _photos_albums()

        # notes
        if action == "notes.list":
            return _notes_list(limit)
        if action == "notes.read":
            if not query:
                return _err("query required")
            return _notes_read(query)
        if action == "notes.create":
            if not (title and body):
                return _err("title and body required")
            return _notes_create(title, body)

        # reminders
        if action == "reminders.list":
            return _reminders_list(limit)
        if action == "reminders.create":
            if not title:
                return _err("title required")
            return _reminders_create(title, due)

        # findmy
        if action == "findmy.devices":
            return _findmy_devices()
        if action == "findmy.locate":
            if not device:
                return _err("device required")
            return _findmy_locate(device)
        if action == "findmy.play_sound":
            if not device:
                return _err("device required")
            return _findmy_play_sound(device)

        # remote protocols (work off-Mac, app-specific password OK)
        if action.startswith(("imap.", "caldav.", "carddav.")):
            from . import remote
            if action == "imap.folders":
                return remote.imap_folders()
            if action == "imap.search":
                return remote.imap_search(query or "", folder=chat or "INBOX", limit=limit)
            if action == "imap.unread":
                return remote.imap_search(query or "", folder=chat or "INBOX", limit=limit, unread_only=True)
            if action == "imap.read":
                if not query:
                    return _err("query=message_id required")
                return remote.imap_read(query, folder=chat or "INBOX")
            if action == "caldav.calendars":
                return remote.caldav_calendars()
            if action == "caldav.events":
                return remote.caldav_events(days=days, limit=limit)
            if action == "caldav.create":
                if not (title and start):
                    return _err("title and start required")
                return remote.caldav_create(title, start, end, calendar_name)
            if action == "carddav.contacts":
                return remote.carddav_contacts(query, limit=limit)

        return _err(f"Unknown action: {action}")

    except subprocess.TimeoutExpired:
        return _err(f"Timeout on {action} — app may be slow/unresponsive")
    except RuntimeError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")
