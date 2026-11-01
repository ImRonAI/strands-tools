"""Bluetooth monitoring and control tool with background scanning and GATT operations.

Background BLE scanning for device discovery and presence detection,
plus direct bluetooth control and GATT read/write operations.

Actions:
    Monitoring:
        - start: Start background BLE scanning
        - stop: Stop scanning
        - status: Check if scanning is running
        - get_history: Get recent device detections
        - list_devices: Show all discovered devices
        - get_device: Get details for specific device
        - clear_history: Clear device history log

    Control:
        - scan_once: Single scan (no background)
        - connect: Connect to device
        - disconnect: Disconnect device
        - get_rssi: Get signal strength for device

    GATT Operations:
        - list_services: Discover services on device
        - list_characteristics: List characteristics for service
        - read_characteristic: Read data from characteristic
        - write_characteristic: Write data to characteristic
        - subscribe: Subscribe to characteristic notifications
        - unsubscribe: Unsubscribe from notifications
"""

import asyncio
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import bleak
    from bleak import BleakScanner, BleakClient
except ImportError:
    bleak = None

from strands import tool

# Global state
_monitor_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_save_dir = Path(".bluetooth_monitor")
_log_file = _save_dir / "devices.jsonl"
_devices_cache: Dict[str, dict] = {}  # address -> device info


def _log_entry(entry: dict):
    """Log device detection to jsonl file."""
    _save_dir.mkdir(exist_ok=True)
    with open(_log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_log() -> list:
    """Read all log entries."""
    if not _log_file.exists():
        return []

    entries = []
    with open(_log_file, "r") as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                continue
    return entries


def _classify_proximity(rssi: int) -> str:
    """Classify proximity based on RSSI."""
    if rssi >= -50:
        return "very_close"
    elif rssi >= -70:
        return "near"
    elif rssi >= -85:
        return "medium"
    else:
        return "far"


async def _scan_devices(duration: float = 5.0) -> List[dict]:
    """Scan for BLE devices."""
    devices = await BleakScanner.discover(timeout=duration, return_adv=True)

    results = []
    for address, (device, adv_data) in devices.items():
        rssi = adv_data.rssi if hasattr(adv_data, "rssi") else -100
        info = {
            "address": address,
            "name": device.name or adv_data.local_name or "Unknown",
            "rssi": rssi,
            "proximity": _classify_proximity(rssi),
            "timestamp": datetime.now().isoformat(),
        }
        results.append(info)

    return results


def _monitor_loop(interval: float):
    """Background monitoring loop."""
    global _devices_cache

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while not _stop_event.is_set():
        try:
            devices = loop.run_until_complete(_scan_devices(duration=interval))

            for device in devices:
                address = device["address"]

                # Check if new device or changed RSSI
                if address not in _devices_cache:
                    # New device detected
                    device["event"] = "discovered"
                    _log_entry(device)
                    _devices_cache[address] = device
                else:
                    # Update existing device
                    old_rssi = _devices_cache[address].get("rssi", -100)
                    new_rssi = device["rssi"]

                    # Log if significant RSSI change (>10 dB)
                    if abs(new_rssi - old_rssi) > 10:
                        device["event"] = "rssi_change"
                        device["old_rssi"] = old_rssi
                        _log_entry(device)

                    _devices_cache[address] = device

            # Check for disappeared devices
            current_addresses = {d["address"] for d in devices}
            for address in list(_devices_cache.keys()):
                if address not in current_addresses:
                    # Device disappeared
                    device = _devices_cache[address].copy()
                    device["event"] = "disappeared"
                    device["timestamp"] = datetime.now().isoformat()
                    _log_entry(device)
                    del _devices_cache[address]

        except Exception as e:
            pass

        time.sleep(max(interval, 1.0))  # Min 1s between scans

    loop.close()


# GATT Operations
_notification_callbacks: Dict[str, callable] = {}  # characteristic_uuid -> callback


async def _discover_services(address: str) -> List[dict]:
    """Discover services on a BLE device."""
    async with BleakClient(address) as client:
        services = []
        for service in client.services:
            services.append(
                {
                    "uuid": service.uuid,
                    "description": service.description or "Unknown Service",
                    "handle": service.handle,
                }
            )
        return services


async def _discover_characteristics(
    address: str, service_uuid: str = None
) -> List[dict]:
    """Discover characteristics on a BLE device."""
    async with BleakClient(address) as client:
        characteristics = []
        for service in client.services:
            if service_uuid and service.uuid != service_uuid:
                continue

            for char in service.characteristics:
                properties = []
                if "read" in char.properties:
                    properties.append("read")
                if (
                    "write" in char.properties
                    or "write-without-response" in char.properties
                ):
                    properties.append("write")
                if "notify" in char.properties or "indicate" in char.properties:
                    properties.append("notify")

                characteristics.append(
                    {
                        "uuid": char.uuid,
                        "service_uuid": service.uuid,
                        "description": char.description or "Unknown Characteristic",
                        "properties": properties,
                        "handle": char.handle,
                    }
                )
        return characteristics


async def _read_characteristic(address: str, char_uuid: str) -> bytes:
    """Read data from a characteristic."""
    async with BleakClient(address) as client:
        data = await client.read_gatt_char(char_uuid)
        return data


async def _write_characteristic(address: str, char_uuid: str, data: bytes) -> bool:
    """Write data to a characteristic."""
    async with BleakClient(address) as client:
        await client.write_gatt_char(char_uuid, data)
        return True


async def _start_notify(address: str, char_uuid: str, callback: callable) -> bool:
    """Subscribe to characteristic notifications."""
    async with BleakClient(address) as client:
        await client.start_notify(char_uuid, callback)
        # Keep connection alive to receive notifications
        await asyncio.sleep(30)  # Listen for 30 seconds
        await client.stop_notify(char_uuid)
        return True


@tool
def bluetooth(
    action: str,
    interval: float = 5.0,
    limit: int = 50,
    address: str = None,
    duration: float = 5.0,
    service_uuid: str = None,
    characteristic_uuid: str = None,
    data: str = None,
) -> Dict[str, Any]:
    """Bluetooth monitoring and control tool with GATT operations.

    Background BLE scanning with device discovery, presence detection, and GATT read/write.

    Args:
        action: Action to perform:
            Monitoring: start, stop, status, get_history, list_devices, get_device, clear_history
            Control: scan_once, connect, disconnect, get_rssi
            GATT: list_services, list_characteristics, read_characteristic, write_characteristic, subscribe
        interval: Scanning interval in seconds (default: 5.0)
        limit: Max number of history entries to return (default: 50)
        address: Device MAC address for device-specific actions
        duration: Scan duration in seconds (default: 5.0)
        service_uuid: Service UUID for GATT operations
        characteristic_uuid: Characteristic UUID for GATT operations
        data: Data to write (hex string, e.g., "010203")

    Returns:
        Dict with status and content
    """
    global _monitor_thread, _stop_event, _devices_cache

    if bleak is None:
        return {
            "status": "error",
            "content": [
                {
                    "text": "❌ bleak not installed. Run: pip install bleak"
                }
            ],
        }

    # Monitoring actions
    if action == "start":
        if _monitor_thread and _monitor_thread.is_alive():
            return {
                "status": "error",
                "content": [{"text": "⚠️ Bluetooth monitoring already running"}],
            }

        _stop_event = threading.Event()
        _monitor_thread = threading.Thread(
            target=_monitor_loop, args=(interval,), daemon=True
        )
        _monitor_thread.start()

        return {
            "status": "success",
            "content": [
                {
                    "text": f"✅ **Bluetooth Monitoring Started**\n"
                    f"⏱️  Interval: {interval}s\n"
                    f"📡 Scanning for BLE devices...\n"
                    f"💾 Save dir: `{_save_dir}`"
                }
            ],
        }

    elif action == "stop":
        if not _monitor_thread or not _monitor_thread.is_alive():
            return {
                "status": "error",
                "content": [{"text": "❌ Bluetooth monitoring not running"}],
            }

        _stop_event.set()
        _monitor_thread.join(timeout=interval + 2)

        return {
            "status": "success",
            "content": [{"text": "✅ **Bluetooth Monitoring Stopped**"}],
        }

    elif action == "status":
        running = _monitor_thread and _monitor_thread.is_alive()
        entries = _read_log()

        status_icon = "🟢" if running else "🔴"
        status_text = "✅ Yes" if running else "❌ No"

        return {
            "status": "success",
            "content": [
                {
                    "text": f"{status_icon} **Bluetooth Monitor Status**\n"
                    f"Running: {status_text}\n"
                    f"📊 Total detections: {len(entries)}\n"
                    f"📱 Currently visible: {len(_devices_cache)}\n"
                    f"💾 Save directory: `{_save_dir}`"
                }
            ],
        }

    elif action == "list_devices":
        if not _devices_cache:
            return {
                "status": "success",
                "content": [{"text": "📭 No devices currently detected"}],
            }

        lines = [f"📱 **Currently Visible Devices ({len(_devices_cache)}):**\n"]
        for address, device in sorted(
            _devices_cache.items(), key=lambda x: x[1]["rssi"], reverse=True
        ):
            name = device.get("name", "Unknown")
            rssi = device.get("rssi", -100)
            proximity = device.get("proximity", "unknown")

            prox_icon = {
                "very_close": "🟢",
                "near": "🟡",
                "medium": "🟠",
                "far": "🔴",
            }.get(proximity, "⚪")

            lines.append(f"{prox_icon} **{name}** ({address})")
            lines.append(f"   RSSI: {rssi} dBm | {proximity}")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    elif action == "get_device":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        if address not in _devices_cache:
            return {
                "status": "error",
                "content": [{"text": f"❌ Device {address} not found in cache"}],
            }

        device = _devices_cache[address]

        return {
            "status": "success",
            "content": [
                {
                    "text": f"📱 **Device Details**\n\n"
                    f"**Name:** {device.get('name', 'Unknown')}\n"
                    f"**Address:** {device['address']}\n"
                    f"**RSSI:** {device.get('rssi', 'N/A')} dBm\n"
                    f"**Proximity:** {device.get('proximity', 'unknown')}\n"
                    f"**Last Seen:** {device.get('timestamp', 'N/A')}"
                }
            ],
        }

    elif action == "get_history":
        entries = _read_log()

        if not entries:
            return {
                "status": "success",
                "content": [{"text": "📭 No bluetooth history yet"}],
            }

        recent = entries[-limit:]

        lines = [f"📋 **Recent {len(recent)} Bluetooth Events:**\n"]
        for entry in reversed(recent):
            ts = entry.get("timestamp", "").split("T")[1].split(".")[0]
            event = entry.get("event", "detected")
            name = entry.get("name", "Unknown")
            address = entry.get("address", "N/A")
            rssi = entry.get("rssi", "N/A")

            event_icon = {
                "discovered": "🆕",
                "disappeared": "👋",
                "rssi_change": "📊",
            }.get(event, "📡")

            lines.append(
                f"{event_icon} **{ts}** [{event}] {name} ({address}) - {rssi} dBm"
            )

        lines.append(f"\n📊 Total events: {len(entries)}")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    elif action == "clear_history":
        if _log_file.exists():
            _log_file.unlink()
        _devices_cache.clear()

        return {
            "status": "success",
            "content": [{"text": "✅ **Bluetooth history cleared**"}],
        }

    # Control actions
    elif action == "scan_once":
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            devices = loop.run_until_complete(_scan_devices(duration=duration))
            loop.close()

            if not devices:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No devices found"}],
                }

            lines = [f"📡 **BLE Scan Results ({len(devices)} devices):**\n"]
            for device in sorted(devices, key=lambda x: x["rssi"], reverse=True):
                name = device.get("name", "Unknown")
                address = device.get("address")
                rssi = device.get("rssi")
                proximity = device.get("proximity")

                prox_icon = {
                    "very_close": "🟢",
                    "near": "🟡",
                    "medium": "🟠",
                    "far": "🔴",
                }.get(proximity, "⚪")

                lines.append(f"{prox_icon} **{name}** ({address}) - {rssi} dBm")

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Scan failed: {str(e)}"}],
            }

    elif action == "connect":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def connect_device():
                async with BleakClient(address) as client:
                    is_connected = await client.is_connected()
                    return is_connected

            connected = loop.run_until_complete(connect_device())
            loop.close()

            if connected:
                return {
                    "status": "success",
                    "content": [{"text": f"✅ **Connected to {address}**"}],
                }
            else:
                return {
                    "status": "error",
                    "content": [{"text": f"❌ Failed to connect to {address}"}],
                }

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Connection failed: {str(e)}"}],
            }

    # GATT Operations
    elif action == "list_services":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            services = loop.run_until_complete(_discover_services(address))
            loop.close()

            if not services:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No services found"}],
                }

            lines = [f"🔍 **Services on {address}:**\n"]
            for service in services:
                lines.append(f"🔷 **{service['uuid']}**")
                lines.append(f"   {service['description']}")

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Service discovery failed: {str(e)}"}],
            }

    elif action == "list_characteristics":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            characteristics = loop.run_until_complete(
                _discover_characteristics(address, service_uuid)
            )
            loop.close()

            if not characteristics:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No characteristics found"}],
                }

            lines = [f"🔍 **Characteristics on {address}:**\n"]
            for char in characteristics:
                props = ", ".join(char["properties"])
                lines.append(f"🔹 **{char['uuid']}**")
                lines.append(f"   {char['description']}")
                lines.append(f"   Properties: {props}")
                lines.append(f"   Service: {char['service_uuid']}\n")

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Characteristic discovery failed: {str(e)}"}],
            }

    elif action == "read_characteristic":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        if not characteristic_uuid:
            return {
                "status": "error",
                "content": [{"text": "❌ characteristic_uuid parameter required"}],
            }

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            value = loop.run_until_complete(
                _read_characteristic(address, characteristic_uuid)
            )
            loop.close()

            # Format as hex string
            hex_value = value.hex()

            # Try to decode as text
            try:
                text_value = value.decode("utf-8")
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"📖 **Read from {characteristic_uuid}:**\n\n"
                            f"**Hex:** {hex_value}\n"
                            f"**Text:** {text_value}\n"
                            f"**Bytes:** {len(value)}"
                        }
                    ],
                }
            except:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"📖 **Read from {characteristic_uuid}:**\n\n"
                            f"**Hex:** {hex_value}\n"
                            f"**Bytes:** {len(value)}"
                        }
                    ],
                }

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Read failed: {str(e)}"}],
            }

    elif action == "write_characteristic":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        if not characteristic_uuid:
            return {
                "status": "error",
                "content": [{"text": "❌ characteristic_uuid parameter required"}],
            }

        if not data:
            return {
                "status": "error",
                "content": [{"text": "❌ data parameter required (hex string)"}],
            }

        try:
            # Convert hex string to bytes
            data_bytes = bytes.fromhex(data)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                _write_characteristic(address, characteristic_uuid, data_bytes)
            )
            loop.close()

            if success:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"✅ **Wrote to {characteristic_uuid}:**\n\n"
                            f"**Hex:** {data}\n"
                            f"**Bytes:** {len(data_bytes)}"
                        }
                    ],
                }

        except ValueError as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Invalid hex data: {str(e)}"}],
            }
        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Write failed: {str(e)}"}],
            }

    elif action == "subscribe":
        if not address:
            return {
                "status": "error",
                "content": [{"text": "❌ address parameter required"}],
            }

        if not characteristic_uuid:
            return {
                "status": "error",
                "content": [{"text": "❌ characteristic_uuid parameter required"}],
            }

        # Store notifications
        notifications = []

        def notification_handler(sender, data):
            hex_value = data.hex()
            try:
                text_value = data.decode("utf-8")
                notifications.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Hex: {hex_value} | Text: {text_value}"
                )
            except:
                notifications.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Hex: {hex_value}"
                )

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Start notifications and listen for 30 seconds
            async def listen():
                async with BleakClient(address) as client:
                    await client.start_notify(characteristic_uuid, notification_handler)
                    await asyncio.sleep(30)
                    await client.stop_notify(characteristic_uuid)

            loop.run_until_complete(listen())
            loop.close()

            if notifications:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"📡 **Notifications from {characteristic_uuid}:**\n\n"
                            + "\n".join(notifications)
                            + f"\n\n📊 Total: {len(notifications)} notifications"
                        }
                    ],
                }
            else:
                return {
                    "status": "success",
                    "content": [{"text": f"⚠️ No notifications received in 30 seconds"}],
                }

        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Subscribe failed: {str(e)}"}],
            }

    else:
        return {
            "status": "error",
            "content": [{"text": f"❌ Unknown action: {action}"}],
        }
