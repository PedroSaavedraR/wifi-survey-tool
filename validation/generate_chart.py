import argparse
import json
import os
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import re

def plot_all_networks(records, output_image, ssid_filter=None):
    samples = list(range(1, len(records) + 1))
    signal_by_bssid = {}
    matching_ssid_found = ssid_filter is None

    for sample, record in zip(samples, records):
        for network in record.get("visible_networks", []):
            if ssid_filter is not None and network.get("ssid") != ssid_filter:
                continue
            matching_ssid_found = True
            for access_point in network.get("bssids", []):
                bssid_hash = access_point.get("bssid_hash")
                signal = access_point.get("signal_percent")
                if bssid_hash and signal is not None:
                    signal_by_bssid.setdefault(bssid_hash, {})[sample] = signal

    if not matching_ssid_found:
        print(f"Error: SSID '{ssid_filter}' was not found in the all-networks data.")
        return

    if not signal_by_bssid:
        print("Error: No visible-network signal values found for the selected SSID.")
        return

    fig, ax = plt.subplots(figsize=(14, 7.5))
    for bssid_hash, values in sorted(signal_by_bssid.items()):
        ax.plot(
            samples,
            [values.get(sample) for sample in samples],
            marker=".",
            linewidth=1.2,
            markersize=4,
            label=bssid_hash,
        )

    previous_room = None
    for sample, record in zip(samples, records):
        room = record.get("metadata", {}).get("room", "Unknown")
        if room != previous_room:
            if previous_room is not None:
                ax.axvline(sample, color="#7F8C8D", linestyle=":", linewidth=1)
            previous_room = room

    title = f"Signal Strength for SSID: {ssid_filter}" if ssid_filter else "Signal Strength of All Detected Access Points"
    ax.set_title(title)
    ax.set_xlabel("Sample Sequence Index")
    ax.set_ylabel("Signal (%)")
    ax.set_ylim(0, 100)
    ax.set_xlim(1, len(records))
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(title="BSSID hash", loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=7)
    fig.tight_layout(rect=(0, 0, 0.82, 1))

    os.makedirs(os.path.dirname(output_image), exist_ok=True)
    fig.savefig(output_image, dpi=300)
    plt.close(fig)
    print(f"All-network chart saved to '{output_image}'.")

def main():
    parser = argparse.ArgumentParser(description="Plot WiFi capture data")
    parser.add_argument(
        "--all",
        dest="include_all_networks",
        action="store_true",
        help="Plot every detected access point from screenshots_all.jsonl",
    )
    parser.add_argument("--ssid", help="Filter the --all chart to this exact SSID")
    args = parser.parse_args()

    if args.ssid and not args.include_all_networks:
        parser.error("--ssid requires --all")

    data_filename = "screenshots_all.jsonl" if args.include_all_networks else "screenshots.jsonl"
    if args.include_all_networks and args.ssid:
        ssid_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", args.ssid).strip("_") or "network"
        image_filename = f"validation_chart_all_{ssid_slug}.png"
    else:
        image_filename = "validation_chart_all.png" if args.include_all_networks else "validation_chart.png"
    data_path = os.path.join("data", data_filename)
    output_dir = "validation"
    output_image = os.path.join(output_dir, image_filename)

    if not os.path.exists(data_path):
        print(f"Error: Data file not found at '{data_path}'.")
        return

    records = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not records:
        print("Error: No records found.")
        return

    if args.include_all_networks:
        plot_all_networks(records, output_image, args.ssid)
        return

    indices = []
    rssi_dbm = []
    rx_rates = []
    conditions = []

    for idx, item in enumerate(records, 1):
        meta = item.get("metadata", {})
        active = item.get("active_interface", {})

        rssi = active.get("rssi_dbm")
        rx = active.get("rx_rate_mbps")
        room = meta.get("room", "Unknown")
        ssid = active.get("ssid", "Unknown")

        indices.append(idx)
        rssi_dbm.append(rssi)
        rx_rates.append(rx)
        conditions.append(f"{room}\n({ssid})")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True)

    # Panel superior: Potencia recibida en dBm (escala invertida lógica de atenuación)
    ax1.plot(indices, rssi_dbm, marker="o", color="#0055A5", linewidth=1.8, markersize=4.5, label="RSSI (dBm)")
    ax1.set_ylabel("Received Power (dBm)", fontsize=11, fontweight="bold")
    ax1.set_ylim(-90, -25)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.set_title("WiFi Validation: Physical RSSI (dBm) & Rx Link Rate (Mbps)", fontsize=13, pad=12)

    # Panel inferior: Velocidad de enlace en escala semilogarítmica
    ax2.plot(indices, rx_rates, marker="s", color="#D9534F", linewidth=1.8, markersize=4.5, label="Rx Rate (Mbps)")
    ax2.set_ylabel("Rx Rate (Mbps) [Log Scale]", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Sample Sequence Index", fontsize=11, fontweight="bold")
    ax2.set_yscale("log")
    ax2.set_yticks([100, 144, 200, 300, 500, 866])
    ax2.get_yaxis().set_major_formatter(ScalarFormatter())
    ax2.set_ylim(90, 1050)
    ax2.grid(True, which="both", linestyle="--", alpha=0.5)

    # Separadores de series de medidas
    prev_cond = None
    for idx, cond in zip(indices, conditions):
        if cond != prev_cond:
            ax1.axvline(x=idx, color="#7F8C8D", linestyle=":", linewidth=1.2)
            ax2.axvline(x=idx, color="#7F8C8D", linestyle=":", linewidth=1.2)
            ax1.text(idx + 0.3, -28, cond, rotation=90, verticalalignment="top", 
                     fontsize=7.5, color="#2C3E50", fontweight="bold",
                     bbox=dict(boxstyle="square,pad=0.15", facecolor="white", edgecolor="none", alpha=0.7))
            prev_cond = cond

    ax1.legend(loc="lower right", framealpha=0.9)
    ax2.legend(loc="lower right", framealpha=0.9)
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(output_image, dpi=300)
    print(f"Chart with RSSI (dBm) successfully saved to '{output_image}'.")

if __name__ == "__main__":
    main()