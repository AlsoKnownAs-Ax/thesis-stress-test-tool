import argparse
import csv
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

_CSV_FIELDS = [
	"timestamp",
	"container_id",
	"container_name",
	"cpu_percent",
	"mem_usage_bytes",
	"mem_limit_bytes",
	"mem_percent",
	"net_rx_bytes",
	"net_tx_bytes",
	"block_read_bytes",
	"block_write_bytes",
	"pids",
]

_UNIT_MULTIPLIERS = {
	"B": 1,
	"KB": 1000,
	"MB": 1000 ** 2,
	"GB": 1000 ** 3,
	"TB": 1000 ** 4,
	"KIB": 1024,
	"MIB": 1024 ** 2,
	"GIB": 1024 ** 3,
	"TIB": 1024 ** 4,
}


class _StopSignal(Exception):
	pass


def _timestamp() -> str:
	return datetime.now(timezone.utc).isoformat()


def _parse_percent(value: Optional[str]) -> Optional[float]:
	if not value:
		return None
	try:
		return float(value.replace("%", "").strip())
	except ValueError:
		return None


def _parse_bytes(value: Optional[str]) -> Optional[int]:
	if not value:
		return None
	clean = value.strip()
	if not clean:
		return None
	if clean.isdigit():
		return int(clean)

	number = ""
	unit = ""
	for char in clean:
		if char.isdigit() or char == ".":
			number += char
		else:
			unit += char

	if not number:
		return None
	unit = unit.strip().upper()
	unit = unit.replace("I", "I")
	multiplier = _UNIT_MULTIPLIERS.get(unit, 1)
	try:
		return int(float(number) * multiplier)
	except ValueError:
		return None


def _parse_pair(value: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
	if not value:
		return None, None
	parts = [part.strip() for part in value.split("/")]
	if len(parts) != 2:
		return None, None
	return _parse_bytes(parts[0]), _parse_bytes(parts[1])


def _fetch_docker_stats() -> Iterable[Dict[str, str]]:
	result = subprocess.run(
		["docker", "stats", "--no-stream", "--format", "{{json .}}"],
		capture_output=True,
		text=True,
	)
	if result.returncode != 0:
		raise RuntimeError(result.stderr.strip() or "docker stats failed")
	for line in result.stdout.splitlines():
		line = line.strip()
		if not line:
			continue
		try:
			yield json.loads(line)
		except json.JSONDecodeError:
			continue


def _matches_container(stats: Dict[str, str], targets: Optional[Set[str]]) -> bool:
	if not targets:
		return True
	container_id = (stats.get("Container") or "").lower()
	name = (stats.get("Name") or "").lower()
	for target in targets:
		if not target:
			continue
		if name == target or container_id.startswith(target):
			return True
	return False


def _write_stats_row(writer: csv.DictWriter, stats: Dict[str, str]) -> None:
	cpu_percent = _parse_percent(stats.get("CPUPerc"))
	mem_usage, mem_limit = _parse_pair(stats.get("MemUsage"))
	mem_percent = _parse_percent(stats.get("MemPerc"))
	net_rx, net_tx = _parse_pair(stats.get("NetIO"))
	block_read, block_write = _parse_pair(stats.get("BlockIO"))
	pids = stats.get("PIDs")
	try:
		pids_value = int(pids) if pids else None
	except ValueError:
		pids_value = None

	writer.writerow(
		{
			"timestamp": _timestamp(),
			"container_id": stats.get("Container", ""),
			"container_name": stats.get("Name", ""),
			"cpu_percent": cpu_percent if cpu_percent is not None else "",
			"mem_usage_bytes": mem_usage if mem_usage is not None else "",
			"mem_limit_bytes": mem_limit if mem_limit is not None else "",
			"mem_percent": mem_percent if mem_percent is not None else "",
			"net_rx_bytes": net_rx if net_rx is not None else "",
			"net_tx_bytes": net_tx if net_tx is not None else "",
			"block_read_bytes": block_read if block_read is not None else "",
			"block_write_bytes": block_write if block_write is not None else "",
			"pids": pids_value if pids_value is not None else "",
		}
	)


def _install_signal_handlers() -> None:
	def _handler(_signum, _frame) -> None:
		raise _StopSignal

	signal.signal(signal.SIGINT, _handler)
	signal.signal(signal.SIGTERM, _handler)


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Log docker stats to a CSV file for Locust benchmarking."
	)
	parser.add_argument("--output", required=True, help="Path to write CSV stats.")
	parser.add_argument(
		"--interval",
		type=float,
		default=1.0,
		help="Polling interval in seconds (default: 1.0).",
	)
	parser.add_argument(
		"--duration",
		type=float,
		default=0.0,
		help="Optional duration in seconds. 0 means run until interrupted.",
	)
	parser.add_argument(
		"--containers",
		default="",
		help="Comma-separated container names or ID prefixes to include.",
	)

	args = parser.parse_args()
	output_path = Path(args.output)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	targets = {
		target.strip().lower()
		for target in args.containers.split(",")
		if target.strip()
	}
	interval = max(args.interval, 0.1)

	_install_signal_handlers()
	start_time = time.monotonic()

	with output_path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
		writer.writeheader()
		while True:
			if args.duration and time.monotonic() - start_time >= args.duration:
				break
			try:
				for stats in _fetch_docker_stats():
					if _matches_container(stats, targets):
						_write_stats_row(writer, stats)
			except _StopSignal:
				break
			except Exception as exc:
				print(f"docker stats error: {exc}", file=sys.stderr)
			handle.flush()
			time.sleep(interval)

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
