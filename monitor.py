"""
Process load monitoring (CPU, memory).
Writes statistics to CSV until stopped or for a given duration.
"""

import argparse
import csv
import signal
import sys
import time
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


def run_monitor(
    process_names: list[str],
    *,
    interval: float = 1.0,
    duration_seconds: float | None = None,
    output_path: Path,
) -> None:
    seen_pids: set[int] = set()
    start = time.perf_counter()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "pid", "process_name", "memory_mb", "cpu_percent", "status"])

        while True:
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
                ts = datetime.now().isoformat(sep=" ", timespec="seconds")
                writer.writerow([ts, pid, name, memory_mb, f"{cpu_percent:.2f}", "running"])
                print(f"  {ts} | PID {pid} | {name} | RAM {memory_mb} MB | CPU {cpu_percent:.1f}%")

            f.flush()

            time.sleep(max(0.05, interval - 0.2))


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

    def on_sigint(*_):  # noqa: ANN002
        print("\nStopping monitor.")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_sigint)

    run_monitor(
        names,
        interval=args.interval,
        duration_seconds=args.duration,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
