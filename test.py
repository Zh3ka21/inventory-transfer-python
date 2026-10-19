from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

script = r'''#!/usr/bin/env python3'''


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
CONCURRENCY = int(os.environ.get("TEST_CONCURRENCY", "20"))
TRANSFER_COUNT = int(os.environ.get("TEST_TRANSFER_COUNT", "100"))
REQUEST_TIMEOUT = float(os.environ.get("TEST_TIMEOUT", "8"))
POOL_MAX_EXPECTED = 5


class ErrorTestFailure(Exception):
    """Raised when a regression check fails."""


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = REQUEST_TIMEOUT,
) -> tuple[int, Any, float]:
    """Send an HTTP request and return (status, parsed body, elapsed seconds)."""
    data = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    started = time.monotonic()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:
        raise ErrorTestFailure(f"{method} {path} failed: {exc}") from exc

    elapsed = time.monotonic() - started
    try:
        parsed: Any = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = body

    return status, parsed, elapsed


def require(condition: bool, message: str) -> None:
    """Fail the current test if condition is false."""
    if not condition:
        raise ErrorTestFailure(message)


def get_inventory(sku: str) -> dict[str, Any]:
    status, body, _ = request("GET", f"/api/inventory/{sku}")
    require(
        status == 200,
        f"Inventory GET for {sku} returned HTTP {status}: {body}",
    )
    require(
        isinstance(body, dict),
        f"Inventory response for {sku} was not a JSON object: {body}",
    )
    require("total" in body, f"Inventory response for {sku} has no 'total': {body}")
    return body


def get_pool() -> dict[str, Any]:
    status, body, _ = request("GET", "/api/health")
    require(status == 200, f"Health endpoint returned HTTP {status}: {body}")
    require(isinstance(body, dict), f"Health response was not a JSON object: {body}")

    pool = body.get("pool")
    require(isinstance(pool, dict), f"Health response has no pool object: {body}")
    for field in ("max", "active", "idle", "waiting"):
        require(field in pool, f"Pool metrics missing '{field}': {pool}")

    return pool


def transfer_payload(from_location: str, to_location: str) -> dict[str, Any]:
    return {
        "sku": "SKU-001",
        "fromLocation": from_location,
        "toLocation": to_location,
        "quantity": 10,
    }


def test_concurrent_transfers_preserve_total() -> None:
    print("\n[1/3] Concurrent transfers preserve inventory total")
    before_total = get_inventory("SKU-001")["total"]
    require(
        isinstance(before_total, (int, float)) and not isinstance(before_total, bool),
        f"Invalid initial inventory total: {before_total!r}",
    )

    jobs = [
        transfer_payload(
            "WAREHOUSE-A" if i % 2 == 0 else "WAREHOUSE-B",
            "WAREHOUSE-B" if i % 2 == 0 else "WAREHOUSE-A",
        )
        for i in range(TRANSFER_COUNT)
    ]

    def send(payload: dict[str, Any]) -> tuple[int, Any, float]:
        return request("POST", "/api/transfer", payload)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=CONCURRENCY
    ) as executor:
        results = list(executor.map(send, jobs))

    status_counts: dict[int, int] = {}
    failures = []
    for index, (status, body, elapsed) in enumerate(results, start=1):
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != 200:
            failures.append(
                f"request {index}: HTTP {status}, body={body}, {elapsed:.3f}s"
            )

    after_total = get_inventory("SKU-001")["total"]
    print(f"  HTTP statuses: {status_counts}")
    print(f"  SKU-001 total before={before_total}, after={after_total}")

    require(
        not failures,
        "Some concurrent transfers failed: " + "; ".join(failures[:5]),
    )
    require(
        after_total == before_total,
        f"Inventory total changed during transfers: {before_total} -> {after_total}",
    )
    print("  PASS: every transfer succeeded and total inventory was preserved.")


def test_invalid_requests_do_not_leak_connections() -> None:
    print("\n[2/3] Invalid transfers do not exhaust the connection pool")

    invalid_payloads = [
        {
            "sku": "SKU-DOES-NOT-EXIST",
            "fromLocation": "WAREHOUSE-A",
            "toLocation": "WAREHOUSE-B",
            "quantity": 1,
        },
        {
            "sku": "SKU-001",
            "fromLocation": "WAREHOUSE-NOT-REAL",
            "toLocation": "WAREHOUSE-B",
            "quantity": 1,
        },
        {
            "sku": "SKU-001",
            "fromLocation": "WAREHOUSE-A",
            "toLocation": "WAREHOUSE-B",
            "quantity": 0,
        },
        {
            "sku": "SKU-001",
            "fromLocation": "WAREHOUSE-A",
            "toLocation": "WAREHOUSE-B",
            "quantity": -1,
        },
    ]
    payloads = [invalid_payloads[i % len(invalid_payloads)] for i in range(10)]

    def send_invalid(payload: dict[str, Any]) -> tuple[int, Any, float]:
        return request(
            "POST",
            "/api/transfer",
            payload,
            timeout=REQUEST_TIMEOUT + 2,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(send_invalid, payloads))

    status_counts: dict[int, int] = {}
    unexpected = []
    for index, (status, body, elapsed) in enumerate(results, start=1):
        status_counts[status] = status_counts.get(status, 0) + 1
        if status not in (400, 404):
            unexpected.append(
                f"request {index}: HTTP {status}, body={body}, {elapsed:.3f}s"
            )

    print(f"  HTTP statuses: {status_counts}")
    require(
        not unexpected,
        "Invalid requests returned unexpected statuses: "
        + "; ".join(unexpected[:5]),
    )

    # Pool metrics may update just after requests complete.
    pool = get_pool()
    deadline = time.monotonic() + 3
    while (
        (pool["active"] != 0 or pool["waiting"] != 0)
        and time.monotonic() < deadline
    ):
        time.sleep(0.2)
        pool = get_pool()

    print(f"  Pool after invalid requests: {pool}")
    require(pool["active"] == 0, f"Pool still has active connections: {pool}")
    require(pool["waiting"] == 0, f"Requests still waiting for connections: {pool}")
    require(
        pool["max"] == POOL_MAX_EXPECTED,
        f"Expected documented pool max {POOL_MAX_EXPECTED}, got {pool['max']}",
    )
    print("  PASS: invalid requests returned client errors and the pool recovered.")


def test_service_still_accepts_valid_transfer() -> None:
    print("\n[3/3] Service remains usable after invalid requests")
    before_total = get_inventory("SKU-001")["total"]

    status, body, elapsed = request(
        "POST",
        "/api/transfer",
        transfer_payload("WAREHOUSE-A", "WAREHOUSE-B"),
    )
    print(f"  Valid transfer: HTTP {status} in {elapsed:.3f}s")
    require(
        status == 200,
        f"Valid transfer failed after invalid requests: HTTP {status}: {body}",
    )

    after_total = get_inventory("SKU-001")["total"]
    require(
        after_total == before_total,
        f"Valid transfer changed total inventory unexpectedly: "
        f"{before_total} -> {after_total}",
    )
    print("  PASS: valid transfer succeeded and total inventory remained unchanged.")


def main() -> int:
    if CONCURRENCY < 1:
        print("TEST_CONCURRENCY must be at least 1.", file=sys.stderr)
        return 2
    if TRANSFER_COUNT < 1:
        print("TEST_TRANSFER_COUNT must be at least 1.", file=sys.stderr)
        return 2
    if REQUEST_TIMEOUT <= 0:
        print("TEST_TIMEOUT must be greater than 0.", file=sys.stderr)
        return 2

    print(f"Inventory transfer regression checks: {BASE_URL}")
    try:
        status, body, _ = request("GET", "/api/health")
        require(status == 200, f"Service health check failed: HTTP {status}: {body}")
        print(f"Health check: {body}")

        test_concurrent_transfers_preserve_total()
        test_invalid_requests_do_not_leak_connections()
        test_service_still_accepts_valid_transfer()
    except ErrorTestFailure as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        print(
            "A failure may indicate a regression, an incompatible API response, "
            "or an incorrectly seeded test database. Investigate before claiming "
            "the fix is verified.",
            file=sys.stderr,
        )
        return 1

    print("\nALL REGRESSION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

