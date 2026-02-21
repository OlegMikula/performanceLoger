"""
Process load monitoring (CPU, memory).
Writes statistics to CSV until stopped or for a given duration.
"""

import argparse
import csv
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psutil


def bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 2)


def find_processes_by_names(names: list[str]) -> list[psutil.Process]:
    """Return processes whose names match the given list (case-insensitive)."""
    names_lower = [n.strip().lower() for n in names if n.strip()]
    found = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() in names_lower:
                found.append(psutil.Process(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def sample_process(proc: psutil.Process) -> tuple[float, float] | None:
    """Return (memory_mb, cpu_percent) or None if process no longer exists.
    Call cpu_percent(interval=0) on all processes and sleep() before sampling."""
    try:
        mem = proc.memory_info().rss
        cpu = proc.cpu_percent(interval=0)
        return (bytes_to_mb(mem), cpu)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _print_summary(
    ram_by_process: dict[tuple[str, int], list[float]],
    cpu_by_process: dict[tuple[str, int], list[float]],
) -> None:
    """Print min, max, avg for RAM and CPU per (process_name, pid)."""
    if not ram_by_process and not cpu_by_process:
        return
    print("\n--- Summary ---")
    keys = sorted(set(ram_by_process) | set(cpu_by_process), key=lambda k: (k[0], k[1]))
    for name, pid in keys:
        rams = ram_by_process.get((name, pid), [])
        cpus = cpu_by_process.get((name, pid), [])
        parts = []
        if rams:
            parts.append(f"RAM min={min(rams):.2f} max={max(rams):.2f} avg={sum(rams)/len(rams):.2f} MB")
        if cpus:
            parts.append(f"CPU min={min(cpus):.2f} max={max(cpus):.2f} avg={sum(cpus)/len(cpus):.2f}%")
        if parts:
            print(f"  {name} (PID {pid}):  {'  |  '.join(parts)}")


def run_monitor(
    process_names: list[str],
    *,
    interval: float = 1.0,
    duration_seconds: float | None = None,
    output_path: Path,
    stop_requested: list[bool] | None = None,
) -> None:
    seen_pids: set[int] = set()
    start = time.perf_counter()
    ram_by_process: dict[tuple[str, int], list[float]] = defaultdict(list)
    cpu_by_process: dict[tuple[str, int], list[float]] = defaultdict(list)
    stop = stop_requested if stop_requested is not None else [False]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "pid", "process_name", "memory_mb", "cpu_percent", "status"])

        while True:
            if stop[0]:
                break
            if duration_seconds is not None and (time.perf_counter() - start) >= duration_seconds:
                print("\nDuration reached. Stopping.")
                break

            processes = find_processes_by_names(process_names)
            current_pids = {p.pid for p in processes}

            # If we had seen this PID before and it's gone now, process exited
            for pid in list(seen_pids):
                if pid not in current_pids:
                    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
                    writer.writerow([ts, pid, "", "", "", "exited"])
                    seen_pids.discard(pid)

            # Prime cpu_percent for accurate reading
            for proc in processes:
                try:
                    proc.cpu_percent(interval=0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            time.sleep(0.15 if interval >= 0.2 else interval / 2)

            for proc in processes:
                try:
                    name = proc.name()
                    pid = proc.pid
                    seen_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

                result = sample_process(proc)
                if result is None:
                    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
                    writer.writerow([ts, pid, name, "", "", "exited"])
                    seen_pids.discard(pid)
                    continue

                memory_mb, cpu_percent = result
                key = (name, pid)
                ram_by_process[key].append(memory_mb)
                cpu_by_process[key].append(cpu_percent)
                ts = datetime.now().isoformat(sep=" ", timespec="seconds")
                writer.writerow([ts, pid, name, memory_mb, f"{cpu_percent:.2f}", "running"])
                print(f"  {ts} | PID {pid} | {name} | RAM {memory_mb} MB | CPU {cpu_percent:.1f}%")

            f.flush()

            time.sleep(max(0.05, interval - 0.2))

    _print_summary(ram_by_process, cpu_by_process)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor process load (CPU, memory). Output to CSV."
    )
    parser.add_argument(
        "-p",
        "--processes",
        required=True,
        help="Comma-separated process names, e.g. chrome.exe,Code.exe",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=1.0,
        help="Sampling interval in seconds (default: 1)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help="Monitor for this many seconds; if omitted, run until Ctrl+C",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: performance_log_YYYYMMDD_HHMMSS.csv)",
    )

    args = parser.parse_args()
    names = [n.strip() for n in args.processes.split(",") if n.strip()]
    if not names:
        print("At least one process name is required via -p/--processes.", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or Path(
        f"performance_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    output_path = output_path.resolve()

    print(f"Monitoring processes: {', '.join(names)}")
    print(f"Interval: {args.interval} s. Output: {output_path}")
    if args.duration:
        print(f"Duration: {args.duration} s")
    else:
        print("Stop with Ctrl+C")
    print()

    stop_requested: list[bool] = [False]

    def on_sigint(*_):  # noqa: ANN002
        print("\nStopping monitor.")
        stop_requested[0] = True

    signal.signal(signal.SIGINT, on_sigint)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_sigint)

    run_monitor(
        names,
        interval=args.interval,
        duration_seconds=args.duration,
        output_path=output_path,
        stop_requested=stop_requested,
    )


if __name__ == "__main__":
    main()
