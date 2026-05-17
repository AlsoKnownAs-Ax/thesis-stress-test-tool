import secrets
import string
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CSV_FIELDS = [
	"timestamp",
	"workload",
	"variant",
	"endpoint",
	"method",
	"requests",
	"failures",
	"error_rate",
	"avg_response_time_ms",
	"median_response_time_ms",
	"min_response_time_ms",
	"max_response_time_ms",
	"p90_response_time_ms",
	"p95_response_time_ms",
	"throughput_rps",
	"total_response_bytes",
	"avg_response_bytes",
	"expected_items_per_request",
	"received_items_avg",
	"received_items_mismatch_count",
	"time_to_first_item_ms",
	"docker_cpu_avg_percent",
	"docker_cpu_max_percent",
	"docker_mem_avg_mib",
	"docker_mem_max_mib",
	"docker_net_rx_mib",
	"docker_net_tx_mib",
	"docker_samples",
]


class SummaryRecorder:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._summary_data: Dict[Tuple[str, str], Dict[str, Any]] = {}
		self._warmup_active = False

	def set_warmup_active(self, active: bool) -> None:
		self._warmup_active = active

	def record_summary(
		self,
		save_custom_csv: bool,
		method: str,
		request_name: str,
		endpoint: str,
		variant: str,
		success: bool,
		response_size_bytes: int,
		expected_item_count: int,
		received_item_count: Optional[int],
		item_count_mismatch: bool,
		time_to_first_item_ms: Optional[float],
	) -> None:
		if not save_custom_csv:
			return
		if self._warmup_active:
			return
		with self._lock:
			entry = self._summary_data.setdefault(
				(method, request_name),
				{
					"endpoint": endpoint,
					"variant": variant,
					"requests": 0,
					"failures": 0,
					"response_bytes": 0,
					"expected_items_sum": 0,
					"received_items_sum": 0,
					"received_items_count": 0,
					"received_items_mismatch_count": 0,
					"time_to_first_item_sum_ms": 0.0,
					"time_to_first_item_count": 0,
				},
			)
			entry["endpoint"] = endpoint
			entry["variant"] = variant
			entry["requests"] += 1
			if not success:
				entry["failures"] += 1
			entry["response_bytes"] += response_size_bytes
			entry["expected_items_sum"] += expected_item_count
			if received_item_count is not None:
				entry["received_items_sum"] += received_item_count
				entry["received_items_count"] += 1
			if item_count_mismatch:
				entry["received_items_mismatch_count"] += 1
			if time_to_first_item_ms is not None:
				entry["time_to_first_item_sum_ms"] += time_to_first_item_ms
				entry["time_to_first_item_count"] += 1

	def snapshot(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
		with self._lock:
			return dict(self._summary_data)


def ensure_results_dir(results_base_dir: Path, workload: str) -> Path:
	workload_dir = results_base_dir / workload
	workload_dir.mkdir(parents=True, exist_ok=True)
	return workload_dir


def initialize_csv(save_custom_csv: bool, results_base_dir: Path, workload: str) -> None:
	if not save_custom_csv:
		return
	ensure_results_dir(results_base_dir, workload)


def timestamp() -> str:
	return datetime.now(timezone.utc).isoformat()


def timestamp_for_filename() -> str:
	return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def short_hash(length: int = 4) -> str:
	letters = string.ascii_lowercase
	return "".join(secrets.choice(letters) for _ in range(length))
