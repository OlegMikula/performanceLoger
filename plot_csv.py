"""
Build charts from performance log CSV files.
Single file: one chart with all processes.
Multiple files: comparison chart (each file in its own style/color).
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt


def load_csv(path: Path) -> list[dict]:
    """Load CSV and return list of rows (dicts). Only 'running' rows have numeric metrics."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["timestamp"] = row.get("timestamp", "").strip()
            row["pid"] = row.get("pid", "").strip()
            row["process_name"] = row.get("process_name", "").strip()
            row["memory_mb"] = row.get("memory_mb", "").strip()
            row["cpu_percent"] = row.get("cpu_percent", "").strip()
            row["status"] = row.get("status", "").strip()
            rows.append(row)
    return rows


def parse_series(rows: list[dict], metric: str) -> tuple[list[datetime], dict[tuple[str, str], list[float]]]:
    """
    Parse rows into relative seconds from first timestamp and per-(process_name, pid) values.
    metric: 'memory_mb' or 'cpu_percent'
    Returns (times as datetime for first row only, then we use relative seconds), series dict.
    Actually we need X as relative seconds for comparison. So return (relative_seconds_list, series_dict).
    """
    if not rows:
        return [], {}

    def parse_ts(s: str):
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None

    # Get all unique timestamps in order to build a common time axis
    times = []
    for r in rows:
        t = parse_ts(r["timestamp"])
        if t is not None:
            times.append(t)
    if not times:
        return [], {}
    t0 = min(times)
    rel_seconds = [(t - t0).total_seconds() for t in times]
    # Build unique (timestamp_str or index) -> relative_seconds
    ts_to_rel = {}
    for r in rows:
        t = parse_ts(r["timestamp"])
        if t is not None:
            ts_to_rel[r["timestamp"]] = (t - t0).total_seconds()

    # Per (process_name, pid): list of (rel_sec, value)
    series: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        if r["status"] != "running":
            continue
        key = (r["process_name"] or "?", r["pid"] or "?")
        rel = ts_to_rel.get(r["timestamp"])
        if rel is None:
            continue
        raw = r.get(metric, "").strip()
        try:
            val = float(raw)
        except ValueError:
            continue
        series[key].append((rel, val))

    # Sort each series by time and return as (x_list, y_list) per key - actually we return
    # series dict with list of (x, y) per key; then we have multiple series to plot.
    out = {}
    for key, points in series.items():
        points.sort(key=lambda p: p[0])
        if points:
            out[key] = ([p[0] for p in points], [p[1] for p in points])
    return out


def plot_single(
    csv_path: Path,
    metric: str,
    output_path: Path | None,
    title: str | None,
) -> None:
    rows = load_csv(csv_path)
    series = parse_series(rows, metric)
    if not series:
        print(f"No data to plot in {csv_path}")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    ylabel = "Memory (MB)" if metric == "memory_mb" else "CPU (%)"
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time from start (s)")
    ax.set_title(title or f"{csv_path.name} — {ylabel}")

    for (pname, pid), (xs, ys) in series.items():
        label = f"{pname} ({pid})"
        ax.plot(xs, ys, "-o", markersize=3, label=label, alpha=0.9)

    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {output_path}")
    else:
        plt.show()
    plt.close()


def plot_compare(
    csv_paths: list[Path],
    metric: str,
    output_path: Path | None,
    title: str | None,
) -> None:
    if len(csv_paths) < 2:
        print("Comparison mode requires at least 2 CSV files.")
        return

    fig, ax = plt.subplots(figsize=(11, 6))
    ylabel = "Memory (MB)" if metric == "memory_mb" else "CPU (%)"
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time from start (s)")
    ax.set_title(title or f"Comparison — {ylabel}")

    colors = plt.cm.tab10.colors
    styles = ["-", "--", "-.", ":"]
    file_colors = {p: colors[i % len(colors)] for i, p in enumerate(csv_paths)}
    file_styles = {p: styles[i % len(styles)] for i, p in enumerate(csv_paths)}

    for path in csv_paths:
        rows = load_csv(path)
        series = parse_series(rows, metric)
        c = file_colors[path]
        linestyle = file_styles[path]
        label_prefix = path.stem[:20] + ("..." if len(path.stem) > 20 else "")
        for (pname, pid), (xs, ys) in series.items():
            label = f"{label_prefix} — {pname} ({pid})"
            ax.plot(xs, ys, linestyle=linestyle, color=c, marker="o", markersize=2, label=label, alpha=0.85)
    ax.legend(loc="best", fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {output_path}")
    else:
        plt.show()
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot performance log CSV(s): single chart or comparison of multiple files."
    )
    parser.add_argument(
        "csv_files",
        nargs="+",
        type=Path,
        help="One or more CSV files from monitor.py",
    )
    parser.add_argument(
        "-m",
        "--metric",
        choices=["memory", "cpu", "both"],
        default="memory",
        help="Metric to plot: memory (MB), cpu (%%), or both in two subplots (default: memory)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output image path (e.g. chart.png). If omitted, display only.",
    )
    parser.add_argument(
        "-t",
        "--title",
        type=str,
        default=None,
        help="Chart title",
    )
    args = parser.parse_args()

    for p in args.csv_files:
        if not p.exists():
            parser.error(f"File not found: {p}")

    if args.metric == "both":
        # Two subplots: memory and cpu
        if len(args.csv_files) == 1:
            rows = load_csv(args.csv_files[0])
            s_mem = parse_series(rows, "memory_mb")
            s_cpu = parse_series(rows, "cpu_percent")
            if not s_mem and not s_cpu:
                print("No data to plot.")
                return
            fig, (ax_m, ax_c) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
            for (pname, pid), (xs, ys) in s_mem.items():
                ax_m.plot(xs, ys, "-o", markersize=3, label=f"{pname} ({pid})", alpha=0.9)
            ax_m.set_ylabel("Memory (MB)")
            ax_m.legend(loc="best", fontsize=8)
            ax_m.grid(True, alpha=0.3)
            for (pname, pid), (xs, ys) in s_cpu.items():
                ax_c.plot(xs, ys, "-o", markersize=3, label=f"{pname} ({pid})", alpha=0.9)
            ax_c.set_ylabel("CPU (%)")
            ax_c.set_xlabel("Time from start (s)")
            ax_c.legend(loc="best", fontsize=8)
            ax_c.grid(True, alpha=0.3)
            fig.suptitle(args.title or args.csv_files[0].name, y=1.02)
            fig.tight_layout()
            if args.output:
                fig.savefig(args.output, dpi=150, bbox_inches="tight")
                print(f"Saved: {args.output}")
            else:
                plt.show()
            plt.close()
        else:
            fig, (ax_m, ax_c) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)
            colors = plt.cm.tab10.colors
            styles = ["-", "--", "-.", ":"]
            for i, path in enumerate(args.csv_files):
                c, ls = colors[i % len(colors)], styles[i % len(styles)]
                prefix = path.stem[:18] + ("..." if len(path.stem) > 18 else "")
                rows = load_csv(path)
                for (pname, pid), (xs, ys) in parse_series(rows, "memory_mb").items():
                    ax_m.plot(xs, ys, linestyle=ls, color=c, marker="o", markersize=2, label=f"{prefix} — {pname} ({pid})", alpha=0.85)
                for (pname, pid), (xs, ys) in parse_series(rows, "cpu_percent").items():
                    ax_c.plot(xs, ys, linestyle=ls, color=c, marker="o", markersize=2, label=f"{prefix} — {pname} ({pid})", alpha=0.85)
            ax_m.set_ylabel("Memory (MB)")
            ax_m.legend(loc="best", fontsize=7)
            ax_m.grid(True, alpha=0.3)
            ax_c.set_ylabel("CPU (%)")
            ax_c.set_xlabel("Time from start (s)")
            ax_c.legend(loc="best", fontsize=7)
            ax_c.grid(True, alpha=0.3)
            fig.suptitle(args.title or "Comparison", y=1.02)
            fig.tight_layout()
            if args.output:
                fig.savefig(args.output, dpi=150, bbox_inches="tight")
                print(f"Saved: {args.output}")
            else:
                plt.show()
            plt.close()
        return

    metric_key = "memory_mb" if args.metric == "memory" else "cpu_percent"
    if len(args.csv_files) == 1:
        plot_single(args.csv_files[0], metric_key, args.output, args.title)
    else:
        plot_compare(args.csv_files, metric_key, args.output, args.title)


if __name__ == "__main__":
    main()
