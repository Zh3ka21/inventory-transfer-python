# Inventory Transfer Service (Python)

This is Zunft's backend assignment: improve an inherited warehouse transfer
service. Choose **one** backend language version; you only need to submit one
repository. The Zunft scope and submission rules below apply to this exercise.

## The guidance on setting up is in setup.md file
[Setup.md](https://github.com/Zh3ka21/inventory-transfer-python/blob/main/setup.md)

## The situation

You have just joined the warehouse team. This service moves stock of a
product (a SKU) from one warehouse location to another.

The service has run in the development environment for several weeks without
any problems. Last week the team started load testing before the release,
and the service began to fail. The team has spent two days on it and they are
stuck. They have asked you to help.

## The business rule

**The total quantity of a SKU across all locations must stay the same after
any number of transfers.** A transfer only moves stock. It must never create
or destroy it.

The database starts with this data:

| SKU     | Location    | Quantity |
|---------|-------------|----------|
| SKU-001 | WAREHOUSE-A | 1000     |
| SKU-001 | WAREHOUSE-B | 500      |
| SKU-001 | WAREHOUSE-C | 300      |
| SKU-002 | WAREHOUSE-A | 2000     |
| SKU-002 | WAREHOUSE-B | 1500     |
| SKU-003 | WAREHOUSE-A | 500      |
| SKU-003 | WAREHOUSE-C | 200      |

So the totals must always be: SKU-001 = 1800, SKU-002 = 3500, SKU-003 = 700.

## Tech stack

- Python 3.12, FastAPI, uvicorn
- psycopg 3 with `psycopg_pool`
- PostgreSQL 15

The database connection pool has a maximum of 5 connections. A request waits
up to 5 seconds for a free connection.

Code layout:

```
app/
  main.py         application setup
  routes.py       HTTP handlers
  rules.py        business rules for transfers
  repository.py   database queries
  db.py           connection pool
db/init.sql       schema and seed data
scripts/          test scripts
```

## Running the service

### With Docker (recommended)

You need Docker with Docker Compose.

```bash
docker compose up --build
```

This starts PostgreSQL, loads the data from `db/init.sql` and starts the
service on http://localhost:8080. PostgreSQL is also available on
`localhost:5432` (user `inventory`, password `inventory`, database
`inventory`) if you want to look inside it with `psql` or another tool. If
port 5432 is already in use on your machine, start with
`DB_PORT=5433 docker compose up --build`.

Useful commands:

```bash
docker compose restart app     # restart only the service, keep the data
docker compose down -v         # stop everything and delete the data
docker compose up --build      # start again with fresh seed data
docker compose logs -f app     # follow the service logs
```

### Without Docker

You need PostgreSQL 15 running on your machine.

```bash
createdb inventory
psql -d inventory -f db/init.sql
```

Then start the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgres://inventory:inventory@localhost:5432/inventory
uvicorn app.main:app --port 8080
```

`DATABASE_URL` defaults to
`postgres://inventory:inventory@localhost:5432/inventory`.

## The API

Read the stock of a SKU:

```bash
curl http://localhost:8080/api/inventory/SKU-001
```

```json
{
  "sku": "SKU-001",
  "locations": [
    {"location": "WAREHOUSE-A", "quantity": 1000},
    {"location": "WAREHOUSE-B", "quantity": 500},
    {"location": "WAREHOUSE-C", "quantity": 300}
  ],
  "total": 1800
}
```

Move stock:

```bash
curl -X POST http://localhost:8080/api/transfer \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU-001","fromLocation":"WAREHOUSE-A","toLocation":"WAREHOUSE-B","quantity":10}'
```

It answers `200` when the transfer is done, `400` when there is not enough
stock or the quantity is not positive, and `404` when the SKU or location is
unknown.

Check the service and its connection pool:

```bash
curl http://localhost:8080/api/health
```

```json
{"status": "UP", "pool": {"max": 5, "total": 1, "active": 0, "idle": 1, "waiting": 0}}
```

`max` is the pool limit, `total` is how many connections are open, `active`
is how many are in use, `idle` is how many are free, and `waiting` is how many
requests are waiting for a connection.

## Scripts

The `scripts/` folder has some tools the team wrote during load testing. They
need `bash`, `curl` and `jq`. **On Windows, run them in WSL or Git Bash.**

| Script | What it does |
|--------|--------------|
| `./scripts/consistency_check.sh` | Compares the total of each SKU with the expected value. Prints OK or FAIL per SKU. |
| `./scripts/burst_test.sh [concurrency] [total]` | Sends many valid transfers at the same time (default: 20 at a time, 100 in total), alternating WAREHOUSE-A to WAREHOUSE-B and back. |
| `./scripts/leak_test.sh [count]` | Sends transfers that cannot succeed, then prints the state of the connection pool. |
| `./scripts/pool_monitor.sh` | Prints the state of the connection pool once per second. Stop it with Ctrl+C. |

All scripts use `http://localhost:8080` by default. You can change this with
the `BASE_URL` environment variable.

## What the team has seen

1. **The totals stop adding up.** After many transfers run at the same time,
   the total of a SKU is no longer the expected value. When the same
   transfers are sent one by one, everything looks correct.
2. **The service stops responding.** After a series of failed transfers (for
   example, transfers with too little stock), new transfers hang for a few
   seconds and then fail. After a restart the service works again, for a
   while.

## Zunft scope

1. Run the service and reproduce the issues using the provided scripts.
2. Investigate the root causes; there may be more than one bug. Explain why ordinary tests miss the behavior.
3. Prioritize fixes, make focused code changes, and verify them with reproducible checks or tests.
4. Describe any refactoring, monitoring, or safeguards you would consider, and why.

You do not need to find or fix every issue. Record blockers, hypotheses,
unsuccessful attempts, and unfinished work.

## Timebox

Timebox your work to **2–3 hours**, including setup, investigation,
implementation, and notes. Stop by three hours and submit what you have.
**Full completion is not expected. An honest thinking log is more valuable
than completing every task without transparency.**

## AI tools

AI tools are allowed. Explain what you delegated, accepted or rejected, and
how you checked it. Be ready to explain your reasoning and demonstrate the
changed behavior in a follow-up interview.

## Submission

Clone the assignment repository into your account and submit your public
cloned repository (or a patch), with code changes to the extent reached
within the timebox. Do not send exercise solutions as pull requests to the
upstream repository.

Include concise notes in `NOTES.md` (alternatively an **optional screen
recording with your voice comments**) covering:

- Starting repository; how to run your version.
- Problems found, priorities, and root causes for changes you made.
- Reproduction steps and tests or manual checks, including results.
- Assumptions, rejected alternatives, deliberate omissions, and next steps with another day.
- Time spent and an honest thinking log: what you noticed, tried, learned, changed your mind about, and left unfinished. Include failed attempts, blockers, and uncertainty. For AI/tool use, explain what you delegated, accepted or rejected, and how you checked it. Brief chronological notes are enough; full chat transcripts are not required.

## Assessment and follow-up

We assess substantive scope and reasoning, not setup effort or unfamiliar
tooling alone. If setup consumes the timebox, document the blocker and your
approach rather than spending extra unpaid time.

In the follow-up interview, be ready to show the changed behavior and explain
a root cause. We assess your reasoning and understanding of the submitted
code, not your ability to recite an upstream answer.
