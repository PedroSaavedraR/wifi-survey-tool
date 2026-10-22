# WiFi Coverage Survey Tool (Windows)

[English](README.md) | [Español](README.es.md)

A command-line tool for querying and recording the active WiFi connection and, optionally, visible networks. Each capture includes a timestamp and campaign and location labels; optional floor-plan coordinates support repeatable measurements and analysis in the Practice 02 notebook.

## 1. Environment and requirements

* **Tested operating system:** Windows 11.
* **Test device:** Lenovo LOQ 15 with a MediaTek MT7921 WiFi adapter.
* **Interpreter:** Python 3.8 or later. The version verified on the test device is Python 3.14.6.
* **System utilities:** `netsh.exe` and the native Windows WLAN API.
* **Dependencies:** capture and GUI use libraries included with Python for Windows (including Tkinter). Install Jupyter and `matplotlib` to run the notebook and generate analysis charts:

```cmd
python -m pip install jupyter matplotlib
```

The `--all` option requests a scan through the Windows WLAN API. On the test device, Windows location services had to be enabled and the collector had to be run with administrator privileges to retrieve visible networks. These requirements may vary depending on the Windows version, adapter, and drivers.

## 2. Installation and files

No external packages are required to collect data. Open a terminal in the project folder. Check the Python installation with:

```cmd
python --version
```

To create the local configuration from the template, run this command in PowerShell:

```powershell
Copy-Item config.example.json config.json
```

Edit `config.json` with the device and campaign labels. This local file is excluded from Git.

Install Jupyter and `matplotlib` only if you want to run the analysis and generate charts. Project code includes:

* `wifi_scanner.py`: data collection, labeling, and capture storage.
* `wifi_survey_gui.py`: floor and map-position selection and Practice 2 capture control.
* `config.example.json`: template without personal identifiers.
* `validation/generate_chart.py`: chart generation from the data.
* `validation/analisis_practica2.ipynb`: notebook for Practice 2 capture analysis.
* `validation/practica2_analysis.py` and `validation/map_measurements.py`: notebook and map-viewer helpers.
* `tests/test_practica2_analysis.py`: tests for analysis and dataset paths.

`.gitignore` excludes local configuration, JSONL captures, the technical report, and generated charts. The original floor plans `FIC - P0.png` to `FIC - P4.png` and `ap_list_up_*.csv` are Moodle course materials; they do not need to be copied into the repository. The GUI lets you select a local plan. The collector creates `data/` when it runs.

## 3. Configuration

The collector loads `config.json` at startup. The example configuration uses these fields:

* `device_id`: identifier for the measurement device.
* `default_campaign`: campaign identifier.
* `building` and `floor`: building and floor.
* `default_interval`: requested interval between captures, in seconds.
* `default_samples`: number of captures per run.
* `measurement_procedure` and `measurement_incidents`: optional procedure and incident notes copied into captures for a run.
* `coordinate_reference`: plan identifier, local image, axis reference, and units. For pixel coordinates, the recommended convention is top-left origin, X to the right, and Y down.
* `access_points`: manually surveyed positions for APs to analyze. Each entry uses `bssid` (MAC address), `x`, `y`, and `units`, with optional `plan_id`, `label`, and `meters_per_unit`. Do not use coordinates from a different plan.

The `--room`, `--orientation`, `--interval`, and `--samples` options let you set these values for an individual run. Use `--point-id`, `--x`, and `--y` to locate captures; both coordinates must be supplied together and use the `coordinate_reference` units. `--procedure` records the run's procedure, and repeatable `--incident` options record incidents. The interval is the requested wait between captures; it does not by itself guarantee the actual time between timestamps.

## 4. Data collection

### Graphical point selection

To select a floor and mark a position directly on its plan, run:

```cmd
python wifi_survey_gui.py
```

Select a floor, load its image if it does not appear automatically, and click your position. The image is shown at its original size: the origin is the top-left corner, X increases to the right, Y increases down, and coordinates are stored as pixels in that image. Use the scrollbars to reach any area. Enter the point identifier, orientation, and number of captures, then select **Iniciar capturas** to open the collector in a separate terminal. The GUI writes Practice 2 captures to `data/practica2/screenshots.jsonl`; enabling all-network scans writes to `data/practica2/screenshots_all.jsonl` and requires a minimum interval of 5 seconds. The Practice 1 files `data/screenshots.jsonl` and `data/screenshots_all.jsonl` are not modified. Stop collection with `Ctrl+C` in that terminal.

The interface shows yellow markers for measured positions on the map; the number indicates how many captures were taken there. Click near a marker to view its network table; if it is within 24 pixels, the selection snaps to the nearest measured position. **Recargar datos** only rereads the dataset. To repeat measurements at the same location, select **Medir de nuevo aquí**. To measure a different location, click an empty area of the plan: the interface suggests a new point identifier, which you can edit, then select **Iniciar capturas en posición seleccionada**. The marker and table refresh automatically when capture finishes. If capture is cancelled before a sample is saved, the provisional selection is cleared and no measured point is shown. RSSI and Rx/Tx rates are shown only for the connected AP; Windows does not provide those rates for neighboring networks.

The interface records the building, floor, plan identifier and selected plan path with each sample, together with the marked position. The path identifies the image used on this computer; when sharing the project, download the `FIC - P0.png` to `FIC - P4.png` plans from Moodle, select the required image with **Cargar plano...**, and optionally place it beside `wifi_scanner.py` for automatic discovery. The Practice 2 notebook reads JSONL files from `data/practica2/`.

### Active connection

To start the collector with the default values, run:

```cmd
python wifi_scanner.py
```

To specify labels and the capture interval directly, for example, run:

```cmd
python wifi_scanner.py --room "Test room" --orientation "0-North" --interval 3 --samples 10
```

This mode queries the active connection and saves only the connected access point to `data/screenshots.jsonl`. To locate captures on the plan, provide the point identifier and coordinates:

```cmd
python wifi_scanner.py --room "P1" --point-id "P1" --x 420 --y 318 --procedure "Laptop stationary at fixed height" --interval 3 --samples 10
```

Replace `420` and `318` with coordinates read from the selected plan; do not reuse these illustrative values. Each run gets a `session_id`, and each capture gets a `sample_index`. Captures are appended to the file; a new run does not delete earlier captures. Omitting coordinates remains supported, and the notebook reports them as missing.

### All visible networks

To request a new Windows scan and record the detected networks, add `--all`:

```cmd
python wifi_scanner.py --room "Test room" --orientation "0-North" --interval 5 --samples 10 --all
```

The `--all` mode saves its records separately to `data/screenshots_all.jsonl` for the default Practice 1 dataset. Its minimum interval is 5 seconds: if the value specified on the command line or in `config.json` is lower, the collector raises it to 5 seconds and reports this. The scan adds approximately 4 seconds per capture, so the actual time between captures will be longer than the configured interval. Check `timestamp_utc` to determine the observed interval.

The CLI preserves the Practice 1 paths by default. To explicitly select the Practice 2 dataset, use `--dataset practica2`; captures are saved under `data/practica2/`.

### Stopping

To stop data collection, press `Ctrl+C` in the terminal. Each record is written before waiting for the next capture, so measurements already saved are retained.

## 5. Data format

Both data files use JSON Lines (JSONL): each line is an independent JSON object. They can be opened in a text editor or processed by other programs.

Current records contain these main fields:

* `metadata`: `timestamp_utc`, `device_id`, `campaign`, `building`, `floor`, `room`, `orientation`, and `network_scope`.
* `metadata.session_id` and `metadata.sample_index`: identify the run and the order of each capture.
* `metadata.measurement_procedure` and `metadata.measurement_incidents`: optional procedure and incident notes.
* `metadata.position`: `point_id`, `plan_id`, plan image, origin, axes, coordinate system, units, uncertainty, calibration, and, when supplied, `x` and `y` coordinates. Historical captures do not have this field.
* `active_interface`: connection status, SSID, BSSID/MAC address, signal percentage, RSSI in dBm, channel, band, radio type, and receive and transmit rates when provided by Windows. If querying the interface fails, this field may contain `error` instead.
* `visible_networks`: detected SSIDs and their BSSID/MAC addresses, signal percentage, channel, and radio type. In the default mode, this contains the active access point; with `--all`, it contains the visible networks from the scan.
* `network_scan`: status of the scan requested in `--all` mode and, if an error occurs, its message.

`network_scan.status` can have these values:

* `not_requested`: default mode; no visible-network scan was requested.
* `success`: the scan and query completed successfully. An empty `visible_networks` list means no networks were detected.
* `error`: Windows could not start the scan or the network query failed. The message is saved in `network_scan.message`; the empty list must not be interpreted as a valid measurement showing no networks.

Unavailable values are omitted from the JSON, not replaced with zero. `signal_percent` is a Windows percentage estimate, not a measurement in dBm. RSSI in dBm is for the active connection. BSSIDs are stored as their unhashed MAC addresses so they can be matched directly to access points surveyed on the floor plan. SSIDs are retained as reported by Windows. Historical captures with a `bssid_hash` field remain readable in analyses, but cannot be automatically matched to new MAC addresses.

Historical samples may not include every key in the current schema. In the data reviewed on October 4, 2026, all 59 records in `screenshots.jsonl` predate the addition of `network_scope` and `network_scan`. The initial 10 records in `screenshots_all.jsonl` include `network_scope`, but predate `network_scan`. New records include both fields.

## 6. Charts and validation

### Practice 02 analysis

The [`validation/analisis_practica2.ipynb`](validation/analisis_practica2.ipynb) notebook reads both JSONL files and produces an AP summary for one point, a signal-versus-distance chart, and a plot of measured positions on the floor plan. Install Jupyter and Matplotlib if needed:

```cmd
python -m pip install jupyter matplotlib
```

Open the notebook from Jupyter started in the project folder. It automatically reads `data/practica2/screenshots.jsonl` and `data/practica2/screenshots_all.jsonl`; it does not query the WiFi network. Original Moodle floor plans (`FIC - P0.png` to `FIC - P4.png`) are selected in the GUI and kept locally.

Before running it, complete `coordinate_reference` in the local `config.json` with the plan, origin, axes, units, and `meters_per_unit` only if the plan has been calibrated. Add each AP's surveyed position to `access_points` using its capture `bssid` MAC address. Keep the plan image at the configured local path. Set `TARGET_POINT_ID` and `TARGET_BSSID` in the notebook to choose the analysis; when left as `None`, the most represented point and AP are selected.

Example AP entry (replace these values with surveyed data; the coordinates are illustrative, not real measurements):

```json
{
  "label": "AP1",
  "bssid": "00:11:22:33:44:55",
  "plan_id": "example-plan",
  "x": 500,
  "y": 300,
  "units": "px"
}
```

Distance is calculated only when an AP and capture have numeric coordinates on the same plan. Without plan calibration, distance is labeled in the plan's native units (for example, pixels), not meters. The chart and map do not mix RSSI in dBm with percentage quality, fill missing values, or interpolate unmeasured areas. Historical records without coordinates remain in the data files but are not plotted.

To generate a chart of the active connection's RSSI and receive rate, run:

```cmd
python validation/generate_chart.py
```

To chart the signal percentage for all BSSIDs in the `--all` file, run:

```cmd
python validation/generate_chart.py --all
```

To chart Practice 2 captures and focus on one AP, use its `bssid` MAC address (available in `data/practica2/screenshots_all.jsonl`):

```cmd
python validation/generate_chart.py --all --data-dir data/practica2 --bssid 00:11:22:33:44:55
```

The chart shows that BSSID's signal percentage by capture index. To filter by SSID instead:

```cmd
python validation/generate_chart.py --all --data-dir data/practica2 --ssid "SSID_NAME"
```

These charts help compare captures/repetitions. They are not signal-versus-distance charts: that analysis and the floor-plan plot also require captures at multiple points, the AP's surveyed position, and a calibrated plan configured in `config.json`. `data/practica2` is the Practice 2 dataset; without `--data-dir`, the script preserves its previous behavior and reads `data`.

You can filter the chart by the exact SSID name:

```cmd
python validation/generate_chart.py --all --ssid "Example_SSID"
```

Charts are saved as `validation/validation_chart.png`, `validation/validation_chart_all.png`, and, when filtering, `validation/validation_chart_all_<SSID>.png`. Missing values are shown as gaps, not invented values.

The validation floor plan is kept locally in `validation/floorplan.png` and excluded from the repository because it shows the layout of the home.

Captures and experimental results are kept locally in the JSONL files; they are not included in the public repository because they contain network identifiers and location labels.

To manually compare fields with Windows, run the system queries in a terminal:

```cmd
netsh wlan show interfaces
netsh wlan show networks mode=bssid
```

Record the observed values and the time of the check, then include the comparison in the technical report. The queries are not simultaneous with the application capture; account for this time difference when interpreting the results.

## 7. Limitations and troubleshooting

SSID values are kept unmodified, as are the locations defined in `config.json`. Review this information before publishing the repository or sharing the data.

* The collector is designed for Windows and depends on `netsh` and the native WLAN API.
* The number of visible networks depends on the adapter, drivers, permissions, and environmental conditions. A scan may return fewer networks than the Windows graphical interface.
* If `network_scan.status` is `error`, check that the WiFi interface is enabled, Windows location services are active, and the terminal has the required permissions. The error message is retained in the JSONL file.
* If the scan completes with `success` and `visible_networks` is empty, no networks were detected by that query; this is different from an error.
* The actual interval may exceed the requested interval due to collection time, especially in `--all` mode. Use the timestamps to calculate it.
* Locations and orientations are entered manually; the tool does not obtain GPS coordinates or generate maps.
