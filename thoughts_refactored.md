# Inventory Transfer Service: Investigation Notes

## Summary

I cloned and ran the inventory-transfer service, checked its initial inventory state, and used the provided scripts to reproduce two problems:

1. **Inventory inconsistency under concurrent transfers.** The burst test returned HTTP 200 for all 100 requests, but the total quantity for `SKU-001` decreased unexpectedly. Repeated runs produced different totals, suggesting a nondeterministic concurrency issue.
2. **Database connection pool exhaustion.** The leak test showed all five connections active, none idle, and additional requests timing out with HTTP 500 responses. The evidence pointed to connections not being returned on some early error paths.

I added a `try ... finally`-style connection cleanup fix and reran the leak test. The follow-up responses were fast and returned the expected 400/404 errors instead of 500s. I then investigated the inventory bug, but these notes do **not** yet record an implemented and verified fix for it.

## Environment Setup and Initial Checks

### 13:45–13:55 — Clone, start, and inspect the service

- Forked the repository and cloned it locally.
- Started building the Docker environment.
- Initially ran `dcup --build`, which failed with an interpolation error involving `${DB_PORT:-5432}:5432`. This was caused by using the wrong shortened command.
- Checked the API health endpoint at `/api/health` through the local API docs. It returned `UP`.
- Compared the inventory endpoints with the expected SKU data; the initial values matched.

### 14:10–14:13 — Fix the consistency-check setup

The first run of `scripts/consistency_check.sh` reported that it could not get answers from the inventory endpoints, even though the containers were running and the health endpoint was healthy.

I checked the container status, application logs, and health endpoint. The issue was that `jq`, which the script requires, was not installed. After installing it, the consistency check passed:

| SKU       | Total | Expected | Warehouse breakdown     |
| --------- | ----: | -------: | ----------------------- |
| `SKU-001` |  1800 |     1800 | A: 1000, B: 500, C: 300 |
| `SKU-002` |  3500 |     3500 | A: 2000, B: 1500        |
| `SKU-003` |   700 |      700 | A: 500, C: 200          |

## Bug 1: Inventory Inconsistency During Concurrent Transfers

### 14:15–14:20 — Reproduce the issue

I ran:

```bash
bash scripts/burst_test.sh
```

The script sent 100 transfers of 10 units of `SKU-001`, with 20 requests running concurrently. All 100 requests returned HTTP 200.

I then ran:

```bash
bash scripts/consistency_check.sh
```

The inventory total had changed from 1800 to 1700, even though the transfers should not change the total quantity of the SKU.

### 14:22–14:56 — Repeat the test and form a hypothesis

I repeated the burst test and consistency check several times. Every request continued to return HTTP 200, but the total quantity for `SKU-001` varied:

| Observed total | Expected total | Difference |
| -------------: | -------------: | ---------: |
|           1700 |           1800 |       -100 |
|           1700 |           1800 |       -100 |
|           1640 |           1800 |       -160 |
|           1550 |           1800 |       -250 |

The warehouse values also changed, while `SKU-002` and `SKU-003` remained unchanged.

At first, I wondered whether stock was disappearing at a fixed rate. Repeated runs showed that the amount lost was nondeterministic. The likely cause is a **lost update caused by overlapping read-modify-write operations**, but the notes here do not include a complete code-level confirmation.

The main concern is that the service reports success even when inventory consistency has been broken. Ordinary checks that only assert HTTP 200 responses would miss this; the inventory consistency script exposed the problem.

### 15:43 onward — Investigate a concurrency fix

I discussed the likely fix and corrected my understanding of how locking should work:

- Do not globally order or serialize all requests. Instead, acquire the relevant inventory-row locks in a consistent order, such as alphabetical warehouse order, to reduce deadlock risk while allowing unrelated transfers to run concurrently.
- Use a locking read such as `SELECT ... FOR UPDATE`. A plain `SELECT` does not prevent another transaction from changing the same row.
- Keep the locks held for the transaction while validating stock and applying the transfer.
- Apply each quantity change to the database value protected by the lock, rather than writing a value calculated from an earlier, potentially stale read.
- Ensure the debit and credit happen in one transaction so a failed transfer cannot leave only one side applied.

**Status:** Root cause is a strong hypothesis, not fully confirmed in these notes. An implementation and reproducible verification of this fix are still outstanding.

## Bug 2: Database Connection Pool Exhaustion

### 15:10 — Reproduce the connection leak

The leak test showed the connection pool reaching its limit:

```json
{ "max": 5, "total": 5, "active": 5, "idle": 0, "waiting": 5 }
```

The first five requests returned expected 400 or 404 responses. Requests 6–10 returned HTTP 500 after approximately five seconds.

This suggested that connections were acquired but not released on some error paths. In particular, returning early for an unknown SKU, invalid location, disallowed transfer, or insufficient stock could bypass connection cleanup.

I initially thought the requests might simply be holding connections for too long. That was not the best explanation: ordinary slowness should clear when requests finish. A leaked connection is never returned to the pool, so the pool can remain exhausted even when there is no ongoing traffic.

### 15:30–15:39 — Add cleanup and retest

I reviewed the transfer handler and identified the need to return the connection on both success and failure. The appropriate structure is to acquire the connection, then release it in a `finally` block so every return path is covered.

After the change, I reran the leak test. All ten requests returned quickly with expected 400/404 responses, rather than later requests failing with HTTP 500.

**Status:** The retest supports that the connection leak was addressed for the tested paths. A broader regression test would still be useful.

## Commands and Results

### Initial inventory check

```bash
bash scripts/consistency_check.sh
```

Initial expected totals:

- `SKU-001`: 1800
- `SKU-002`: 3500
- `SKU-003`: 700

### Concurrent transfer test

```bash
bash scripts/burst_test.sh
bash scripts/consistency_check.sh
```

The burst test returned 100 HTTP 200 responses, but the subsequent consistency check showed unexpected loss from `SKU-001`.

### Connection leak test

The initial test exhausted the five-connection pool and produced HTTP 500 responses for requests 6–10 after about five seconds. After adding connection cleanup, the ten test requests returned quickly with the expected 400/404 responses.
