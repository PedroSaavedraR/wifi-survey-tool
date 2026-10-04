# WiFi Coverage Survey Tool (Windows)

[English](README.md) | [Español](README.es.md)

A command-line tool for querying and recording the active WiFi connection and, optionally, visible networks. Each capture includes a timestamp and campaign and location labels for later analysis. Suggested repository name: `wifi-coverage-survey`.

## 1. Environment and requirements

* **Tested operating system:** Windows 11.
* **Test device:** Lenovo LOQ 15 with a MediaTek MT7921 WiFi adapter.
* **Interpreter:** Python 3.8 or later. The version verified on the test device is Python 3.14.6.
* **System utilities:** `netsh.exe` and the native Windows WLAN API.
* **Dependencies:** `wifi_scanner.py` uses the Python standard library. Install `matplotlib` to generate charts:

```cmd
python -m pip install matplotlib
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

Install `matplotlib` only if you want to generate charts. The files tracked in the repository are:

* `wifi_scanner.py`: data collection, labeling, and capture storage.
* `config.example.json`: template without personal identifiers.
* `validation/generate_chart.py`: chart generation from the data.

`.gitignore` excludes the local configuration, JSONL captures, technical report, images, and floor plan script, as they may contain SSIDs, locations, or details about the home. The collector creates `data/` when it runs.

## 3. Configuration

The collector loads `config.json` at startup. The example configuration uses these fields:

* `device_id`: identifier for the measurement device.
* `default_campaign`: campaign identifier.
* `building` and `floor`: building and floor.
* `default_interval`: requested interval between captures, in seconds.
* `default_samples`: number of captures per run.

The `--room`, `--orientation`, `--interval`, and `--samples` options let you set these values for an individual run. The interval is the requested wait between captures; it does not by itself guarantee the actual time between timestamps.

## 4. Data collection

### Active connection

To start the collector with the default values, run:

```cmd
python wifi_scanner.py
```

To specify labels and the capture interval directly, for example, run:

```cmd
python wifi_scanner.py --room "Test room" --orientation "0-North" --interval 3 --samples 10
```

This mode queries the active connection and saves only the connected access point to `data/screenshots.jsonl`. Captures are appended to the file; a new run does not delete earlier captures.

### All visible networks

To request a new Windows scan and record the detected networks, add `--all`:

```cmd
python wifi_scanner.py --room "Test room" --orientation "0-North" --interval 5 --samples 10 --all
```

The `--all` mode saves its records separately to `data/screenshots_all.jsonl`. Its minimum interval is 5 seconds: if the value specified on the command line or in `config.json` is lower, the collector raises it to 5 seconds and reports this. The scan adds approximately 4 seconds per capture, so the actual time between captures will be longer than the configured interval. Check `timestamp_utc` to determine the observed interval.

### Stopping

To stop data collection, press `Ctrl+C` in the terminal. Each record is written before waiting for the next capture, so measurements already saved are retained.

## 5. Data format

Both data files use JSON Lines (JSONL): each line is an independent JSON object. They can be opened in a text editor or processed by other programs.

Current records contain these main fields:

* `metadata`: `timestamp_utc`, `device_id`, `campaign`, `building`, `floor`, `room`, `orientation`, and `network_scope`.
* `active_interface`: connection status, SSID, pseudonymized BSSID, signal percentage, RSSI in dBm, channel, band, radio type, and receive and transmit rates when provided by Windows. If querying the interface fails, this field may contain `error` instead.
* `visible_networks`: detected SSIDs and their pseudonymized BSSIDs, signal percentage, channel, and radio type. In the default mode, this contains the active access point; with `--all`, it contains the visible networks from the scan.
* `network_scan`: status of the scan requested in `--all` mode and, if an error occurs, its message.

`network_scan.status` can have these values:

* `not_requested`: default mode; no visible-network scan was requested.
* `success`: the scan and query completed successfully. An empty `visible_networks` list means no networks were detected.
* `error`: Windows could not start the scan or the network query failed. The message is saved in `network_scan.message`; the empty list must not be interpreted as a valid measurement showing no networks.

Unavailable values are omitted from the JSON, not replaced with zero. `signal_percent` is a Windows percentage estimate, not a measurement in dBm. RSSI in dBm is for the active connection. BSSIDs are stored as the first 12 hexadecimal characters of a SHA-256 hash so access points can be distinguished between captures. SSIDs are retained as reported by Windows.

Historical samples may not include every key in the current schema. In the data reviewed on October 4, 2026, all 59 records in `screenshots.jsonl` predate the addition of `network_scope` and `network_scan`. The initial 10 records in `screenshots_all.jsonl` include `network_scope`, but predate `network_scan`. New records include both fields.

## 6. Charts and validation

To generate a chart of the active connection's RSSI and receive rate, run:

```cmd
python validation/generate_chart.py
```

To chart the signal percentage for all BSSIDs in the `--all` file, run:

```cmd
python validation/generate_chart.py --all
```

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
