import os
from pathlib import Path
from typing import Dict

HOST = os.getenv("BENCHMARK_HOST", "http://localhost:8000")
ENDPOINT_UNARY = "/api/gateway/benchmark/unary"
ENDPOINT_STREAM = "/api/gateway/benchmark/stream"
ENDPOINT_STREAM_NDJSON = "/api/gateway/benchmark/stream-ndjson"

WORKLOADS: Dict[str, Dict[str, int]] = {
	"easy": {"item_count": 10, "payload_size_bytes": 512}, # 0.0049 MiB
	"medium": {"item_count": 500, "payload_size_bytes": 4096}, # 1.9531 MiB
	"hard": {"item_count": 1000, "payload_size_bytes": 4096}, # 3.9062 MiB
}

BENCHMARK_WORKLOAD = os.getenv("BENCHMARK_WORKLOAD", "easy")
BENCHMARK_VARIANT = os.getenv("BENCHMARK_VARIANT", "unary")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
WARMUP_SECONDS = int(os.getenv("WARMUP_SECONDS", "60"))
SAVE_CUSTOM_CSV = os.getenv("SAVE_CUSTOM_CSV", "true").lower() not in {
	"0",
	"false",
	"no",
}
RESULTS_BASE_DIR = Path(os.getenv("RESULTS_BASE_DIR", "results"))

_DOCKER_STATS_PATH = os.getenv("DOCKER_STATS_PATH", "results/docker-stats.csv")
DOCKER_STATS_PATH = Path(_DOCKER_STATS_PATH) if _DOCKER_STATS_PATH else None

AUTO_DOCKER_STATS = os.getenv("AUTO_DOCKER_STATS", "true").lower() not in {
	"0",
	"false",
	"no",
}
DOCKER_STATS_INTERVAL_SECONDS = float(
	os.getenv("DOCKER_STATS_INTERVAL_SECONDS", "1.0")
)
DOCKER_STATS_START_DELAY_SECONDS = float(
	os.getenv("DOCKER_STATS_START_DELAY_SECONDS", str(WARMUP_SECONDS))
)
DOCKER_STATS_CONTAINERS = os.getenv("DOCKER_STATS_CONTAINERS", "")
