import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean


# Router marker centers on the bundled FIC - P2.png floor plan.
FIC_P2_ACCESS_POINT_POSITIONS = {
    "INFOR-A04-2-02-2158": (298, 101),
    "INFOR-A04-2-03-2113": (629, 112),
    "INFOR-A04-2-05-2115": (795, 111),
    "INFOR-A01-2-07-2133": (1095, 115),
    "INFOR-A01-2-09-2134": (1259, 115),
    "INFOR-A04-2-01-2157": (299, 280),
    "INFOR-A04-2-04-2114": (630, 261),
    "INFOR-A04-2-06-2116": (803, 273),
    "INFOR-A01-2-10-2135": (1247, 273),
}


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
                        "signal_observation_count": 0,
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
                        network["signal_observation_count"] += 1
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


def load_access_point_inventory(inventory_path, plan_id):
    inventory_path = Path(inventory_path)
    plan_parts = plan_id.rsplit("-P", 1)
    if (
        len(plan_parts) != 2
        or plan_parts[0].casefold() != "fic"
        or not plan_parts[1].isdigit()
    ):
        return []
    floor_marker = f"-{plan_parts[1]}-"

    access_points = []
    with inventory_path.open("r", encoding="utf-8-sig", newline="") as inventory_file:
        reader = csv.DictReader(inventory_file)
        required_columns = {"Dispositivo", "Dirección MAC de radio"}
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                f"Invalid AP inventory headers in {inventory_path}; expected "
                "'Dispositivo' and 'Dirección MAC de radio'."
            )

        for row in reader:
            name = (row.get("Dispositivo") or "").strip()
            radio_mac = (row.get("Dirección MAC de radio") or "").strip().upper()
            if floor_marker not in name or not radio_mac:
                continue
            mac_parts = radio_mac.split(":")
            if len(mac_parts) != 6 or any(len(part) != 2 for part in mac_parts):
                raise ValueError(
                    f"Invalid radio MAC '{radio_mac}' for access point '{name}'."
                )

            x, y = (
                FIC_P2_ACCESS_POINT_POSITIONS.get(name, (None, None))
                if plan_id.casefold() == "fic-p2"
                else (None, None)
            )
            access_points.append({
                "name": name,
                "radio_mac": radio_mac,
                "bssid_prefix": ":".join(mac_parts[:5]),
                "x": x,
                "y": y,
            })
    return access_points


def summarize_router_eduroam_signal(point, access_points):
    summaries = []
    for access_point in access_points:
        matching_networks = [
            network
            for network in point["networks"]
            if network["bssid"].upper().startswith(access_point["bssid_prefix"] + ":")
            and "eduroam" in {
                ssid.strip().casefold()
                for ssid in network["ssid"].split(",")
            }
        ]
        networks_with_signal = [
            network
            for network in matching_networks
            if network["mean_signal_percent"] is not None
        ]
        strongest_network = max(
            networks_with_signal,
            key=lambda network: (
                network["mean_signal_percent"],
                network["bssid"],
            ),
            default=None,
        )
        summaries.append({
            **access_point,
            "detected": bool(matching_networks),
            "bssid": strongest_network["bssid"] if strongest_network else None,
            "mean_signal_percent": (
                strongest_network["mean_signal_percent"]
                if strongest_network else None
            ),
            "signal_observation_count": (
                strongest_network["signal_observation_count"]
                if strongest_network else 0
            ),
        })
    return summaries


def build_router_coverage_models(points, access_points):
    models = []
    for access_point in access_points:
        samples = []
        for (x, y), point in points.items():
            summary = summarize_router_eduroam_signal(point, [access_point])[0]
            value = summary["mean_signal_percent"]
            if value is not None and 0 <= value <= 100:
                if access_point["x"] is not None and access_point["y"] is not None:
                    distance = math.hypot(x - access_point["x"], y - access_point["y"])
                    samples.append((distance, value))

        radius_model = _fit_radial_signal(samples)
        models.append({
            **access_point,
            "samples": samples,
            **radius_model,
        })
    return models


def _fit_radial_signal(samples):
    if len(samples) < 2:
        return {
            "supported": False,
            "slope": None,
            "intercept": None,
            "radius_70": None,
            "radius_40": None,
            "max_radius": max((distance for distance, _ in samples), default=None),
        }

    distances = [distance for distance, _ in samples]
    signals = [signal for _, signal in samples]
    mean_distance = mean(distances)
    mean_signal = mean(signals)
    distance_variance = sum(
        (distance - mean_distance) ** 2
        for distance in distances
    )
    if distance_variance == 0:
        return {
            "supported": False,
            "slope": None,
            "intercept": None,
            "radius_70": None,
            "radius_40": None,
            "max_radius": max(distances),
        }

    slope = sum(
        (distance - mean_distance) * (signal - mean_signal)
        for distance, signal in samples
    ) / distance_variance
    intercept = mean_signal - slope * mean_distance
    max_radius = max(distances)
    if slope >= 0:
        return {
            "supported": False,
            "slope": slope,
            "intercept": intercept,
            "radius_70": None,
            "radius_40": None,
            "max_radius": max_radius,
        }

    def threshold_radius(threshold):
        crossing = (threshold - intercept) / slope
        return min(max(crossing, 0), max_radius)

    return {
        "supported": True,
        "slope": slope,
        "intercept": intercept,
        "radius_70": threshold_radius(70),
        "radius_40": threshold_radius(40),
        "max_radius": max_radius,
    }


def _optional_mean(values):
    return mean(values) if values else None
