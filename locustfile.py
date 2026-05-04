from __future__ import annotations

import csv
import math
import os
import random
import time
from datetime import datetime, timezone

from locust import between, events, task
from locust.contrib.fasthttp import FastHttpUser

WORKLOAD_PROFILE = "hard"

BASE_URL = os.getenv("TARGET_HOST", "http://localhost:8000")
ORDER_CREATE_PATH = "/api/gateway/order/create"
USER_CREATE_PATH = "/api/gateway/user/create"
VALID_WORKLOAD_PROFILES = {"easy", "medium", "hard", "all"}

if WORKLOAD_PROFILE not in VALID_WORKLOAD_PROFILES:
    raise ValueError(
        f"Invalid WORKLOAD_PROFILE={WORKLOAD_PROFILE!r}. Expected one of: easy, medium, hard, all."
    )

REQUEST_TIME_SAMPLE_SIZE = 10000
request_time_samples = []
response_codes = {}
request_count = 0
response_time_sum = 0.0
min_response_time = float("inf")
max_response_time = float("-inf")
start_time = time.time()


class GatewayUserBase(FastHttpUser):
    abstract = True
    host = BASE_URL

    def on_start(self):
        self.user_id = self.provision_user()
        self.order_ids = []

    def build_user_payload(self):
        unique_suffix = random.randint(100000, 999999)
        return {
            "email": f"stress.user.{unique_suffix}@example.com",
            "first_name": random.choice(["Alex", "Sam", "Jordan", "Taylor"]),
            "last_name": random.choice(["Lee", "Patel", "Smith", "Garcia"]),
        }

    def provision_user(self):
        payload = self.build_user_payload()
        response = self.client.post(USER_CREATE_PATH, json=payload, name=USER_CREATE_PATH)

        if response.status_code != 200:
            return None

        try:
            user_data = response.json()
        except ValueError:
            return None

        return user_data.get("id")

    def ensure_user_id(self):
        if not getattr(self, "user_id", None):
            self.user_id = self.provision_user()
        return self.user_id

    def build_order_payload(self, quantity_min=1, quantity_max=10):
        user_id = self.ensure_user_id()
        if not user_id:
            return None

        return {
            "user_id": user_id,
            "product_id": str(random.randint(1, 100)),
            "quantity": random.randint(quantity_min, quantity_max),
        }

    def send_order(self, payload, request_name=ORDER_CREATE_PATH):
        with self.client.post(ORDER_CREATE_PATH, json=payload, catch_response=True, name=request_name) as response:
            if response.status_code in (200, 412):
                response.success()
                if response.status_code == 200:
                    try:
                        order_data = response.json()
                        order_id = order_data.get("order_id")
                        if order_id is not None:
                            self.order_ids.append(order_id)
                    except ValueError:
                        pass
            else:
                response.failure(f"Unexpected status {response.status_code}")

    def send_invalid_order(self, payload, request_name):
        with self.client.post(ORDER_CREATE_PATH, json=payload, catch_response=True, name=request_name) as response:
            if response.status_code in (400, 422):
                response.success()
            else:
                response.failure(f"Unexpected status for invalid payload: {response.status_code}")


def profile_enabled(profile_name):
    return WORKLOAD_PROFILE in (profile_name, "all")


class EasyOrderUser(GatewayUserBase):
    abstract = not profile_enabled("easy")
    wait_time = between(2, 5)

    @task(6)
    def create_order(self):
        payload = self.build_order_payload()
        if not payload:
            return

        self.send_order(payload)

    @task(1)
    def create_order_with_higher_quantity(self):
        payload = self.build_order_payload(quantity_min=50, quantity_max=200)
        if not payload:
            return

        self.send_order(payload, request_name=f"{ORDER_CREATE_PATH} (high quantity)")

    @task(1)
    def create_invalid_order(self):
        payload = {
            "user_id": "",
            "product_id": "999",
            "quantity": -1,
        }

        self.send_invalid_order(payload, request_name=f"{ORDER_CREATE_PATH} (invalid)")

    @task(1)
    def refresh_user_record(self):
        user_id = self.provision_user()
        if user_id:
            self.user_id = user_id


class MediumOrderUser(GatewayUserBase):
    abstract = not profile_enabled("medium")
    wait_time = between(1, 3)

    @task(5)
    def create_order(self):
        payload = self.build_order_payload()
        if not payload:
            return

        self.send_order(payload)

    @task(2)
    def create_order_with_higher_quantity(self):
        payload = self.build_order_payload(quantity_min=50, quantity_max=200)
        if not payload:
            return

        self.send_order(payload, request_name=f"{ORDER_CREATE_PATH} (high quantity)")

    @task(1)
    def create_invalid_order(self):
        payload = {
            "user_id": "",
            "product_id": "999",
            "quantity": -1,
        }

        self.send_invalid_order(payload, request_name=f"{ORDER_CREATE_PATH} (invalid)")

    @task(1)
    def refresh_user_record(self):
        user_id = self.provision_user()
        if user_id:
            self.user_id = user_id


class HardOrderUser(GatewayUserBase):
    abstract = not profile_enabled("hard")
    wait_time = between(0.5, 1.5)

    @task(4)
    def rapid_create_orders(self):
        payload = self.build_order_payload(quantity_min=1, quantity_max=5)
        if not payload:
            return

        self.client.post(ORDER_CREATE_PATH, json=payload, name=ORDER_CREATE_PATH)

    @task(2)
    def create_order(self):
        payload = self.build_order_payload()
        if not payload:
            return

        self.send_order(payload)

    @task(2)
    def create_order_with_higher_quantity(self):
        payload = self.build_order_payload(quantity_min=100, quantity_max=300)
        if not payload:
            return

        self.send_order(payload, request_name=f"{ORDER_CREATE_PATH} (high quantity)")

    @task(2)
    def create_invalid_order(self):
        payload = {
            "user_id": "",
            "product_id": "999",
            "quantity": -1,
        }

        self.send_invalid_order(payload, request_name=f"{ORDER_CREATE_PATH} (invalid)")

    @task(1)
    def refresh_user_record(self):
        user_id = self.provision_user()
        if user_id:
            self.user_id = user_id


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    global request_count, response_time_sum, min_response_time, max_response_time

    request_count += 1
    response_time_sum += response_time
    if response_time < min_response_time:
        min_response_time = response_time
    if response_time > max_response_time:
        max_response_time = response_time

    if len(request_time_samples) < REQUEST_TIME_SAMPLE_SIZE:
        request_time_samples.append(response_time)
    else:
        replace_index = random.randint(0, request_count - 1)
        if replace_index < REQUEST_TIME_SAMPLE_SIZE:
            request_time_samples[replace_index] = response_time

    code = response.status_code if response is not None else "error"
    response_codes[code] = response_codes.get(code, 0) + 1


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global start_time, request_count, response_time_sum, min_response_time, max_response_time
    request_time_samples.clear()
    response_codes.clear()
    request_count = 0
    response_time_sum = 0.0
    min_response_time = float("inf")
    max_response_time = float("-inf")
    start_time = time.time()

    print("\n" + "=" * 60)
    print("Starting Thesis API Gateway stress test")
    print(f"Target: {BASE_URL}")
    print(f"Order endpoint: {ORDER_CREATE_PATH}")
    print(f"User endpoint: {USER_CREATE_PATH}")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    if request_count == 0:
        return

    elapsed = time.time() - start_time
    sorted_samples = sorted(request_time_samples)
    sample_count = len(sorted_samples)
    total_requests = request_count
    mean_response_time = response_time_sum / total_requests

    if sample_count == 0:
        median_response_time = 0.0
        p95_response_time = 0.0
        p99_response_time = 0.0
    elif sample_count % 2:
        median_response_time = sorted_samples[sample_count // 2]
        p95_index = min(sample_count - 1, max(0, math.ceil(sample_count * 0.95) - 1))
        p99_index = min(sample_count - 1, max(0, math.ceil(sample_count * 0.99) - 1))
        p95_response_time = sorted_samples[p95_index]
        p99_response_time = sorted_samples[p99_index]
    else:
        middle = sample_count // 2
        median_response_time = (sorted_samples[middle - 1] + sorted_samples[middle]) / 2
        p95_index = min(sample_count - 1, max(0, math.ceil(sample_count * 0.95) - 1))
        p99_index = min(sample_count - 1, max(0, math.ceil(sample_count * 0.99) - 1))
        p95_response_time = sorted_samples[p95_index]
        p99_response_time = sorted_samples[p99_index]
    requests_per_second = total_requests / elapsed if elapsed > 0 else 0

    print("\n" + "=" * 60)
    print("Stress test metrics summary")
    print("=" * 60)
    print(f"Total duration: {elapsed:.2f} seconds")
    print(f"Total requests: {total_requests}")
    print(f"Requests per second: {requests_per_second:.2f}")
    print("\nResponse time statistics (ms):")
    print(f"  Min: {min_response_time:.2f}")
    print(f"  Max: {max_response_time:.2f}")
    print(f"  Mean: {mean_response_time:.2f}")
    print(f"  Median: {median_response_time:.2f}")
    print(f"  P95: {p95_response_time:.2f}")
    print(f"  P99: {p99_response_time:.2f}")
    print("\nResponse codes:")
    for code, count in sorted(response_codes.items(), key=lambda item: str(item[0])):
        print(f"  {code}: {count}")
    print("=" * 60 + "\n")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_filename = f"stress_test_results_{timestamp}.csv"
    output_dir = os.path.join("results", WORKLOAD_PROFILE)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, csv_filename)

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Timestamp (UTC)", datetime.now(timezone.utc).isoformat()])
        writer.writerow(["Total Duration (seconds)", f"{elapsed:.2f}"])
        writer.writerow(["Total Requests", total_requests])
        writer.writerow(["Requests per Second", f"{requests_per_second:.2f}"])
        writer.writerow(["Min Response Time (ms)", f"{min_response_time:.2f}"])
        writer.writerow(["Max Response Time (ms)", f"{max_response_time:.2f}"])
        writer.writerow(["Mean Response Time (ms)", f"{mean_response_time:.2f}"])
        writer.writerow(["Median Response Time (ms)", f"{median_response_time:.2f}"])
        writer.writerow(["P95 Response Time (ms)", f"{p95_response_time:.2f}"])
        writer.writerow(["P99 Response Time (ms)", f"{p99_response_time:.2f}"])
        writer.writerow([])
        writer.writerow(["Status Code", "Count"])
        for code, count in sorted(response_codes.items(), key=lambda item: str(item[0])):
            writer.writerow([code, count])

    print(f"Results saved to: {output_path}")
