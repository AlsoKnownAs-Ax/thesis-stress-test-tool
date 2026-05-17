import csv
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_float(value: Optional[str]) -> Optional[float]:
	if value is None:
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _safe_int(value: Optional[str]) -> Optional[int]:
	if value is None:
		return None
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return None


def load_docker_stats_summary(stats_path: Optional[Path]) -> Dict[str, Any]:
	if not stats_path or not stats_path.exists():
		return {}

	bytes_per_mib = 1024 * 1024

	per_timestamp: Dict[str, Dict[str, float]] = {}
	per_container: Dict[str, Dict[str, Optional[int]]] = {}

	with stats_path.open("r", newline="", encoding="utf-8") as handle:
		reader = csv.DictReader(handle)
		for row in reader:
			timestamp = row.get("timestamp")
			if not timestamp:
				continue

			cpu = _safe_float(row.get("cpu_percent"))
			mem_usage = _safe_int(row.get("mem_usage_bytes"))
			net_rx = _safe_int(row.get("net_rx_bytes"))
			net_tx = _safe_int(row.get("net_tx_bytes"))

			totals = per_timestamp.setdefault(timestamp, {"cpu": 0.0, "mem": 0.0})
			if cpu is not None:
				totals["cpu"] += cpu
			if mem_usage is not None:
				totals["mem"] += mem_usage

			container_key = (
				row.get("container_id")
				or row.get("container_name")
				or "unknown"
			)
			if net_rx is not None or net_tx is not None:
				container_entry = per_container.setdefault(
					container_key,
					{
						"rx_first": None,
						"rx_last": None,
						"tx_first": None,
						"tx_last": None,
					},
				)
				if net_rx is not None:
					if container_entry["rx_first"] is None:
						container_entry["rx_first"] = net_rx
					container_entry["rx_last"] = net_rx
				if net_tx is not None:
					if container_entry["tx_first"] is None:
						container_entry["tx_first"] = net_tx
					container_entry["tx_last"] = net_tx

	if not per_timestamp:
		return {}

	cpu_values = [value["cpu"] for value in per_timestamp.values()]
	mem_values = [value["mem"] for value in per_timestamp.values()]

	cpu_avg = sum(cpu_values) / len(cpu_values)
	cpu_max = max(cpu_values)
	mem_avg = sum(mem_values) / len(mem_values)
	mem_max = max(mem_values)

	net_rx_total = 0
	net_tx_total = 0
	for entry in per_container.values():
		if entry["rx_first"] is not None and entry["rx_last"] is not None:
			delta = entry["rx_last"] - entry["rx_first"]
			if delta > 0:
				net_rx_total += delta
		if entry["tx_first"] is not None and entry["tx_last"] is not None:
			delta = entry["tx_last"] - entry["tx_first"]
			if delta > 0:
				net_tx_total += delta

	return {
		"cpu_avg_percent": round(cpu_avg, 3),
		"cpu_max_percent": round(cpu_max, 3),
		"mem_avg_mib": round(mem_avg / bytes_per_mib, 3),
		"mem_max_mib": round(mem_max / bytes_per_mib, 3),
		"net_rx_mib": round(net_rx_total / bytes_per_mib, 3),
		"net_tx_mib": round(net_tx_total / bytes_per_mib, 3),
		"samples": len(per_timestamp),
	}
