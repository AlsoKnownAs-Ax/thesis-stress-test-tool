from typing import Any, Dict, Optional

from settings import BENCHMARK_WORKLOAD, WORKLOADS


def get_workload_config() -> Dict[str, int]:
	if BENCHMARK_WORKLOAD not in WORKLOADS:
		raise ValueError(
			f"Unknown workload '{BENCHMARK_WORKLOAD}'. "
			f"Valid options: {', '.join(WORKLOADS.keys())}."
		)
	return WORKLOADS[BENCHMARK_WORKLOAD]


def detect_item_count(payload: Any) -> Optional[int]:
	if isinstance(payload, list):
		return len(payload)
	if isinstance(payload, dict):
		for key in ("items", "orders", "data", "results"):
			value = payload.get(key)
			if isinstance(value, list):
				return len(value)
		for key in ("item_count", "count"):
			value = payload.get(key)
			if isinstance(value, int):
				return value
	return None
