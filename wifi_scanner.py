import argparse
import datetime
import ctypes
import hashlib
import json
import os
import re
import subprocess
import time

def parse_args():
    parser = argparse.ArgumentParser(description="WiFi Data Acquisition CLI Tool for Windows")
    parser.add_argument("--room", default="Lab-1.1", help="Measurement location or room identifier")
    parser.add_argument("--orientation", default="0-North", help="Device orientation (e.g., 0-North, 180-South)")
    parser.add_argument("--interval", type=int, default=None, help="Cadence between samples in seconds")
    parser.add_argument("--samples", type=int, default=None, help="Total number of samples to collect")
    parser.add_argument(
        "--all",
        dest="include_all_networks",
        action="store_true",
        help="Include every detected SSID instead of only the connected SSID",
    )
    return parser.parse_args()

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def output_path_for_mode(include_all_networks):
    filename = "screenshots_all.jsonl" if include_all_networks else "screenshots.jsonl"
    return os.path.join("data", filename)

def effective_interval(interval, include_all_networks):
    if include_all_networks and interval < 5:
        return 5
    return interval

def hash_bssid(bssid_str):
    """Anonymizes BSSID using SHA-256 prefix for privacy while preserving tracking consistency."""
    if not bssid_str:
        return None
    return hashlib.sha256(bssid_str.strip().encode()).hexdigest()[:12]

def run_cmd(cmd):
    try:
        # netsh returns UTF-8 output on the tested Windows installation.
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
        return res.stdout
    except subprocess.CalledProcessError:
        return None
    except UnicodeDecodeError:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
        return res.stdout

def get_active_connection():
    output = run_cmd(["netsh", "wlan", "show", "interfaces"])
    if not output:
        return {"error": "Failed to run netsh"}
    
    output_lower = output.lower()
    if "no hay ninguna interfaz" in output_lower or "there is no wireless interface" in output_lower:
        return {"error": "WiFi interface disabled or unavailable"}

    info = {
        "status": "disconnected",
        "ssid": None,
        "bssid_hash": None,
        "signal_percent": None,
        "rssi_dbm": None,
        "channel": None,
        "band": None,
        "radio_type": None,
        "rx_rate_mbps": None,
        "tx_rate_mbps": None
    }

    for line in output.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        
        key, val = [part.strip() for part in line.split(":", 1)]
        key_lower = key.lower()

        # Estado / State
        if key_lower in ["estado", "state"]:
            if "conectado" in val.lower() or "connected" in val.lower():
                info["status"] = "connected"

        # SSID (evitar confundir con AP BSSID)
        elif key_lower == "ssid":
            info["ssid"] = val

        # AP BSSID o BSSID
        elif "bssid" in key_lower:
            info["bssid_hash"] = hash_bssid(val)

        # Señal en %
        elif ("se" in key_lower and "al" in key_lower) or "signal" in key_lower:
            m = re.search(r"(\d+)%", val)
            if m:
                info["signal_percent"] = int(m.group(1))

        # RSSI directo en dBm
        elif "rssi" in key_lower:
            m = re.search(r"(-?\d+)", val)
            if m:
                info["rssi_dbm"] = int(m.group(1))

        # Canal
        elif "canal" in key_lower or "channel" in key_lower:
            m = re.search(r"(\d+)", val)
            if m:
                info["channel"] = int(m.group(1))

        # Banda (ej. 2.4 GHz, 5 GHz)
        elif "banda" in key_lower or "band" in key_lower:
            info["band"] = val

        # Tipo de radio
        elif "radio" in key_lower:
            info["radio_type"] = val

        # Velocidades de enlace
        elif "recepci" in key_lower or "receive rate" in key_lower:
            m = re.search(r"([\d\.]+)", val)
            if m:
                info["rx_rate_mbps"] = float(m.group(1))
        elif "transmisi" in key_lower or "transmit rate" in key_lower:
            m = re.search(r"([\d\.]+)", val)
            if m:
                info["tx_rate_mbps"] = float(m.group(1))

    return info

def request_wifi_scan():
    if os.name != "nt":
        return "Fresh WiFi scans are only supported on Windows."

    try:
        wlan = ctypes.WinDLL("wlanapi.dll")
    except OSError as error:
        return f"Could not load Windows WLAN API: {error}"

    dword = ctypes.c_uint32
    handle_type = ctypes.c_void_p

    class Guid(ctypes.Structure):
        _fields_ = [
            ("data1", dword),
            ("data2", ctypes.c_uint16),
            ("data3", ctypes.c_uint16),
            ("data4", ctypes.c_ubyte * 8),
        ]

    class InterfaceInfo(ctypes.Structure):
        _fields_ = [
            ("interface_guid", Guid),
            ("description", ctypes.c_wchar * 256),
            ("state", dword),
        ]

    class InterfaceInfoList(ctypes.Structure):
        _fields_ = [
            ("count", dword),
            ("index", dword),
            ("interfaces", InterfaceInfo * 1),
        ]

    wlan.WlanOpenHandle.argtypes = [
        dword,
        ctypes.c_void_p,
        ctypes.POINTER(dword),
        ctypes.POINTER(handle_type),
    ]
    wlan.WlanOpenHandle.restype = dword
    wlan.WlanEnumInterfaces.argtypes = [
        handle_type,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(InterfaceInfoList)),
    ]
    wlan.WlanEnumInterfaces.restype = dword
    wlan.WlanScan.argtypes = [
        handle_type,
        ctypes.POINTER(Guid),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    wlan.WlanScan.restype = dword
    wlan.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    wlan.WlanCloseHandle.argtypes = [handle_type, ctypes.c_void_p]

    handle = handle_type()
    negotiated_version = dword()
    interface_list = ctypes.POINTER(InterfaceInfoList)()

    try:
        result = wlan.WlanOpenHandle(2, None, ctypes.byref(negotiated_version), ctypes.byref(handle))
        if result != 0:
            return f"WlanOpenHandle failed with Windows error {result}."

        result = wlan.WlanEnumInterfaces(handle, None, ctypes.byref(interface_list))
        if result != 0:
            return f"WlanEnumInterfaces failed with Windows error {result}."

        interface_info = interface_list.contents
        first_interface = ctypes.addressof(interface_info) + InterfaceInfoList.interfaces.offset
        interfaces = ctypes.cast(first_interface, ctypes.POINTER(InterfaceInfo))
        scan_results = [
            wlan.WlanScan(handle, ctypes.byref(interfaces[index].interface_guid), None, None, None)
            for index in range(interface_info.count)
        ]

        if not scan_results or not any(result == 0 for result in scan_results):
            return "Windows could not start a WiFi scan."

        time.sleep(4)
        failures = [result for result in scan_results if result != 0]
        if failures:
            return f"Some WiFi interfaces could not be scanned: {failures}."
        return None
    finally:
        if interface_list:
            wlan.WlanFreeMemory(interface_list)
        if handle:
            wlan.WlanCloseHandle(handle, None)

def get_visible_networks():
    output = run_cmd(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if output is None:
        return None

    networks = []
    current_net = None

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SSID "):
            current_net = {
                "ssid": line.split(":", 1)[1].strip(),
                "bssids": []
            }
            networks.append(current_net)
        elif line.startswith("BSSID ") and current_net is not None:
            bssid_val = line.split(":", 1)[1].strip()
            current_net["bssids"].append({
                "bssid_hash": hash_bssid(bssid_val),
                "signal_percent": None,
                "channel": None,
                "radio_type": None
            })
        elif re.search(r"Señal|Signal", line, re.IGNORECASE) and current_net and current_net["bssids"]:
            m = re.search(r"(\d+)%", line)
            if m:
                current_net["bssids"][-1]["signal_percent"] = int(m.group(1))
        elif re.search(r"Canal|Channel", line, re.IGNORECASE) and current_net and current_net["bssids"]:
            m = re.search(r"(\d+)", line.split(":", 1)[1])
            if m:
                current_net["bssids"][-1]["channel"] = int(m.group(1))
        elif re.search(r"Tipo de radio|Radio type", line, re.IGNORECASE) and current_net and current_net["bssids"]:
            current_net["bssids"][-1]["radio_type"] = line.split(":", 1)[1].strip()

    return networks

def connected_network_from_active(active_info):
    ssid = active_info.get("ssid")
    if active_info.get("status") != "connected" or not ssid:
        return []

    return [{
        "ssid": ssid,
        "source": "active_interface",
        "bssids": [{
            "bssid_hash": active_info.get("bssid_hash"),
            "signal_percent": active_info.get("signal_percent"),
            "channel": active_info.get("channel"),
            "radio_type": active_info.get("radio_type"),
        }],
    }]

def acquire_network_observation(include_all_networks, active_info):
    if not include_all_networks:
        return connected_network_from_active(active_info), {"status": "not_requested"}

    scan_error = request_wifi_scan()
    if scan_error:
        return [], {"status": "error", "message": scan_error}

    visible_networks = get_visible_networks()
    if visible_networks is None:
        return [], {
            "status": "error",
            "message": "The netsh visible-network query failed.",
        }

    return visible_networks, {"status": "success"}

def print_visible_networks(networks, active_info):
    print(f"Networks included in capture: {len(networks)}")
    active_bssid = active_info.get("bssid_hash")

    if not networks:
        print("  No networks included in this capture.")
        return

    for network in networks:
        print(f"  SSID: {network.get('ssid') or '<hidden SSID>'}")
        for access_point in network.get("bssids", []):
            is_connected = (
                network.get("source") == "active_interface"
                or (access_point.get("bssid_hash") == active_bssid and active_bssid is not None)
            )
            status = "connected AP" if is_connected else "other AP"
            signal = access_point.get("signal_percent")
            channel = access_point.get("channel")
            radio_type = access_point.get("radio_type") or "n/a"
            signal_text = f"{signal}%" if signal is not None else "n/a"
            channel_text = channel if channel is not None else "n/a"
            bssid_hash = access_point.get("bssid_hash") or "n/a"
            print(
                f"    {status} | BSSID hash: {bssid_hash} | Signal: {signal_text} "
                f"| Channel: {channel_text} | Radio: {radio_type}"
            )

def omit_none_values(value):
    if isinstance(value, dict):
        return {key: omit_none_values(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [omit_none_values(item) for item in value if item is not None]
    return value

def main():
    args = parse_args()
    config = load_config()

    interval = args.interval if args.interval is not None else config.get("default_interval", 3)
    requested_interval = interval
    interval = effective_interval(interval, args.include_all_networks)
    if interval != requested_interval:
        print(f"--all requires an interval of at least 5s; using 5s instead of {requested_interval}s.")
    max_samples = args.samples if args.samples is not None else config.get("default_samples", 15)

    os.makedirs("data", exist_ok=True)
    output_filepath = output_path_for_mode(args.include_all_networks)

    print(f"Starting WiFi acquisition: {max_samples} samples, {interval}s interval.")
    network_mode = "all detected SSIDs" if args.include_all_networks else "connected AP only"
    print(f"Network selection: {network_mode}.")
    print(f"Incremental storage: {output_filepath}")

    samples_count = 0
    try:
        while samples_count < max_samples:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            active_info = get_active_connection()
            visible_info, network_scan = acquire_network_observation(
                args.include_all_networks,
                active_info,
            )
            if network_scan["status"] == "error":
                print(f"Warning: visible-network scan failed: {network_scan['message']}")
            elif network_scan["status"] == "success" and not visible_info:
                print("Visible-network scan succeeded; no networks were detected.")
            elif network_scan["status"] == "not_requested" and not visible_info:
                print("Warning: no active WiFi connection; use --all to scan visible networks.")

            record = {
                "metadata": {
                    "timestamp_utc": timestamp,
                    "device_id": config.get("device_id", "unknown-device"),
                    "campaign": config.get("default_campaign", "test-campaign"),
                    "building": config.get("building", "unknown-building"),
                    "floor": config.get("floor", "unknown-floor"),
                    "room": args.room,
                    "orientation": args.orientation,
                    "network_scope": "all_visible" if args.include_all_networks else "connected_ap"
                },
                "active_interface": active_info,
                "visible_networks": visible_info,
                "network_scan": network_scan
            }

            with open(output_filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(omit_none_values(record), ensure_ascii=False) + "\n")

            samples_count += 1
            print(f"[{timestamp}] Sample {samples_count}/{max_samples} | SSID: {active_info.get('ssid')} | Signal: {active_info.get('signal_percent')}%")
            if network_scan["status"] != "error":
                print_visible_networks(visible_info, active_info)

            if samples_count < max_samples:
                time.sleep(interval)

    except KeyboardInterrupt:
        print("\nAcquisition stopped by user. Existing records safely stored.")

if __name__ == "__main__":
    main()