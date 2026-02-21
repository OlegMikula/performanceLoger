# Performance Logger — process load monitoring

Collects CPU and memory statistics for specified processes and writes them to CSV.

## Installation

```bash
pip install -r requirements.txt
```

---

## monitor.py — logging

### Usage

**Monitor until you stop (Ctrl+C):**
```bash
python monitor.py -p "chrome.exe,Code.exe"
```

**Monitor for 60 seconds:**
```bash
python monitor.py -p "chrome.exe" -d 60
```

**Sampling every 2 seconds, custom output file:**
```bash
python monitor.py -p "notepad.exe" -i 2 -o my_log.csv
```

**Wildcard process names** (e.g. all processes whose name starts with `GTB-`):
```bash
python monitor.py -p "GTB-*" -d 120 -o gtb_log.csv
```

### Arguments

| Argument | Description |
|----------|-------------|
| `-p`, `--processes` | Comma-separated process names (e.g. `chrome.exe`, `Code.exe`). Supports wildcards: `*` = any characters, `?` = one character (e.g. `GTB-*`). |
| `-i`, `--interval` | Sampling interval in seconds (default: 1). |
| `-d`, `--duration` | Run for this many seconds; if omitted, runs until Ctrl+C. |
| `-o`, `--output` | Output CSV path (default: `performance_log_YYYYMMDD_HHMMSS.csv`). |

### After run

When monitoring ends (by duration or Ctrl+C), a **summary** is printed: for each process (by unique PID), min / max / avg for RAM (MB) and CPU (%).

### CSV format

| Column | Description |
|--------|-------------|
| timestamp | Sample time |
| pid | Process ID (helps see when a process exited) |
| process_name | Process name |
| memory_mb | Memory in MB |
| cpu_percent | CPU usage in percent |
| status | `running` or `exited` |

---

## plot_csv.py — charts

Builds charts from performance log CSVs. Single file → one chart; multiple files → comparison chart (X axis = time from start).

### Usage

**Single file (all processes or filtered by PIDs):**
```bash
python plot_csv.py log.csv -o chart.png
python plot_csv.py log.csv --pid "23420, 21404" -o chart.png
```

**Comparison (multiple files):**
```bash
python plot_csv.py run1.csv run2.csv run3.csv -o compare.png
```

**One PID per file** (run1 → 1111, run2 → 2222):
```bash
python plot_csv.py run1.csv run2.csv --pid "1111, 2222" -o compare.png
```

**Multiple PIDs per file** — use `;` to group by file (run1: 1111,1112; run2: 2221,2222):
```bash
python plot_csv.py run1.csv run2.csv --pid "1111,1112;2221,2222" -o compare.png
```

**Metric:** `-m memory` (default), `-m cpu`, or `-m both` (two subplots: memory and CPU).

**Optional:** `-o path` saves the image; without `-o`, the chart opens in a window. `-t "Title"` sets the chart title.

### Arguments

| Argument | Description |
|----------|-------------|
| `csv_files` | One or more CSV files (from monitor.py). |
| `-m`, `--metric` | `memory` (default), `cpu`, or `both`. |
| `-o`, `--output` | Output image path (e.g. `chart.png`). If omitted, display only. |
| `-t`, `--title` | Chart title. |
| `--pid` | PIDs to plot. **Single file:** comma-separated (e.g. `"1111, 1112"`). **Comparison:** use `;` to group by file (e.g. `"1111,1112;2221,2222"` = run1→1111,1112 and run2→2221,2222). Or one PID for all files, or N single PIDs (one per file). |
