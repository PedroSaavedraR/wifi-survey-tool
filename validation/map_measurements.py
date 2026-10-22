import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _valid_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def load_map_measurements(data_dir, plan_id):
    data_dir = Path(data_dir)
    files = [
        data_dir / "screenshots.jsonl",
        data_dir / "screenshots_all.jsonl",
    ]
    existing_files = [path for path in files if path.is_file()]
    if not existing_files:
        return {}

    points = {}
    for path in existing_files:
        with path.open("r", encoding="utf-8") as capture_file:
            for line_number, line in enumerate(capture_file, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in {path}, line {line_number}: {error}"
                    ) from error

                metadata = record.get("metadata") or {}
                position = metadata.get("position") or {}
                if position.get("plan_id") != plan_id:
                    continue
                x = _valid_number(position.get("x"))
                y = _valid_number(position.get("y"))
                if x is None or y is None:
                    continue

                point_key = (round(x), round(y))
                point = points.setdefault(point_key, {
                    "capture_count": 0,
                    "sessions": set(),
                    "point_ids": set(),
                    "networks": {},
                    "scan_errors": 0,
                })
                point["capture_count"] += 1
                point_id = position.get("point_id") or metadata.get("room")
                if point_id:
                    point["point_ids"].add(point_id)
                session_id = metadata.get("session_id")
                if session_id:
                    point["sessions"].add(session_id)
                if (record.get("network_scan") or {}).get("status") == "error":
                    point["scan_errors"] += 1

                active = record.get("active_interface") or {}
                active_bssid = active.get("bssid") or active.get("bssid_hash")
                connected_bssid = (
                    active_bssid
                    if active.get("status") == "connected"
                    else None
                )
                current_capture = {}
                for network in record.get("visible_networks") or []:
                    for access_point in network.get("bssids") or []:
                        bssid = access_point.get("bssid") or access_point.get("bssid_hash")
                        if not bssid:
                            continue
                        entry = current_capture.setdefault(bssid, {
                            "ssid": network.get("ssid"),
                            "signal_percent": access_point.get("signal_percent"),
                            "channel": access_point.get("channel"),
                            "radio_type": access_point.get("radio_type"),
                        })
                        if not entry.get("ssid") and network.get("ssid"):
                            entry["ssid"] = network["ssid"]

                if connected_bssid and connected_bssid not in current_capture:
                    current_capture[connected_bssid] = {
                        "ssid": active.get("ssid"),
                        "signal_percent": active.get("signal_percent"),
                        "channel": active.get("channel"),
                        "radio_type": active.get("radio_type"),
                    }

                for bssid, observed in current_capture.items():
                    network = point["networks"].setdefault(bssid, {
                        "bssid": bssid,
                        "ssids": set(),
                        "detections": 0,
                        "connected_captures": 0,
                        "signal_percent_values": [],
                        "rssi_dbm_values": [],
                        "rx_rate_values": [],
                        "tx_rate_values": [],
                        "channels": set(),
                        "radio_types": set(),
                        "bands": set(),
                    })
                    network["detections"] += 1
                    if observed.get("ssid"):
                        network["ssids"].add(observed["ssid"])
                    if bssid == connected_bssid:
                        network["connected_captures"] += 1
                        for key, field in (
                            ("rssi_dbm", "rssi_dbm_values"),
                            ("rx_rate_mbps", "rx_rate_values"),
                            ("tx_rate_mbps", "tx_rate_values"),
                        ):
                            value = _valid_number(active.get(key))
                            if value is not None:
                                network[field].append(value)
                        if active.get("band"):
                            network["bands"].add(active["band"])
                        if active.get("channel") is not None:
                            network["channels"].add(str(active["channel"]))
                        if active.get("radio_type"):
                            network["radio_types"].add(active["radio_type"])

                    signal = _valid_number(observed.get("signal_percent"))
                    if signal is not None:
                        network["signal_percent_values"].append(signal)
                    if observed.get("channel") is not None:
                        network["channels"].add(str(observed["channel"]))
                    if observed.get("radio_type"):
                        network["radio_types"].add(observed["radio_type"])

    for point in points.values():
        point["sessions"] = len(point["sessions"])
        point["point_ids"] = sorted(point["point_ids"])
        summaries = []
        for network in point["networks"].values():
            network["ssid"] = ", ".join(sorted(network.pop("ssids"))) or "SSID oculto/no disponible"
            network["mean_signal_percent"] = _optional_mean(network.pop("signal_percent_values"))
            network["mean_rssi_dbm"] = _optional_mean(network.pop("rssi_dbm_values"))
            network["mean_rx_rate_mbps"] = _optional_mean(network.pop("rx_rate_values"))
            network["mean_tx_rate_mbps"] = _optional_mean(network.pop("tx_rate_values"))
            for field in ("channels", "radio_types", "bands"):
                network[field] = ", ".join(sorted(network[field])) or "—"
            summaries.append(network)
        point["networks"] = sorted(
            summaries,
            key=lambda network: (-network["detections"], network["bssid"]),
        )
    return points


def _optional_mean(values):
    return mean(values) if values else None
