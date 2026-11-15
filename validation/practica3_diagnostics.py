import argparse
import csv
import inspect
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, pstdev


def band_for_channel(channel):
    try:
        channel = int(channel)
    except (TypeError, ValueError):
        return "unknown"
    if 1 <= channel <= 14:
        return "2.4 GHz"
    if 32 <= channel <= 177:
        return "5 GHz"
    return "unknown"


def collect_ssid_observations(records, ssid):
    observations = []
    for record in records:
        metadata = record.get("metadata") or {}
        position = metadata.get("position") or {}
        for network in record.get("visible_networks") or []:
            if (network.get("ssid") or "").strip().casefold() != ssid.casefold():
                continue
            for access_point in network.get("bssids") or []:
                bssid = access_point.get("bssid") or access_point.get("bssid_hash")
                if not bssid:
                    continue
                signal = access_point.get("signal_percent")
                if (
                    isinstance(signal, bool)
                    or not isinstance(signal, (int, float))
                    or not 0 <= signal <= 100
                ):
                    signal = None
                channel = access_point.get("channel")
                observations.append({
                    "bssid": bssid,
                    "channel": channel,
                    "band": band_for_channel(channel),
                    "signal_percent": float(signal) if signal is not None else None,
                    "point_id": position.get("point_id") or metadata.get("room"),
                })
    return observations


def summarize_bssids(observations):
    groups = defaultdict(list)
    for row in observations:
        if row["signal_percent"] is None:
            continue
        groups[(row["band"], row["bssid"], row["channel"])].append(
            row["signal_percent"]
        )
    summaries = []
    for (band, bssid, channel), values in sorted(groups.items()):
        summaries.append({
            "band": band,
            "bssid": bssid,
            "channel": channel,
            "observations": len(values),
            "mean_signal_percent": mean(values),
            "median_signal_percent": median(values),
            "std_signal_percent": pstdev(values),
            "min_signal_percent": min(values),
            "max_signal_percent": max(values),
        })
    return summaries


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate_diagnostics(data_file, ssid, output_dir):
    import matplotlib.pyplot as plt

    data_file = Path(data_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [
        json.loads(line)
        for line in data_file.open("r", encoding="utf-8")
        if line.strip()
    ]
    observations = collect_ssid_observations(records, ssid)
    if not any(row["signal_percent"] is not None for row in observations):
        raise ValueError(f"No valid signal-percent observations found for SSID '{ssid}'.")

    summaries = summarize_bssids(observations)
    channel_counts = Counter(
        (row["band"], int(row["channel"]))
        for row in observations
        if row["band"] != "unknown"
    )
    channel_rows = [
        {"band": band, "channel": channel, "bssid_observations": count}
        for (band, channel), count in sorted(channel_counts.items())
    ]
    bssid_csv = output_dir / "practica3_eduroam_bssid_summary.csv"
    channel_csv = output_dir / "practica3_eduroam_channel_counts.csv"
    _write_csv(
        bssid_csv,
        summaries,
        [
            "band", "bssid", "channel", "observations", "mean_signal_percent",
            "median_signal_percent", "std_signal_percent", "min_signal_percent",
            "max_signal_percent",
        ],
    )
    _write_csv(
        channel_csv,
        channel_rows,
        ["band", "channel", "bssid_observations"],
    )

    filename_ssid = re.sub(r"[^A-Za-z0-9._-]+", "_", ssid).strip("_") or "ssid"
    bands = ("2.4 GHz", "5 GHz")
    figure, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    for axis, band in zip(axes, bands):
        counts = {
            channel: count
            for (observed_band, channel), count in channel_counts.items()
            if observed_band == band
        }
        channels = sorted(counts)
        axis.bar(channels, [counts[channel] for channel in channels], color="tab:blue")
        axis.set_title(f"{band}: {ssid}")
        axis.set_xlabel("Canal")
        axis.set_ylabel("Detecciones BSSID")
        axis.set_xticks(channels)
        axis.tick_params(axis="x", labelrotation=45)
        axis.grid(axis="y", linestyle="--", alpha=0.35)
    channel_plot = output_dir / f"practica3_{filename_ssid}_channels_by_band.png"
    figure.savefig(channel_plot, dpi=220)
    plt.close(figure)

    signal_plots = []
    for band, suffix in (("2.4 GHz", "2_4GHz"), ("5 GHz", "5GHz")):
        band_summaries = [row for row in summaries if row["band"] == band]
        if not band_summaries:
            continue
        band_summaries.sort(key=lambda row: row["mean_signal_percent"])
        values_by_bssid = [
            [
                row["signal_percent"]
                for row in observations
                if row["band"] == band and row["bssid"] == summary["bssid"]
            ]
            for summary in band_summaries
        ]
        height = max(6.0, len(band_summaries) * 0.24)
        figure, axis = plt.subplots(figsize=(11, height), constrained_layout=True)
        boxplot_options = {"showfliers": False}
        if "orientation" in inspect.signature(axis.boxplot).parameters:
            boxplot_options["orientation"] = "horizontal"
        else:
            boxplot_options["vert"] = False
        axis.boxplot(values_by_bssid, **boxplot_options)
        axis.set_yticks(range(1, len(band_summaries) + 1))
        axis.set_yticklabels([row["bssid"] for row in band_summaries])
        axis.set_title(f"{ssid}: calidad porcentual por BSSID ({band})")
        axis.set_xlabel("Señal informada por Windows (%)")
        axis.set_ylabel("BSSID (cada radio se representa por separado)")
        axis.set_xlim(0, 100)
        axis.grid(axis="x", linestyle="--", alpha=0.35)
        axis.tick_params(axis="y", labelsize=7)
        plot_path = output_dir / f"practica3_{filename_ssid}_signal_percent_{suffix}.png"
        figure.savefig(plot_path, dpi=220)
        plt.close(figure)
        signal_plots.append(plot_path)

    return {
        "ssid": ssid,
        "bssid_detections": len(observations),
        "valid_signal_percent_observations": sum(
            row["signal_percent"] is not None for row in observations
        ),
        "bssid_counts_by_band": {
            band: len({row["bssid"] for row in summaries if row["band"] == band})
            for band in bands
        },
        "channel_observations_by_band": {
            band: sum(count for (observed_band, _), count in channel_counts.items()
                      if observed_band == band)
            for band in bands
        },
        "bssid_csv": str(bssid_csv),
        "channel_csv": str(channel_csv),
        "channel_plot": str(channel_plot),
        "signal_plots": [str(path) for path in signal_plots],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate per-BSSID signal and channel diagnostics for one SSID."
    )
    parser.add_argument("--data-file", default="data/practica2/screenshots_all.jsonl")
    parser.add_argument("--ssid", default="eduroam")
    parser.add_argument("--output-dir", default="validation")
    args = parser.parse_args()
    print(json.dumps(
        generate_diagnostics(args.data_file, args.ssid, args.output_dir),
        indent=2,
    ))


if __name__ == "__main__":
    main()
