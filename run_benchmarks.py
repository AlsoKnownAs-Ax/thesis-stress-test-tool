import argparse
import os
import subprocess
import sys
import time

from settings import WORKLOADS

WORKLOAD_VARIANTS = ["unary", "stream", "stream_ndjson"]
USER_VARIANTS = [50, 125, 250]

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run all workloads for unary/stream/stream_ndjson at user variants."
        )
    )
    parser.add_argument(
        "--host",
        default=os.getenv("BENCHMARK_HOST", "http://localhost:8000"),
        help="Target host for Locust requests.",
    )
    parser.add_argument(
        "--locustfile",
        default="locustfile.py",
        help="Locust file to execute.",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=30,
        help="Cooldown between runs in seconds.",
    )
    parser.add_argument(
        "--run-time",
        default="5m",
        help="Run time for each test (e.g. 5m).",
    )
    parser.add_argument(
        "--start-run",
        default=None,
        help="Start at this workload (e.g. easy, medium, hard).",
    )
    parser.add_argument(
        "--skip-variant",
        default=None,
        help="Skip a benchmark variant (e.g. unary, stream, stream_ndjson).",
    )
    args = parser.parse_args()

    workloads = list(WORKLOADS.keys())
    if not workloads:
        raise SystemExit("No workloads defined in settings.WORKLOADS.")

    if args.start_run:
        if args.start_run not in workloads:
            valid = ", ".join(workloads)
            raise SystemExit(f"Unknown start-run '{args.start_run}'. Valid: {valid}.")
        start_index = workloads.index(args.start_run)
        workloads = workloads[start_index:]

    variants = WORKLOAD_VARIANTS
    if args.skip_variant:
        if args.skip_variant not in WORKLOAD_VARIANTS:
            valid = ", ".join(WORKLOAD_VARIANTS)
            raise SystemExit(
                f"Unknown skip-variant '{args.skip_variant}'. Valid: {valid}."
            )
        variants = [
            variant for variant in WORKLOAD_VARIANTS if variant != args.skip_variant
        ]

    total_runs = len(workloads) * len(variants) * len(USER_VARIANTS)
    run_index = 0

    for workload in workloads:
        for variant in variants:
            for users in USER_VARIANTS:
                run_index += 1
                env = os.environ.copy()
                env["BENCHMARK_WORKLOAD"] = workload
                env["BENCHMARK_VARIANT"] = variant

                command = [
                    sys.executable,
                    "-m",
                    "locust",
                    "-f",
                    args.locustfile,
                    "--host",
                    args.host,
                    "--headless",
                    "-u",
                    str(users),
                    "-r",
                    "100",
                    "-t",
                    args.run_time,
                ]

                print(
                    f"Run {run_index}/{total_runs}: workload={workload}, "
                    f"variant={variant}, users={users}, run_time={args.run_time}"
                )
                try:
                    subprocess.run(command, check=True, env=env)
                except subprocess.CalledProcessError as exc:
                    print(f"Run failed with exit code {exc.returncode}.")
                    return exc.returncode

                if run_index < total_runs and args.cooldown_seconds > 0:
                    print(f"Cooldown {args.cooldown_seconds}s before next run...")
                    time.sleep(args.cooldown_seconds)

    print("All runs complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
