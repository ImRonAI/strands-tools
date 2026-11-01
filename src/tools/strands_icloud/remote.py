"""🌐 Remote iCloud access via standard protocols — works OFF-Mac too.

Uses app-specific password (ICLOUD_USERNAME/ICLOUD_PASSWORD or keychain):
  imap.*    → imap.mail.me.com:993  (Mail)
  caldav.*  → caldav.icloud.com     (Calendar)
  carddav.* → contacts.icloud.com   (Contacts)

App-specific passwords WORK here (unlike pyicloud web API).
"""

import email
import email.header
import imaplib
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

IMAP_HOST = "imap.mail.me.com"
CALDAV_URL = "https://caldav.icloud.com"
CARDDAV_URL = "https://contacts.icloud.com"


def _creds() -> tuple:
    user = os.getenv("ICLOUD_USERNAME")
    pw = os.getenv("ICLOUD_PASSWORD")
    if not pw and user:
        try:
            import keyring
            pw = keyring.get_password("strands-icloud", user) or keyring.get_password("pyicloud", user)
        except ImportError:
            pass
    if not (user and pw):
        raise RuntimeError("Need ICLOUD_USERNAME + ICLOUD_PASSWORD (app-specific) env or keychain")
    return user, pw


def _ok(text: str) -> Dict[str, Any]:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> Dict[str, Any]:
    return {"status": "error", "content": [{"text": text}]}


# ---------------------------------------------------------------- IMAP

def _imap_connect() -> imaplib.IMAP4_SSL:
    user, pw = _creds()
    conn = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    conn.login(user, pw)
    return conn


def _decode_hdr(raw: Optional[str]) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def imap_folders() -> Dict:
    conn = _imap_connect()
    try:
        _, boxes = conn.list()
        names = []
        for b in boxes:
            m = re.search(rb'"([^"]+)"$|\s(\S+)$', b)
            if m:
                names.append((m.group(1) or m.group(2)).decode())
        return _ok(f"📬 {len(names)} folders:\n" + "\n".join(f"- {n}" for n in names))
    finally:
        conn.logout()


def imap_search(query: str, folder: str = "INBOX", limit: int = 20, unread_only: bool = False) -> Dict:
    conn = _imap_connect()
    try:
        conn.select(folder, readonly=True)
        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if query:
            criteria.append(f'(OR (OR SUBJECT "{query}" FROM "{query}") BODY "{query}")')
        crit = " ".join(criteria) if criteria else "ALL"
        _, data = conn.search(None, crit)
        ids = data[0].split()
        ids = ids[-limit:]
        lines = []
        for mid in reversed(ids):
            _, msg_data = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            raw = msg_data[0][1].decode(errors="replace")
            msg = email.message_from_string(raw)
            lines.append(f"- [{mid.decode()}] [{msg['Date']}] {_decode_hdr(msg['From'])}: {_decode_hdr(msg['Subject'])}")
        return _ok(f"📧 {len(lines)} results in {folder}" + (f" for '{query}'" if query else "") + ":\n" + "\n".join(lines))
    finally:
        conn.logout()


def imap_read(message_id: str, folder: str = "INBOX") -> Dict:
    conn = _imap_connect()
    try:
        conn.select(folder, readonly=True)
        _, msg_data = conn.fetch(message_id.encode(), "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", "", html)
                        break
        else:
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
        return _ok(
            f"📧 From: {_decode_hdr(msg['From'])}\nDate: {msg['Date']}\n"
            f"Subject: {_decode_hdr(msg['Subject'])}\n\n{body[:8000]}"
        )
    finally:
        conn.logout()


# ---------------------------------------------------------------- CalDAV

def _caldav_client():
    try:
        import caldav
    except ImportError:
        raise RuntimeError("caldav not installed: pip install caldav")
    user, pw = _creds()
    return caldav.DAVClient(url=CALDAV_URL, username=user, password=pw)


def caldav_calendars() -> Dict:
    client = _caldav_client()
    cals = client.principal().calendars()
    return _ok(f"📅 {len(cals)} calendars:\n" + "\n".join(f"- {c.name}" for c in cals))


def caldav_events(days: int = 7, limit: int = 50) -> Dict:
    client = _caldav_client()
    start = datetime.now()
    end = start + timedelta(days=days)
    lines = []
    for cal in client.principal().calendars():
        try:
            for ev in cal.search(start=start, end=end, event=True, expand=True):
                v = ev.vobject_instance.vevent
                summary = getattr(v, "summary", None)
                dtstart = getattr(v, "dtstart", None)
                s = summary.value if summary else "?"
                d = dtstart.value.strftime("%Y-%m-%d %H:%M") if dtstart else "?"
                lines.append(f"- [{d}] ({cal.name}) {s}")
        except Exception:
            continue
    lines.sort()
    lines = lines[:limit]
    if not lines:
        return _ok(f"📅 No events in next {days} days (CalDAV)")
    return _ok(f"📅 {len(lines)} events (next {days}d, via CalDAV):\n" + "\n".join(lines))


def caldav_create(title: str, start: str, end: Optional[str] = None, calendar_name: Optional[str] = None) -> Dict:
    client = _caldav_client()
    sd = datetime.strptime(start, "%Y-%m-%d %H:%M")
    ed = datetime.strptime(end, "%Y-%m-%d %H:%M") if end else sd + timedelta(hours=1)
    cals = client.principal().calendars()
    cal = None
    if calendar_name:
        for c in cals:
            if calendar_name.lower() in (c.name or "").lower():
                cal = c
                break
        if not cal:
            return _err(f"Calendar '{calendar_name}' not found. Have: {[c.name for c in cals]}")
    else:
        cal = cals[0]
    cal.save_event(dtstart=sd, dtend=ed, summary=title)
    return _ok(f"✅ Event created via CalDAV: {title} @ {start} in '{cal.name}'")


# ---------------------------------------------------------------- CardDAV

def carddav_contacts(query: Optional[str] = None, limit: int = 50) -> Dict:
    """List/search contacts via CardDAV addressbook."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests not installed")
    user, pw = _creds()
    auth = (user, pw)

    # discover principal
    r = requests.request(
        "PROPFIND", CARDDAV_URL + "/",
        auth=auth, headers={"Depth": "0", "Content-Type": "text/xml"},
        data='<propfind xmlns="DAV:"><prop><current-user-principal/></prop></propfind>',
        timeout=30,
    )
    m = re.search(r"<href>([^<]*principal[^<]*)</href>", r.text)
    if not m:
        return _err(f"CardDAV principal discovery failed (HTTP {r.status_code})")
    principal = m.group(1)

    # discover addressbook home
    r = requests.request(
        "PROPFIND", CARDDAV_URL + principal,
        auth=auth, headers={"Depth": "0", "Content-Type": "text/xml"},
        data='<propfind xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><prop><C:addressbook-home-set/></prop></propfind>',
        timeout=30,
    )
    m = re.search(r"<href[^>]*>([^<]+)</href>", r.text.split("addressbook-home-set")[1] if "addressbook-home-set" in r.text else "")
    if not m:
        return _err("CardDAV addressbook home discovery failed")
    home = m.group(1)
    if home.startswith("http"):
        base = home
    else:
        base = CARDDAV_URL + home

    # fetch vcards
    r = requests.request(
        "REPORT", base.rstrip("/") + "/card/",
        auth=auth, headers={"Depth": "1", "Content-Type": "text/xml"},
        data='<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><C:address-data/></D:prop></C:addressbook-query>',
        timeout=60,
    )
    cards = re.findall(r"BEGIN:VCARD.*?END:VCARD", r.text, re.DOTALL)
    results = []
    for c in cards:
        fn = re.search(r"^FN[^:]*:(.+)$", c, re.MULTILINE)
        tel = re.findall(r"^TEL[^:]*:(.+)$", c, re.MULTILINE)
        em = re.findall(r"^EMAIL[^:]*:(.+)$", c, re.MULTILINE)
        clean = lambda s: s.replace("&#13;", "").replace("\r", "").strip()
        name = clean(fn.group(1)) if fn else "?"
        if query and query.lower() not in name.lower():
            continue
        results.append(f"- {name} | 📞 {' '.join(clean(t) for t in tel) or '-'} | ✉️ {' '.join(clean(e) for e in em) or '-'}")
        if len(results) >= limit:
            break
    return _ok(f"👤 {len(results)} contacts (CardDAV):\n" + "\n".join(results))
