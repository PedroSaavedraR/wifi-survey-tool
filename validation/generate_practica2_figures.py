import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from validation.map_measurements import (
    FIC_P2_METERS_PER_PIXEL,
    load_access_point_inventory,
)
from validation.practica2_analysis import (
    build_observations,
    observations_with_distances,
    plot_floorplan,
    plot_signal_distance,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate offline Practice 2 signal and floor-plan figures."
    )
    parser.add_argument("--data-dir", default="data/practica2")
    parser.add_argument("--inventory")
    parser.add_argument("--plan-file", default="FIC - P2.png")
    parser.add_argument("--plan-id", default="FIC-P2")
    parser.add_argument(
        "--access-point",
        default="INFOR-A04-2-05-2115",
        help="Inventory device name (default: INFOR-A04-2-05-2115)",
    )
    parser.add_argument("--output-dir", default="figuras_memoria")
    args = parser.parse_args()

    data_path = Path(args.data_dir) / "screenshots_all.jsonl"
    if not data_path.is_file():
        raise FileNotFoundError(f"Capture file not found: '{data_path}'.")

    inventory_path = Path(args.inventory) if args.inventory else None
    if inventory_path is None:
        inventory_files = sorted(Path(".").glob("ap_list_up_*.csv"))
        if len(inventory_files) != 1:
            raise FileNotFoundError(
                "Specify --inventory when the project folder does not contain "
                "exactly one ap_list_up_*.csv file."
            )
        inventory_path = inventory_files[0]
    if not inventory_path.is_file():
        raise FileNotFoundError(f"AP inventory not found: '{inventory_path}'.")

    with data_path.open("r", encoding="utf-8") as capture_file:
        records = [
            json.loads(line)
            for line in capture_file
            if line.strip()
        ]
    observations = build_observations(records)
    access_points = load_access_point_inventory(inventory_path, args.plan_id)
    access_point = next(
        (
            item for item in access_points
            if item["name"] == args.access_point
        ),
        None,
    )
    if access_point is None:
        raise ValueError(
            f"Access point '{args.access_point}' is not present in the "
            f"inventory for plan '{args.plan_id}'."
        )
    if access_point["x"] is None or access_point["y"] is None:
        raise ValueError(
            f"Access point '{args.access_point}' has no position for "
            f"plan '{args.plan_id}'."
        )

    prefix = access_point["bssid_prefix"].casefold() + ":"
    signal_values = defaultdict(list)
    for row in observations:
        if (
            row["ssid"] == "eduroam"
            and row["plan_id"] == args.plan_id
            and row["bssid"].casefold().startswith(prefix)
            and row["signal_percent"] is not None
        ):
            signal_values[row["bssid"]].append(row["signal_percent"])
    if not signal_values:
        raise ValueError(
            f"No eduroam signal observations found for '{args.access_point}'."
        )
    bssid = max(
        sorted(signal_values),
        key=lambda candidate: (
            sum(signal_values[candidate]) / len(signal_values[candidate]),
            candidate,
        ),
    )

    positioned_ap = {
        **access_point,
        "bssid": bssid,
        "plan_id": args.plan_id,
        "units": "px",
        "meters_per_unit": FIC_P2_METERS_PER_PIXEL,
    }
    distances = observations_with_distances(
        observations,
        [positioned_ap],
        bssid,
        default_plan_id=args.plan_id,
        default_meters_per_unit=FIC_P2_METERS_PER_PIXEL,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", args.access_point).strip("_")
    distance_path = output_dir / f"senal_distancia_{slug}.png"
    plan_path = output_dir / f"plano_{slug}.png"

    plot_signal_distance(
        distances,
        bssid,
        "signal_percent",
        "%",
        output_path=distance_path,
        metric_label="Calidad de señal",
    )
    plot_floorplan(
        observations,
        [positioned_ap],
        bssid,
        "signal_percent",
        "%",
        args.plan_file,
        default_plan_id=args.plan_id,
        output_path=plan_path,
        metric_label="calidad de señal",
    )
    session_count = len({
        row["session_id"] for row in distances if row.get("session_id")
    })
    print(
        f"AP: {access_point['name']}; BSSID: {bssid}; "
        f"observations: {len(distances)}; sessions: {session_count}"
    )
    print(f"Distance plot: {distance_path}")
    print(f"Floor-plan plot: {plan_path}")
    print(
        "Distance calibration: approximately "
        f"{FIC_P2_METERS_PER_PIXEL:.5f} m/px from the floor-plan scale bar."
    )


if __name__ == "__main__":
    main()
