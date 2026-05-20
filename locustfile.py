import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from gevent import sleep, spawn_later
from locust import HttpUser, between, events, task

from csv_metrics import CSV_FIELDS, SummaryRecorder, ensure_results_dir, initialize_csv
from csv_metrics import short_hash, timestamp
from docker_stats import load_docker_stats_summary
from settings import (
	AUTO_DOCKER_STATS,
	BENCHMARK_VARIANT,
	BENCHMARK_WORKLOAD,
	DOCKER_STATS_PATH,
	DOCKER_STATS_CONTAINERS,
	DOCKER_STATS_INTERVAL_SECONDS,
	DOCKER_STATS_START_DELAY_SECONDS,
	ENDPOINT_STREAM,
	ENDPOINT_STREAM_NDJSON,
	ENDPOINT_UNARY,
	HOST,
	REQUEST_TIMEOUT_SECONDS,
	RESULTS_BASE_DIR,
	SAVE_CUSTOM_CSV,
	WARMUP_SECONDS,
	WORKLOADS,
)
from workloads import detect_item_count, get_workload_config

_summary_recorder = SummaryRecorder()
_docker_logger_process: Optional[subprocess.Popen] = None
_run_user_count: Optional[int] = None


def _start_docker_logger() -> None:
	global _docker_logger_process
	if not AUTO_DOCKER_STATS or not DOCKER_STATS_PATH:
		return
	if _docker_logger_process and _docker_logger_process.poll() is None:
		return
	script_path = Path(__file__).with_name("docker_stats_logger.py")
	command = [
		sys.executable,
		str(script_path),
		"--output",
		str(DOCKER_STATS_PATH),
		"--interval",
		str(DOCKER_STATS_INTERVAL_SECONDS),
	]
	if DOCKER_STATS_CONTAINERS.strip():
		command.extend(["--containers", DOCKER_STATS_CONTAINERS])
	_docker_logger_process = subprocess.Popen(command)


def _stop_docker_logger() -> None:
	global _docker_logger_process
	if not _docker_logger_process:
		return
	if _docker_logger_process.poll() is not None:
		_docker_logger_process = None
		return
	_docker_logger_process.terminate()
	try:
		_docker_logger_process.wait(timeout=5)
	except subprocess.TimeoutExpired:
		_docker_logger_process.kill()
	_docker_logger_process = None


@events.test_start.add_listener
def _(environment, **kwargs) -> None:
	global _run_user_count
	initialize_csv(SAVE_CUSTOM_CSV, RESULTS_BASE_DIR, BENCHMARK_WORKLOAD)
	if hasattr(environment, "runner") and environment.runner:
		_run_user_count = getattr(environment.runner, "target_user_count", None)
		if _run_user_count is None:
			_run_user_count = environment.runner.user_count
	_warmup_active = WARMUP_SECONDS > 0
	_summary_recorder.set_warmup_active(_warmup_active)
	if AUTO_DOCKER_STATS:
		start_delay = max(DOCKER_STATS_START_DELAY_SECONDS, 0.0)
		spawn_later(start_delay, _start_docker_logger)
	if not _warmup_active:
		return

	def _end_warmup() -> None:
		sleep(WARMUP_SECONDS)
		if hasattr(environment, "stats"):
			environment.stats.reset_all()
		# End warm-up so custom CSV starts with clean measurements.
		_summary_recorder.set_warmup_active(False)

	environment.runner.greenlet.spawn(_end_warmup)


@events.test_stop.add_listener
def _(environment, **kwargs) -> None:
	if not SAVE_CUSTOM_CSV:
		return
	_stop_docker_logger()
	initialize_csv(SAVE_CUSTOM_CSV, RESULTS_BASE_DIR, BENCHMARK_WORKLOAD)
	docker_summary = load_docker_stats_summary(DOCKER_STATS_PATH)
	summary_snapshot = _summary_recorder.snapshot()
	workload_dir = ensure_results_dir(RESULTS_BASE_DIR, BENCHMARK_WORKLOAD)
	output_path = workload_dir / (
		f"{BENCHMARK_WORKLOAD}-{BENCHMARK_VARIANT}-{short_hash()}.csv"
	)
	with output_path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
		writer.writeheader()
		users = _run_user_count if _run_user_count is not None else ""
		for (name, method), stats_entry in environment.stats.entries.items():
			summary = summary_snapshot.get((method, name))
			if summary is None:
				summary = {
					"endpoint": name,
					"variant": BENCHMARK_VARIANT,
					"requests": stats_entry.num_requests,
					"failures": stats_entry.num_failures,
					"response_bytes": 0,
					"expected_items_sum": 0,
					"received_items_sum": 0,
					"received_items_count": 0,
					"received_items_mismatch_count": 0,
					"time_to_first_item_sum_ms": 0.0,
					"time_to_first_item_count": 0,
					"total_stream_time_sum_ms": 0.0,
					"total_stream_time_count": 0,
				}
			requests = stats_entry.num_requests
			failures = stats_entry.num_failures
			error_rate = (failures / requests) if requests else 0.0
			avg_bytes = summary["response_bytes"] / requests if requests else 0.0
			received_avg = (
				summary["received_items_sum"] / summary["received_items_count"]
				if summary["received_items_count"]
				else -1
			)
			time_to_first_item_avg = (
				summary["time_to_first_item_sum_ms"]
				/ summary["time_to_first_item_count"]
				if summary["time_to_first_item_count"]
				else ""
			)
			total_stream_time_avg = (
				summary["total_stream_time_sum_ms"]
				/ summary["total_stream_time_count"]
				if summary["total_stream_time_count"]
				else ""
			)
			writer.writerow(
				{
					"timestamp": timestamp(),
					"users": users,
					"workload": BENCHMARK_WORKLOAD,
					"variant": summary["variant"],
					"endpoint": summary["endpoint"],
					"method": method,
					"requests": requests,
					"failures": failures,
					"error_rate": round(error_rate, 6),
					"time_to_first_byte_ms": round(stats_entry.avg_response_time, 3),
					"median_response_time_ms": round(stats_entry.median_response_time, 3),
					"min_response_time_ms": stats_entry.min_response_time,
					"max_response_time_ms": stats_entry.max_response_time,
					"p90_response_time_ms": round(
						stats_entry.get_response_time_percentile(0.9), 3
					),
					"p95_response_time_ms": round(
						stats_entry.get_response_time_percentile(0.95), 3
					),
					"throughput_rps": round(stats_entry.total_rps, 3),
					"total_response_bytes": summary["response_bytes"],
					"avg_response_bytes": round(avg_bytes, 3),
					"expected_items_per_request": WORKLOADS[BENCHMARK_WORKLOAD][
						"item_count"
					],
					"received_items_avg": received_avg,
					"received_items_mismatch_count": summary[
						"received_items_mismatch_count"
					],
					"time_to_first_item_ms": time_to_first_item_avg,
					"total_stream_time_ms": total_stream_time_avg,
					"docker_cpu_avg_percent": docker_summary.get(
						"cpu_avg_percent", ""
					),
					"docker_cpu_max_percent": docker_summary.get(
						"cpu_max_percent", ""
					),
					"docker_mem_avg_mib": docker_summary.get(
						"mem_avg_mib", ""
					),
					"docker_mem_max_mib": docker_summary.get(
						"mem_max_mib", ""
					),
					"docker_net_rx_mib": docker_summary.get("net_rx_mib", ""),
					"docker_net_tx_mib": docker_summary.get("net_tx_mib", ""),
					"docker_samples": docker_summary.get("samples", ""),
				}
			)
	if DOCKER_STATS_PATH and DOCKER_STATS_PATH.exists():
		try:
			DOCKER_STATS_PATH.unlink()
		except OSError:
			pass


class BenchmarkUser(HttpUser):
	host = HOST
	wait_time = between(0.1, 0.3)

	def _request(self, endpoint: str, request_name: str, variant: str) -> None:
		workload = get_workload_config()
		params = {
			"itemCount": workload["item_count"],
			"payloadSizeBytes": workload["payload_size_bytes"],
		}

		error_message = ""
		json_parse_success = False
		received_item_count: Optional[int] = None
		time_to_first_item_ms: Optional[float] = None
		start_time = time.perf_counter()

		try:
			with self.client.get(
				endpoint,
				params=params,
				name=request_name,
				timeout=REQUEST_TIMEOUT_SECONDS,
				catch_response=True,
			) as response:
				status_code = response.status_code
				response_size_bytes = len(response.content or b"")
				success = 200 <= status_code < 300

				item_count_mismatch = False
				if success:
					try:
						payload = response.json()
						json_parse_success = True
						received_item_count = detect_item_count(payload)
					except Exception as exc:
						success = False
						error_message = f"json_parse_error: {exc.__class__.__name__}"
				else:
					error_message = f"http_{status_code}"

				expected_item_count = workload["item_count"]
				if json_parse_success and received_item_count is not None:
					if received_item_count > 0:
						time_to_first_item_ms = (
							time.perf_counter() - start_time
						) * 1000
					# Item count mismatches matter for thesis validity, so fail the request.
					if received_item_count != expected_item_count:
						item_count_mismatch = True
						success = False
						error_message = (
							f"item_count_mismatch: expected {expected_item_count} "
							f"got {received_item_count}"
						)

				if success:
					response.success()
				else:
					response.failure(error_message or "request_failed")

				_summary_recorder.record_summary(
					SAVE_CUSTOM_CSV,
					"GET",
					request_name,
					endpoint,
					variant,
					success,
					response_size_bytes,
					expected_item_count,
					received_item_count,
					item_count_mismatch,
					time_to_first_item_ms,
					None,
				)
		except Exception as exc:
			error_message = f"exception: {exc.__class__.__name__}"
			_summary_recorder.record_summary(
				SAVE_CUSTOM_CSV,
				"GET",
				request_name,
				endpoint,
				variant,
				False,
				0,
				workload["item_count"],
				None,
				False,
				None,
				None,
			)

	def _request_ndjson(self) -> None:
		workload = get_workload_config()
		params = {
			"itemCount": workload["item_count"],
			"payloadSizeBytes": workload["payload_size_bytes"],
		}
		start_time = time.perf_counter()
		error_message = ""
		received_item_count = 0
		bytes_received = 0
		item_count_mismatch = False
		time_to_first_item_ms: Optional[float] = None
		buffer = b""

		try:
			with self.client.get(
				ENDPOINT_STREAM_NDJSON,
				params=params,
				name="GET stream_ndjson",
				timeout=REQUEST_TIMEOUT_SECONDS,
				stream=True,
				catch_response=True,
			) as response:
				status_code = response.status_code
				success = 200 <= status_code < 300
				if not success:
					error_message = f"http_{status_code}"
				else:
					for chunk in response.iter_content(chunk_size=4096):
						if not chunk:
							continue
						bytes_received += len(chunk)
						buffer += chunk
						while b"\n" in buffer:
							line_bytes, buffer = buffer.split(b"\n", 1)
							line_bytes = line_bytes.rstrip(b"\r")
							if not line_bytes.strip():
								continue
							try:
								json.loads(line_bytes.decode("utf-8"))
								received_item_count += 1
								if time_to_first_item_ms is None:
									time_to_first_item_ms = (
										time.perf_counter() - start_time
									) * 1000
							except Exception as exc:
								success = False
								error_message = (
									f"json_parse_error: {exc.__class__.__name__}"
								)
								break
						if not success:
							break
					if success and buffer.strip():
						try:
							json.loads(buffer.decode("utf-8"))
							received_item_count += 1
							if time_to_first_item_ms is None:
								time_to_first_item_ms = (
									time.perf_counter() - start_time
								) * 1000
						except Exception as exc:
							success = False
							error_message = (
								f"json_parse_error: {exc.__class__.__name__}"
							)

					total_stream_time_ms = (time.perf_counter() - start_time) * 1000
				expected_item_count = workload["item_count"]
				if success and received_item_count != expected_item_count:
					item_count_mismatch = True
					success = False
					error_message = (
						f"item_count_mismatch: expected {expected_item_count} "
						f"got {received_item_count}"
					)

				if success:
					response.success()
				else:
					response.failure(error_message or "request_failed")

				_summary_recorder.record_summary(
					SAVE_CUSTOM_CSV,
					"GET",
					"GET stream_ndjson",
					ENDPOINT_STREAM_NDJSON,
					"stream_ndjson",
					success,
					bytes_received,
					expected_item_count,
					received_item_count if received_item_count > 0 else None,
					item_count_mismatch,
					time_to_first_item_ms,
					total_stream_time_ms,
				)
		except Exception as exc:
			error_message = f"exception: {exc.__class__.__name__}"
			_summary_recorder.record_summary(
				SAVE_CUSTOM_CSV,
				"GET",
				"GET stream_ndjson",
				ENDPOINT_STREAM_NDJSON,
				"stream_ndjson",
				False,
				0,
				workload["item_count"],
				None,
				False,
				None,
				None,
			)

	@task
	def benchmark(self) -> None:
		if BENCHMARK_VARIANT == "unary":
			self._request(ENDPOINT_UNARY, "GET unary", "unary")
		elif BENCHMARK_VARIANT == "stream":
			self._request(ENDPOINT_STREAM, "GET stream_aggregated", "stream")
		elif BENCHMARK_VARIANT == "stream_ndjson":
			self._request_ndjson()
		elif BENCHMARK_VARIANT == "mixed":
			# Mixed tests alternate between unary and aggregated stream.
			self._request(ENDPOINT_UNARY, "GET unary", "unary")
			self._request(ENDPOINT_STREAM, "GET stream_aggregated", "stream")
		else:
			raise ValueError(
				f"Unknown BENCHMARK_VARIANT '{BENCHMARK_VARIANT}'. "
				"Valid options: unary, stream, stream_ndjson, mixed."
			)
