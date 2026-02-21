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


def filter_series_by_pids(
    series: dict[tuple[str, str], tuple[list[float], list[float]]],
    pids: set[int] | None,
) -> dict[tuple[str, str], tuple[list[float], list[float]]]:
    """Keep only series whose PID is in pids. If pids is None, return series unchanged."""
    if pids is None or not pids:
        return series
    return {
        (name, pid): xy
        for (name, pid), xy in series.items()
        if pid.strip() and _pid_in_set(pid, pids)
    }


def _pid_in_set(pid_str: str, pids: set[int]) -> bool:
    try:
        return int(pid_str) in pids
    except ValueError:
        return False


def plot_single(
    csv_path: Path,
    metric: str,
    output_path: Path | None,
    title: str | None,
    pids: set[int] | None = None,
) -> None:
    rows = load_csv(csv_path)
    series = filter_series_by_pids(parse_series(rows, metric), pids)
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
    pids: set[int] | None = None,
    pids_per_file: list[set[int] | None] | None = None,
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

    for i, path in enumerate(csv_paths):
        rows = load_csv(path)
        file_pids = (pids_per_file[i] if pids_per_file else None) or pids
        series = filter_series_by_pids(parse_series(rows, metric), file_pids)
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
    parser.add_argument(
        "--pid",
        type=str,
        default=None,
        metavar="PIDS",
        help="PIDs to plot. One file: comma-separated (e.g. \"1111, 1112\"). Comparison: use \";\" to group by file (e.g. \"1111,1112;2221,2222\" for run1→1111,1112 and run2→2221,2222). Or one PID for all, or N single PIDs (one per file).",
    )
    args = parser.parse_args()

    for p in args.csv_files:
        if not p.exists():
            parser.error(f"File not found: {p}")

    def parse_pid_group(s: str) -> set[int]:
        out: set[int] = set()
        for x in s.split(","):
            x = x.strip()
            if x:
                try:
                    out.add(int(x))
                except ValueError:
                    raise ValueError(f"Invalid PID: {x!r}")
        return out

    nfiles = len(args.csv_files)
    pids: set[int] | None = None
    pids_per_file: list[set[int] | None] | None = None

    if args.pid:
        raw = args.pid.strip()
        if ";" in raw:
            groups = [g.strip() for g in raw.split(";")]
            if nfiles == 1:
                if len(groups) != 1:
                    parser.error("Single file: use comma-separated PIDs only (no \";\").")
                try:
                    pids = parse_pid_group(groups[0])
                except ValueError as e:
                    parser.error(f"Invalid --pid: {e}")
                if not pids:
                    parser.error("--pid must contain at least one integer.")
            else:
                if len(groups) != nfiles:
                    parser.error(
                        f"When using \";\" for per-file PIDs, provide {nfiles} groups (one per file), got {len(groups)}."
                    )
                try:
                    pids_per_file = [parse_pid_group(g) or None for g in groups]
                except ValueError as e:
                    parser.error(f"Invalid --pid: {e}")
                if all(not s for s in pids_per_file):
                    parser.error("--pid must contain at least one integer in some group.")
                pids = None
        else:
            try:
                pid_list = list(parse_pid_group(raw))
            except ValueError as e:
                parser.error(f"Invalid --pid: {e}")
            if not pid_list:
                parser.error("--pid must contain at least one integer.")
            if nfiles == 1:
                pids = set(pid_list)
            else:
                pids = set(pid_list)
                if len(pid_list) == 1:
                    pids_per_file = [set(pid_list)] * nfiles
                elif len(pid_list) == nfiles:
                    pids_per_file = [set([p]) for p in pid_list]
                else:
                    parser.error(
                        f"When comparing {nfiles} files without \";\", --pid must have 1 value (same for all) or {nfiles} values (one per file), got {len(pid_list)}."
                    )
    else:
        if nfiles > 1:
            pids_per_file = [None] * nfiles

    if args.metric == "both":
        # Two subplots: memory and cpu
        if len(args.csv_files) == 1:
            rows = load_csv(args.csv_files[0])
            s_mem = filter_series_by_pids(parse_series(rows, "memory_mb"), pids)
            s_cpu = filter_series_by_pids(parse_series(rows, "cpu_percent"), pids)
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
                file_pids = pids_per_file[i] if pids_per_file else None
                s_mem = filter_series_by_pids(parse_series(rows, "memory_mb"), file_pids)
                s_cpu = filter_series_by_pids(parse_series(rows, "cpu_percent"), file_pids)
                for (pname, pid), (xs, ys) in s_mem.items():
                    ax_m.plot(xs, ys, linestyle=ls, color=c, marker="o", markersize=2, label=f"{prefix} — {pname} ({pid})", alpha=0.85)
                for (pname, pid), (xs, ys) in s_cpu.items():
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
        plot_single(args.csv_files[0], metric_key, args.output, args.title, pids)
    else:
        plot_compare(
            args.csv_files,
            metric_key,
            args.output,
            args.title,
            pids=pids,
            pids_per_file=pids_per_file if nfiles > 1 else None,
        )


if __name__ == "__main__":
    main()
