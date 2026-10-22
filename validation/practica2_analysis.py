import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median


def load_captures(data_dir):
    data_dir = Path(data_dir)
    files = [data_dir / "screenshots.jsonl", data_dir / "screenshots_all.jsonl"]
    existing_files = [path for path in files if path.exists()]
    if not existing_files:
        raise FileNotFoundError(f"No capture files found in '{data_dir}'.")

    records = []
    for path in existing_files:
        with path.open("r", encoding="utf-8") as capture_file:
            for line_number, line in enumerate(capture_file, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON in {path}, line {line_number}: {error}") from error
    return records


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def build_observations(records):
    observations = []
    for record in records:
        metadata = record.get("metadata") or {}
        position = metadata.get("position") or {}
        active = record.get("active_interface") or {}
        visible_networks = record.get("visible_networks") or []
        timestamp = metadata.get("timestamp_utc")
        active_bssid = active.get("bssid") or active.get("bssid_hash")
        found_active_bssid = False

        for network in visible_networks:
            for access_point in network.get("bssids") or []:
                bssid = access_point.get("bssid") or access_point.get("bssid_hash")
                if not bssid:
                    continue
                connected = (
                    bssid == active_bssid
                    and active.get("status") == "connected"
                )
                found_active_bssid = found_active_bssid or connected
                observations.append({
                    "timestamp_utc": timestamp,
                    "session_id": metadata.get("session_id"),
                    "sample_index": metadata.get("sample_index"),
                    "device_id": metadata.get("device_id"),
                    "campaign": metadata.get("campaign"),
                    "building": metadata.get("building"),
                    "floor": metadata.get("floor"),
                    "room": metadata.get("room"),
                    "orientation": metadata.get("orientation"),
                    "measurement_procedure": metadata.get("measurement_procedure"),
                    "measurement_incidents": metadata.get("measurement_incidents"),
                    "point_id": position.get("point_id") or metadata.get("room"),
                    "plan_id": position.get("plan_id"),
                    "map_file": position.get("map_file"),
                    "coordinate_system": position.get("coordinate_system"),
                    "origin": position.get("origin"),
                    "x_axis": position.get("x_axis"),
                    "y_axis": position.get("y_axis"),
                    "units": position.get("units"),
                    "meters_per_unit": _finite_number(position.get("meters_per_unit")),
                    "position_uncertainty": _finite_number(position.get("uncertainty")),
                    "x": _finite_number(position.get("x")),
                    "y": _finite_number(position.get("y")),
                    "ssid": network.get("ssid"),
                    "bssid": bssid,
                    "signal_percent": _finite_number(access_point.get("signal_percent")),
                    "rssi_dbm": _finite_number(active.get("rssi_dbm")) if connected else None,
                    "connected": connected,
                })

        if active_bssid and active.get("status") == "connected" and not found_active_bssid:
            observations.append({
                "timestamp_utc": timestamp,
                "session_id": metadata.get("session_id"),
                "sample_index": metadata.get("sample_index"),
                "device_id": metadata.get("device_id"),
                "campaign": metadata.get("campaign"),
                "building": metadata.get("building"),
                "floor": metadata.get("floor"),
                "room": metadata.get("room"),
                "orientation": metadata.get("orientation"),
                "measurement_procedure": metadata.get("measurement_procedure"),
                "measurement_incidents": metadata.get("measurement_incidents"),
                "point_id": position.get("point_id") or metadata.get("room"),
                "plan_id": position.get("plan_id"),
                "map_file": position.get("map_file"),
                "coordinate_system": position.get("coordinate_system"),
                "origin": position.get("origin"),
                "x_axis": position.get("x_axis"),
                "y_axis": position.get("y_axis"),
                "units": position.get("units"),
                "meters_per_unit": _finite_number(position.get("meters_per_unit")),
                "position_uncertainty": _finite_number(position.get("uncertainty")),
                "x": _finite_number(position.get("x")),
                "y": _finite_number(position.get("y")),
                "ssid": active.get("ssid"),
                "bssid": active_bssid,
                "signal_percent": _finite_number(active.get("signal_percent")),
                "rssi_dbm": _finite_number(active.get("rssi_dbm")),
                "connected": True,
            })
    return observations


def select_signal_metric(observations, bssid):
    selected = [row for row in observations if row["bssid"] == bssid]
    if any(row["rssi_dbm"] is not None for row in selected):
        return "rssi_dbm", "dBm"
    if any(row["signal_percent"] is not None for row in selected):
        return "signal_percent", "%"
    return None, None


def summarize_access_points(observations, point_id):
    groups = {}
    for row in observations:
        if row["point_id"] != point_id:
            continue
        group = groups.setdefault(row["bssid"], {
            "bssid": row["bssid"],
            "ssids": [],
            "detections": 0,
            "connected_captures": 0,
            "signal_percent_values": [],
            "rssi_dbm_values": [],
        })
        group["detections"] += 1
        if row["ssid"]:
            group["ssids"].append(row["ssid"])
        if row["connected"]:
            group["connected_captures"] += 1
        if row["signal_percent"] is not None:
            group["signal_percent_values"].append(row["signal_percent"])
        if row["rssi_dbm"] is not None:
            group["rssi_dbm_values"].append(row["rssi_dbm"])

    summaries = []
    for group in groups.values():
        ssids = Counter(group.pop("ssids"))
        percent_values = group.pop("signal_percent_values")
        rssi_values = group.pop("rssi_dbm_values")
        group["ssid"] = ssids.most_common(1)[0][0] if ssids else None
        group["max_signal_percent"] = max(percent_values) if percent_values else None
        group["median_signal_percent"] = median(percent_values) if percent_values else None
        group["max_rssi_dbm"] = max(rssi_values) if rssi_values else None
        group["median_rssi_dbm"] = median(rssi_values) if rssi_values else None
        summaries.append(group)
    return sorted(summaries, key=lambda item: (-item["detections"], item["bssid"]))


def summarize_signal_methods(observations, point_id, bssid):
    values = [
        row["rssi_dbm"]
        for row in observations
        if row["point_id"] == point_id
        and row["bssid"] == bssid
        and row["rssi_dbm"] is not None
    ]
    if not values:
        return {
            "valid_rssi_observations": 0,
            "mean_rssi_dbm": None,
            "median_rssi_dbm": None,
            "median_power_mw": None,
            "median_power_converted_dbm": None,
        }

    powers_mw = [10 ** (value / 10) for value in values]
    median_power_mw = median(powers_mw)
    return {
        "valid_rssi_observations": len(values),
        "mean_rssi_dbm": mean(values),
        "median_rssi_dbm": median(values),
        "median_power_mw": median_power_mw,
        "median_power_converted_dbm": 10 * math.log10(median_power_mw),
    }


def _access_point_by_bssid(access_points, bssid):
    for access_point in access_points:
        if access_point.get("bssid") == bssid or access_point.get("bssid_hash") == bssid:
            return access_point
    return None


def observations_with_distances(
    observations,
    access_points,
    bssid,
    default_plan_id=None,
    default_meters_per_unit=None,
):
    access_point = _access_point_by_bssid(access_points, bssid)
    if access_point is None:
        return []
    ap_x = _finite_number(access_point.get("x"))
    ap_y = _finite_number(access_point.get("y"))
    if ap_x is None or ap_y is None:
        return []
    ap_plan_id = access_point.get("plan_id") or default_plan_id
    ap_units = access_point.get("units")

    result = []
    for row in observations:
        if row["bssid"] != bssid or row["x"] is None or row["y"] is None:
            continue
        if not row["plan_id"] or row["plan_id"] != ap_plan_id:
            continue
        if row["units"] and ap_units and row["units"] != ap_units:
            continue
        distance = math.hypot(row["x"] - ap_x, row["y"] - ap_y)
        units = row["units"] or ap_units or "coordinate units"
        scale_value = access_point.get("meters_per_unit")
        if scale_value is None:
            scale_value = row.get("meters_per_unit")
        if scale_value is None:
            scale_value = default_meters_per_unit
        scale = _finite_number(scale_value)
        if scale_value is not None:
            if scale is None or scale <= 0:
                raise ValueError("meters_per_unit must be a positive finite number.")
            distance *= scale
            units = "m"
        result.append({**row, "distance": distance, "distance_units": units})
    return result


def plot_signal_distance(observations, bssid, metric, metric_units, output_path=None):
    import matplotlib.pyplot as plt

    rows = [
        row for row in observations
        if row["bssid"] == bssid
        and row.get("distance") is not None
        and row.get(metric) is not None
    ]
    if not rows:
        raise ValueError("No valid observations have both the selected AP signal and a calculated distance.")

    distance_units = rows[0]["distance_units"]
    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.scatter(
        [row["distance"] for row in rows],
        [row[metric] for row in rows],
        alpha=0.8,
        edgecolors="white",
        linewidths=0.4,
    )
    axis.set_xlabel(f"Distance to AP ({distance_units})")
    axis.set_ylabel(f"{metric} ({metric_units})")
    axis.set_title(f"Observed WiFi signal by distance — AP {bssid}")
    axis.grid(True, linestyle="--", alpha=0.4)
    figure.tight_layout()
    if output_path:
        figure.savefig(output_path, dpi=200)
    return figure


def plot_floorplan(
    observations,
    access_points,
    bssid,
    metric,
    metric_units,
    plan_file,
    default_plan_id=None,
    output_path=None,
):
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    image_path = Path(plan_file)
    if not image_path.is_file():
        raise FileNotFoundError(f"Floor plan image not found: '{image_path}'.")
    access_point = _access_point_by_bssid(access_points, bssid)
    if access_point is None:
        raise ValueError(f"No floor-plan position configured for AP '{bssid}'.")
    ap_x = _finite_number(access_point.get("x"))
    ap_y = _finite_number(access_point.get("y"))
    if ap_x is None or ap_y is None:
        raise ValueError(f"AP '{bssid}' must have numeric x and y coordinates.")
    ap_plan_id = access_point.get("plan_id") or default_plan_id
    ap_units = access_point.get("units")

    groups = {}
    for row in observations:
        if (
            row["bssid"] != bssid
            or row["plan_id"] != ap_plan_id
            or (row["units"] and ap_units and row["units"] != ap_units)
            or row["x"] is None
            or row["y"] is None
            or row.get(metric) is None
        ):
            continue
        key = (row["point_id"], row["x"], row["y"])
        groups.setdefault(key, []).append(row[metric])
    if not groups:
        raise ValueError("No measured positions for this AP and plan can be plotted.")

    image = mpimg.imread(image_path)
    figure, axis = plt.subplots(figsize=(10, 7))
    axis.imshow(image, origin="upper")
    points = list(groups)
    scatter = axis.scatter(
        [point[1] for point in points],
        [point[2] for point in points],
        c=[median(groups[point]) for point in points],
        cmap="RdYlGn",
        edgecolors="black",
        linewidths=0.7,
        s=85,
    )
    for point in points:
        if point[0]:
            axis.annotate(str(point[0]), (point[1], point[2]), xytext=(5, 5), textcoords="offset points")
    axis.scatter([ap_x], [ap_y], marker="*", c="blue", edgecolors="white", s=230, label="AP")
    figure.colorbar(scatter, ax=axis, label=f"Median {metric} ({metric_units})")
    axis.set_title(f"Measured positions on plan — AP {bssid}")
    axis.set_xlabel("x (plan coordinates)")
    axis.set_ylabel("y (plan coordinates)")
    axis.legend()
    figure.tight_layout()
    if output_path:
        figure.savefig(output_path, dpi=200)
    return figure
