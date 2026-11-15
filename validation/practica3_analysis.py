import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
VALIDATION_DIR = PROJECT_ROOT / "validation"
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

from practica2_analysis import build_observations, observations_with_distances


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _filter_model_rows(observations, bssid, access_points=None, plan_id=None, default_plan_id=None, default_meters_per_unit=None, delta_h_m=0.0):
    delta_h = _finite_number(delta_h_m)
    if delta_h is None or delta_h < 0:
        raise ValueError("delta_h_m must be a finite, non-negative number.")
    if access_points is not None:
        rows = []
        for row in observations:
            if row.get("bssid") != bssid:
                continue
            if row.get("x") is None or row.get("y") is None:
                continue
            ap = None
            for candidate in access_points:
                candidate_bssid = candidate.get("bssid") or candidate.get("radio_mac") or candidate.get("bssid_hash")
                if candidate_bssid and candidate_bssid.casefold() == bssid.casefold():
                    ap = candidate
                    break
                prefix = (candidate.get("bssid_prefix") or "").strip()
                if prefix and row.get("bssid", "").casefold().startswith(prefix.casefold() + ":"):
                    ap = candidate
                    break
            if ap is None:
                continue
            ap_x = _finite_number(ap.get("x"))
            ap_y = _finite_number(ap.get("y"))
            if ap_x is None or ap_y is None:
                continue
            if plan_id is not None and ap.get("plan_id") and ap.get("plan_id") != plan_id and row.get("plan_id") not in (None, plan_id):
                continue
            distance = math.hypot(float(row["x"]) - ap_x, float(row["y"]) - ap_y)
            scale = _finite_number(ap.get("meters_per_unit"))
            if scale is None:
                scale = _finite_number(row.get("meters_per_unit"))
            if scale is None:
                scale = _finite_number(default_meters_per_unit)
            if scale is not None and scale > 0:
                distance *= scale
            row_with_distance = dict(row)
            row_with_distance["distance"] = distance
            rows.append(row_with_distance)
    else:
        rows = [
            row for row in observations
            if row.get("bssid") == bssid
            and row.get("rssi_dbm") is not None
            and row.get("distance") is not None
        ]
    valid_rows = []
    for row in rows:
        horizontal_distance = _finite_number(row.get("distance"))
        rssi = _finite_number(row.get("rssi_dbm"))
        if horizontal_distance is None or horizontal_distance < 0 or rssi is None:
            continue
        distance = math.hypot(horizontal_distance, delta_h)
        if distance <= 0:
            continue
        valid_rows.append({
            "distance_m": distance,
            "rssi_dbm": rssi,
            "point_id": row.get("point_id"),
            "session_id": row.get("session_id"),
            "sample_index": row.get("sample_index"),
        })
    if not valid_rows:
        raise ValueError(f"No valid RSSI measurements found for BSSID '{bssid}'.")
    valid_rows.sort(key=lambda item: (item["distance_m"], item.get("point_id") or "", item.get("sample_index") or 0))
    return valid_rows


def fit_log_distance_exponent(rows, d0, reference_A=None):
    if d0 is None or not isinstance(d0, (int, float)) or d0 <= 0:
        raise ValueError("d0 must be a positive number.")
    x_values = []
    y_values = []
    for row in rows:
        distance = _finite_number(row.get("distance_m"))
        rssi = _finite_number(row.get("rssi_dbm"))
        if distance is None or distance <= 0 or rssi is None:
            continue
        x = math.log10(distance / float(d0))
        x_values.append(x)
        y_values.append(rssi)
    if not x_values:
        raise ValueError("No valid points available to fit the log-distance exponent.")

    if reference_A is None:
        mean_x = mean(x_values)
        mean_y = mean(y_values)
        fit_x = [value - mean_x for value in x_values]
        fit_y = [value - mean_y for value in y_values]
        sum_xx = sum(value * value for value in fit_x)
    else:
        reference_A = _finite_number(reference_A)
        if reference_A is None:
            raise ValueError("A measured reference level must be a finite number.")
        mean_y = None
        mean_x = None
        fit_x = x_values
        fit_y = [value - reference_A for value in y_values]
        sum_xx = sum(value * value for value in fit_x)
    if sum_xx <= 1e-12:
        raise ValueError(
            "No se puede estimar n: las medidas válidas de RSSI en dBm solo "
            "cubren una distancia. Si el AP aparece como red vecina, la captura "
            "guarda signal_percent (%), no RSSI en dBm; ese porcentaje no se "
            "puede usar como sustituto. Conecta el equipo a ese AP al medir en "
            "varios puntos o registra RSSI en dBm para las redes vecinas."
        )

    slope = sum(x * y for x, y in zip(fit_x, fit_y)) / sum_xx
    n = -slope / 10.0
    A = reference_A if reference_A is not None else mean_y - slope * mean_x
    predictions = []
    residuals = []
    for row, x in zip(
        (
            row for row in rows
            if _finite_number(row.get("distance_m")) is not None
            and _finite_number(row.get("distance_m")) > 0
            and _finite_number(row.get("rssi_dbm")) is not None
        ),
        x_values,
    ):
        distance = _finite_number(row.get("distance_m"))
        rssi = _finite_number(row.get("rssi_dbm"))
        predicted = A - 10.0 * n * math.log10(distance / float(d0))
        predictions.append((row, predicted))
        residuals.append(rssi - predicted)

    if not residuals:
        raise ValueError("No measurement residuals were produced by the log-distance fit.")

    sigma = math.sqrt(sum((error - mean(residuals)) ** 2 for error in residuals) / len(residuals))
    return {
        "A": A,
        "n": n,
        "slope": slope,
        "sigma": sigma,
        "residuals": residuals,
        "predictions": predictions,
    }


def estimate_reference_level(rows, d0):
    return fit_log_distance_exponent(rows, d0)["A"]


def compute_model_statistics(rows, A, d0, n):
    if d0 is None or not isinstance(d0, (int, float)) or d0 <= 0:
        raise ValueError("d0 must be a positive number.")
    errors = []
    for row in rows:
        distance = _finite_number(row.get("distance_m"))
        actual = _finite_number(row.get("rssi_dbm"))
        if distance is None or distance <= 0 or actual is None:
            continue
        predicted = float(A) - 10.0 * float(n) * math.log10(distance / float(d0))
        errors.append({
            "distance_m": distance,
            "rssi_dbm": actual,
            "predicted_rssi_dbm": predicted,
            "error_db": actual - predicted,
        })
    if not errors:
        raise ValueError("No valid measurements remain to evaluate the propagation model.")

    abs_errors = [abs(item["error_db"]) for item in errors]
    squared_errors = [item["error_db"] ** 2 for item in errors]
    residuals = [item["error_db"] for item in errors]
    sigma = math.sqrt(sum((error - mean(residuals)) ** 2 for error in residuals) / len(residuals))
    return {
        "n": float(n),
        "measurements": len(errors),
        "MAE": sum(abs_errors) / len(abs_errors),
        "RMSE": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "sigma": sigma,
        "errors": errors,
    }


def compare_propagation_models(rows, d0, fixed_n=2.0, reference_A=None):
    fitted = fit_log_distance_exponent(rows, d0, reference_A=reference_A)
    if reference_A is None:
        fixed_A = mean(
            float(row["rssi_dbm"])
            + 10.0 * fixed_n * math.log10(float(row["distance_m"]) / float(d0))
            for row in rows
            if _finite_number(row.get("distance_m")) is not None
            and _finite_number(row.get("distance_m")) > 0
            and _finite_number(row.get("rssi_dbm")) is not None
        )
    else:
        fixed_A = _finite_number(reference_A)
    fixed = compute_model_statistics(rows, fixed_A, d0, fixed_n)
    fitted_metrics = compute_model_statistics(rows, fitted["A"], d0, fitted["n"])
    return {
        "A": fitted["A"],
        "d0": float(d0),
        "reference_A": reference_A,
        "total_measurements": len(rows),
        "model_1": {
            "label": f"n = {fixed_n}",
            "n": float(fixed_n),
            "A": fixed_A,
            "MAE": fixed["MAE"],
            "RMSE": fixed["RMSE"],
            "sigma": None,
        },
        "model_2": {
            "label": f"n = {fitted_metrics['n']:.6f}",
            "n": float(fitted_metrics["n"]),
            "A": fitted["A"],
            "MAE": fitted_metrics["MAE"],
            "RMSE": fitted_metrics["RMSE"],
            "sigma": fitted_metrics["sigma"],
        },
        "fitted": fitted,
        "fixed": fixed,
    }


def plot_propagation_comparison(rows, d0, fixed_n=2.0, output_path=None, reference_A=None):
    import matplotlib.pyplot as plt

    model_summary = compare_propagation_models(
        rows,
        d0,
        fixed_n=fixed_n,
        reference_A=reference_A,
    )
    distances = [row["distance_m"] for row in rows]
    values = [row["rssi_dbm"] for row in rows]
    max_distance = max(distances)
    min_distance = min(distances)
    x_plot = [min_distance * 0.9, max_distance * 1.1]

    def model_line(model):
        return [
            model["A"] - 10.0 * model["n"] * math.log10(distance / float(d0))
            for distance in x_plot
        ]

    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.scatter(distances, values, c="black", s=28, alpha=0.8, label="Medidas válidas")
    axis.plot(x_plot, model_line(model_summary["model_1"]), color="tab:blue", linewidth=2, label=f"n = {fixed_n}")
    axis.plot(x_plot, model_line(model_summary["model_2"]), color="tab:orange", linewidth=2, label=f"n = {model_summary['model_2']['n']:.3f}")

    axis.set_xlabel("Distancia al AP (m)")
    axis.set_ylabel("RSSI (dBm)")
    axis.set_title("Comparación de modelos de propagación")
    axis.grid(True, linestyle="--", alpha=0.35)
    axis.legend()
    figure.tight_layout()
    if output_path:
        figure.savefig(output_path, dpi=300)
    return figure, model_summary


def _load_records(data_path):
    records = []
    with Path(data_path).open("r", encoding="utf-8") as handler:
        for line in handler:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def measure_reference_level(rows, point_id):
    reference_rows = [
        row for row in rows
        if row.get("point_id") == point_id
        and _finite_number(row.get("rssi_dbm")) is not None
        and _finite_number(row.get("distance_m")) is not None
    ]
    if not reference_rows:
        raise ValueError(f"No valid RSSI reference measurements found at point '{point_id}'.")
    distances = [float(row["distance_m"]) for row in reference_rows]
    if max(distances) - min(distances) > 0.005:
        raise ValueError(f"Reference point '{point_id}' has inconsistent distances.")
    values = [float(row["rssi_dbm"]) for row in reference_rows]
    reference_A = mean(values)
    return {
        "point_id": point_id,
        "d0": mean(distances),
        "A": reference_A,
        "measurements": len(values),
        "sigma": math.sqrt(
            sum((value - reference_A) ** 2 for value in values) / len(values)
        ),
    }


def analyze_propagation_dataset(data_dir, bssid, d0, inventory_path=None, plan_id=None, default_meters_per_unit=None, output_path=None, delta_h_m=0.0, reference_point_id=None):
    data_dir = Path(data_dir)
    candidate_paths = [data_dir / "screenshots_all.jsonl", data_dir / "screenshots.jsonl"]
    capture_path = next((path for path in candidate_paths if path.is_file()), None)
    if capture_path is None:
        raise FileNotFoundError(f"No capture data found in '{data_dir}'.")

    records = _load_records(capture_path)
    observations = build_observations(records)
    access_points = []
    if default_meters_per_unit is None and (plan_id or "").casefold() == "fic-p2":
        from map_measurements import FIC_P2_METERS_PER_PIXEL
        default_meters_per_unit = FIC_P2_METERS_PER_PIXEL
    if inventory_path is not None:
        from validation.map_measurements import load_access_point_inventory
        access_points = load_access_point_inventory(inventory_path, plan_id or "FIC-P2")
    rows = _filter_model_rows(
        observations,
        bssid,
        access_points=access_points if access_points else None,
        plan_id=plan_id,
        default_plan_id=plan_id,
        default_meters_per_unit=default_meters_per_unit,
        delta_h_m=delta_h_m,
    )
    reference = None
    reference_A = None
    if reference_point_id:
        reference = measure_reference_level(rows, reference_point_id)
        if d0 is not None and not math.isclose(
            float(d0),
            reference["d0"],
            rel_tol=1e-6,
            abs_tol=0.005,
        ):
            raise ValueError(
                f"d0 must match the measured distance at reference point "
                f"'{reference_point_id}' ({reference['d0']:.6f} m)."
            )
        d0 = reference["d0"]
        reference_A = reference["A"]
    elif d0 is None:
        d0 = 1.0

    summary = compare_propagation_models(rows, d0, reference_A=reference_A)
    summary["delta_h_m"] = float(delta_h_m)
    summary["reference"] = reference
    if output_path:
        plot_propagation_comparison(
            rows,
            d0,
            output_path=output_path,
            reference_A=reference_A,
        )
    return summary


def write_model_metrics_csv(summary, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model",
        "n",
        "A_dBm",
        "d0_m",
        "MAE_dB",
        "RMSE_dB",
        "sigma_dB",
        "measurements",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for key, label in (("model_1", "fixed_n_2"), ("model_2", "fitted_n")):
            model = summary[key]
            writer.writerow({
                "model": label,
                "n": model["n"],
                "A_dBm": model["A"],
                "d0_m": summary["d0"],
                "MAE_dB": model["MAE"],
                "RMSE_dB": model["RMSE"],
                "sigma_dB": "" if model["sigma"] is None else model["sigma"],
                "measurements": summary["total_measurements"],
            })
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Compare log-distance propagation models from saved WiFi captures.")
    parser.add_argument("--data-dir", default="data/practica2")
    parser.add_argument("--bssid", required=True, help="BSSID or MAC address to analyze.")
    parser.add_argument("--d0", type=float, help="Reference distance in meters; inferred from --reference-point-id when omitted.")
    parser.add_argument("--delta-h", type=float, default=0.0, help="Vertical separation between AP and receiver in meters.")
    parser.add_argument("--reference-point-id", help="Point whose repeated RSSI values define the measured reference A.")
    parser.add_argument("--inventory", help="Optional AP inventory CSV for distance calculations.")
    parser.add_argument("--plan-id", default="FIC-P2")
    parser.add_argument("--output", default="validation/practica3_model_comparison.png")
    parser.add_argument("--metrics-output", default="validation/practica3_model_metrics.csv")
    args = parser.parse_args()

    summary = analyze_propagation_dataset(
        args.data_dir,
        args.bssid,
        args.d0,
        inventory_path=args.inventory,
        plan_id=args.plan_id,
        output_path=args.output,
        delta_h_m=args.delta_h,
        reference_point_id=args.reference_point_id,
    )
    metrics_path = write_model_metrics_csv(summary, args.metrics_output)
    print(json.dumps({
        "A_dBm": summary["A"],
        "A_fixed_dBm": summary["model_1"]["A"],
        "A_fitted_dBm": summary["model_2"]["A"],
        "d0_m": summary["d0"],
        "delta_h_m": summary["delta_h_m"],
        "reference_point_id": summary["reference"]["point_id"] if summary["reference"] else None,
        "reference_measurements": summary["reference"]["measurements"] if summary["reference"] else None,
        "reference_sigma_db": summary["reference"]["sigma"] if summary["reference"] else None,
        "n_fixed": summary["model_1"]["n"],
        "n_fitted": summary["model_2"]["n"],
        "mae_fixed_db": summary["model_1"]["MAE"],
        "mae_fitted_db": summary["model_2"]["MAE"],
        "rmse_fixed_db": summary["model_1"]["RMSE"],
        "rmse_fitted_db": summary["model_2"]["RMSE"],
        "sigma_db": summary["model_2"]["sigma"],
        "measurements_used": summary["total_measurements"],
        "metrics_csv": str(metrics_path),
    }, indent=2))


if __name__ == "__main__":
    main()
