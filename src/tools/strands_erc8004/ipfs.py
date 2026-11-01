"""
IPFS tool for Strands Agents — upload, pin, fetch, and manage content on IPFS.

Supports multiple backends:
  1. Pinata (recommended, free tier: 1GB) — set PINATA_JWT
  2. web3.storage (free tier: 5GB) — set W3S_TOKEN
  3. Local IPFS node — set IPFS_API (default: http://127.0.0.1:5001)
  4. Public gateways (read-only, no auth needed)

Completes the ERC-8004 workflow:
  erc8004(action="create_registration_file") → ipfs(action="upload") → erc8004(action="register_agent", uri="ipfs://...")
"""

import json
import os
import time
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from strands import tool

# ─── Gateway config ──────────────────────────────────────────────────────────

GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://dweb.link/ipfs/",
    "https://w3s.link/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
]

PINATA_API = "https://api.pinata.cloud"
W3S_API = "https://api.web3.storage"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _get_http():
    """Get requests with retry."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def _detect_backend():
    """Auto-detect available IPFS backend."""
    if os.getenv("PINATA_JWT"):
        return "pinata"
    if os.getenv("W3S_TOKEN"):
        return "w3s"
    # Check local IPFS
    api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
    try:
        _get_http().post(f"{api}/api/v0/id", timeout=2)
        return "local"
    except Exception:
        pass
    return None


def _cid_to_gateway_url(cid: str, gateway: str = None) -> str:
    """Convert CID to a gateway URL."""
    if not gateway:
        gateway = os.getenv("IPFS_GATEWAY", GATEWAYS[0])
    if not gateway.endswith("/"):
        gateway += "/"
    return f"{gateway}{cid}"


def _upload_pinata(
    content: bytes, filename: str, content_type: str = "application/json"
) -> Dict:
    """Upload to Pinata."""
    jwt = os.getenv("PINATA_JWT")
    if not jwt:
        raise ValueError("PINATA_JWT not set")

    http = _get_http()

    # Use pinFileToIPFS for binary, pinJSONToIPFS for JSON
    if content_type == "application/json":
        try:
            json_data = json.loads(content)
            resp = http.post(
                f"{PINATA_API}/pinning/pinJSONToIPFS",
                headers={
                    "Authorization": f"Bearer {jwt}",
                    "Content-Type": "application/json",
                },
                json={"pinataContent": json_data, "pinataMetadata": {"name": filename}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"cid": data["IpfsHash"], "size": data.get("PinSize", len(content))}
        except (json.JSONDecodeError, KeyError):
            pass  # Fall through to file upload

    # File upload
    resp = http.post(
        f"{PINATA_API}/pinning/pinFileToIPFS",
        headers={"Authorization": f"Bearer {jwt}"},
        files={"file": (filename, content, content_type)},
        data={"pinataMetadata": json.dumps({"name": filename})},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"cid": data["IpfsHash"], "size": data.get("PinSize", len(content))}


def _upload_w3s(
    content: bytes, filename: str, content_type: str = "application/json"
) -> Dict:
    """Upload to web3.storage."""
    token = os.getenv("W3S_TOKEN")
    if not token:
        raise ValueError("W3S_TOKEN not set")

    http = _get_http()
    resp = http.post(
        f"{W3S_API}/upload",
        headers={"Authorization": f"Bearer {token}", "X-Name": filename},
        files={"file": (filename, content, content_type)},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"cid": data["cid"], "size": len(content)}


def _upload_local(content: bytes, filename: str) -> Dict:
    """Upload to local IPFS node."""
    api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
    http = _get_http()
    resp = http.post(
        f"{api}/api/v0/add",
        files={"file": (filename, content)},
        params={"pin": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"cid": data["Hash"], "size": int(data.get("Size", len(content)))}


def _fetch_cid(cid: str, timeout: int = 15) -> bytes:
    """Fetch content by CID — tries Pinata (if JWT), local node, then public gateways."""
    http = _get_http()
    errors = []

    # Try Pinata dedicated gateway FIRST (fastest for Pinata-pinned content)
    jwt = os.getenv("PINATA_JWT")
    pinata_gw = os.getenv("PINATA_GATEWAY")  # e.g. https://mygateway.mypinata.cloud
    if jwt:
        try:
            if pinata_gw:
                url = f"{pinata_gw.rstrip('/')}/ipfs/{cid}"
            else:
                url = f"https://gateway.pinata.cloud/ipfs/{cid}"
            resp = http.get(
                url, headers={"Authorization": f"Bearer {jwt}"}, timeout=timeout
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            errors.append(f"pinata-gw: {e}")

    # Try local node (fast if running)
    try:
        api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
        resp = http.post(f"{api}/api/v0/cat", params={"arg": cid}, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        errors.append(f"local: {e}")

    # Try public gateways (shorter timeout per gateway, try more)
    custom_gw = os.getenv("IPFS_GATEWAY")
    gateways = ([custom_gw] if custom_gw else []) + GATEWAYS
    gw_timeout = min(timeout, 8)  # Max 8s per gateway to avoid long waits

    for gw in gateways:
        url = _cid_to_gateway_url(cid, gw)
        try:
            resp = http.get(url, timeout=gw_timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            errors.append(f"{gw}: {e}")
            continue

    raise ConnectionError(
        f"Could not fetch {cid} from any source:\n" + "\n".join(errors[:3])
    )


def _pin_pinata(cid: str, name: str = "") -> Dict:
    """Pin existing CID on Pinata."""
    jwt = os.getenv("PINATA_JWT")
    if not jwt:
        raise ValueError("PINATA_JWT not set")

    http = _get_http()
    body = {"hashToPin": cid}
    if name:
        body["pinataMetadata"] = {"name": name}

    resp = http.post(
        f"{PINATA_API}/pinning/pinByHash",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _list_pinata(limit: int = 20, name_filter: str = "") -> list:
    """List pinned items on Pinata."""
    jwt = os.getenv("PINATA_JWT")
    if not jwt:
        raise ValueError("PINATA_JWT not set")

    http = _get_http()
    params = {"pageLimit": limit, "status": "pinned"}
    if name_filter:
        params["metadata[name]"] = name_filter

    resp = http.get(
        f"{PINATA_API}/data/pinList",
        headers={"Authorization": f"Bearer {jwt}"},
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("rows", [])


def _unpin_pinata(cid: str) -> bool:
    """Unpin from Pinata."""
    jwt = os.getenv("PINATA_JWT")
    if not jwt:
        raise ValueError("PINATA_JWT not set")

    http = _get_http()
    resp = http.delete(
        f"{PINATA_API}/pinning/unpin/{cid}",
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=15,
    )
    resp.raise_for_status()
    return True


# ─── Tool ────────────────────────────────────────────────────────────────────


@tool
def ipfs(
    action: str,
    content: str = "",
    file_path: str = "",
    cid: str = "",
    filename: str = "",
    content_type: str = "application/json",
    backend: str = "",
    name_filter: str = "",
    max_results: int = 20,
) -> Dict[str, Any]:
    """IPFS tool — upload, fetch, pin, and manage content on IPFS.

    Supports Pinata (PINATA_JWT), web3.storage (W3S_TOKEN), or local IPFS node.

    Actions:
      upload      — Upload content or file to IPFS. Returns ipfs:// URI.
      fetch       — Fetch content by CID from public gateways.
      pin         — Pin existing CID on Pinata.
      unpin       — Unpin CID from Pinata.
      list        — List pinned items (Pinata only).
      status      — Check which backends are available.

    Args:
        action: upload, fetch, pin, unpin, list, status
        content: Text/JSON content to upload (for upload action)
        file_path: Path to file to upload (alternative to content)
        cid: IPFS CID (for fetch/pin/unpin)
        filename: Optional filename for upload
        content_type: MIME type (default: application/json)
        backend: Force backend: pinata, w3s, local (auto-detect if empty)
        name_filter: Filter by name (for list)
        max_results: Max items to return (for list, default 20)
    """
    try:
        if action == "status":
            backends = []
            if os.getenv("PINATA_JWT"):
                # Verify Pinata auth
                try:
                    http = _get_http()
                    resp = http.get(
                        f"{PINATA_API}/data/testAuthentication",
                        headers={"Authorization": f"Bearer {os.getenv('PINATA_JWT')}"},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    backends.append("✅ Pinata (authenticated)")
                except Exception as e:
                    backends.append(f"⚠️ Pinata (JWT set but auth failed: {e})")
            else:
                backends.append("❌ Pinata (set PINATA_JWT)")

            if os.getenv("W3S_TOKEN"):
                backends.append("✅ web3.storage (token set)")
            else:
                backends.append("❌ web3.storage (set W3S_TOKEN)")

            api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
            try:
                resp = _get_http().post(f"{api}/api/v0/id", timeout=2)
                peer_id = resp.json().get("ID", "?")[:16]
                backends.append(f"✅ Local IPFS ({api}, peer: {peer_id}...)")
            except Exception:
                backends.append(f"❌ Local IPFS ({api} — not running)")

            backends.append(
                f"✅ Public gateways (read-only): {len(GATEWAYS)} configured"
            )

            auto = _detect_backend() or "none (read-only mode)"

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"📡 IPFS Backends:\n"
                        + "\n".join(f"   {b}" for b in backends)
                        + f"\n\n   Auto-detected: {auto}"
                    }
                ],
            }

        elif action == "upload":
            if not content and not file_path:
                return {
                    "status": "error",
                    "content": [{"text": "Need 'content' or 'file_path' to upload"}],
                }

            # Resolve backend
            be = backend or _detect_backend()
            if not be:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "No IPFS backend available. Set one of:\n"
                            "  PINATA_JWT=... (recommended, free 1GB)\n"
                            "  W3S_TOKEN=... (free 5GB)\n"
                            "  Or run local IPFS: ipfs daemon"
                        }
                    ],
                }

            # Get content bytes
            if file_path:
                p = Path(file_path).expanduser()
                if not p.exists():
                    return {
                        "status": "error",
                        "content": [{"text": f"File not found: {file_path}"}],
                    }
                data = p.read_bytes()
                if not filename:
                    filename = p.name
                # Guess content type
                ext = p.suffix.lower()
                ct_map = {
                    ".json": "application/json",
                    ".txt": "text/plain",
                    ".html": "text/html",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".pdf": "application/pdf",
                }
                content_type = ct_map.get(ext, "application/octet-stream")
            else:
                data = content.encode("utf-8") if isinstance(content, str) else content
                if not filename:
                    filename = f"upload-{int(time.time())}.json"

            # Upload
            if be == "pinata":
                result = _upload_pinata(data, filename, content_type)
            elif be == "w3s":
                result = _upload_w3s(data, filename, content_type)
            elif be == "local":
                result = _upload_local(data, filename)
            else:
                return {
                    "status": "error",
                    "content": [{"text": f"Unknown backend: {be}"}],
                }

            cid_hash = result["cid"]
            ipfs_uri = f"ipfs://{cid_hash}"
            gateway_url = _cid_to_gateway_url(cid_hash)

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Uploaded to IPFS via {be}!\n"
                        f"   CID: {cid_hash}\n"
                        f"   URI: {ipfs_uri}\n"
                        f"   Gateway: {gateway_url}\n"
                        f"   Size: {result['size']} bytes\n"
                        f"   Filename: {filename}\n\n"
                        f"   Use with ERC-8004:\n"
                        f"   erc8004(action='register_agent', uri='{ipfs_uri}', ...)"
                    }
                ],
            }

        elif action == "fetch":
            if not cid:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Need 'cid' to fetch (e.g. 'QmXx...' or 'bafyrei...')"}
                    ],
                }

            # Strip ipfs:// prefix if present
            cid = cid.replace("ipfs://", "").strip("/")

            data = _fetch_cid(cid)

            # Try to parse as JSON for nice display
            try:
                parsed = json.loads(data)
                text = json.dumps(parsed, indent=2)
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"📄 Content from ipfs://{cid} ({len(data)} bytes):\n\n{text}"
                        }
                    ],
                }
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Binary or non-JSON
                preview = data[:200].hex() if len(data) > 200 else data.hex()
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"📦 Binary content from ipfs://{cid} ({len(data)} bytes)\n"
                            f"   Preview (hex): {preview}..."
                        }
                    ],
                }

        elif action == "pin":
            if not cid:
                return {"status": "error", "content": [{"text": "Need 'cid' to pin"}]}
            cid = cid.replace("ipfs://", "").strip("/")

            be = backend or _detect_backend()
            if be == "pinata":
                _pin_pinata(cid, name=filename or cid[:16])
                return {
                    "status": "success",
                    "content": [{"text": f"📌 Pinned {cid} on Pinata"}],
                }
            elif be == "local":
                api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
                _get_http().post(
                    f"{api}/api/v0/pin/add", params={"arg": cid}, timeout=60
                )
                return {
                    "status": "success",
                    "content": [{"text": f"📌 Pinned {cid} on local IPFS"}],
                }
            else:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Pin requires Pinata (PINATA_JWT) or local IPFS"}
                    ],
                }

        elif action == "unpin":
            if not cid:
                return {"status": "error", "content": [{"text": "Need 'cid' to unpin"}]}
            cid = cid.replace("ipfs://", "").strip("/")

            be = backend or _detect_backend()
            if be == "pinata":
                _unpin_pinata(cid)
                return {
                    "status": "success",
                    "content": [{"text": f"🗑️ Unpinned {cid} from Pinata"}],
                }
            elif be == "local":
                api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
                _get_http().post(
                    f"{api}/api/v0/pin/rm", params={"arg": cid}, timeout=15
                )
                return {
                    "status": "success",
                    "content": [{"text": f"🗑️ Unpinned {cid} from local IPFS"}],
                }
            else:
                return {
                    "status": "error",
                    "content": [{"text": "Unpin requires Pinata or local IPFS"}],
                }

        elif action == "list":
            be = backend or _detect_backend()
            if be == "pinata":
                pins = _list_pinata(limit=max_results, name_filter=name_filter)
                if not pins:
                    return {
                        "status": "success",
                        "content": [{"text": "No pinned items found"}],
                    }

                lines = [f"📋 Pinned items on Pinata ({len(pins)}):"]
                for p in pins:
                    cid_hash = p.get("ipfs_pin_hash", "?")
                    name = p.get("metadata", {}).get("name", "unnamed")
                    size = p.get("size", 0)
                    date = p.get("date_pinned", "")[:10]
                    lines.append(f"   {cid_hash[:20]}... | {name} | {size}B | {date}")
                return {"status": "success", "content": [{"text": "\n".join(lines)}]}
            elif be == "local":
                api = os.getenv("IPFS_API", "http://127.0.0.1:5001")
                resp = _get_http().post(
                    f"{api}/api/v0/pin/ls", params={"type": "recursive"}, timeout=15
                )
                resp.raise_for_status()
                keys = resp.json().get("Keys", {})
                lines = [f"📋 Pinned items on local IPFS ({len(keys)}):"]
                for c, info in list(keys.items())[:max_results]:
                    lines.append(f"   {c[:20]}... | {info.get('Type', '?')}")
                return {"status": "success", "content": [{"text": "\n".join(lines)}]}
            else:
                return {
                    "status": "error",
                    "content": [{"text": "List requires Pinata or local IPFS"}],
                }

        else:
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Unknown action: {action}\n"
                        f"Valid: upload, fetch, pin, unpin, list, status"
                    }
                ],
            }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ IPFS error: {e}"}]}
