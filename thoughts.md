# Timecodes

13:45 - Forking repo + cloning to local machine
13:48 - Built environment - Docker run
13:51 - Logged an error:

```bash
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ dcup --build
ERROR: Invalid interpolation format for "db" option in service "services": "${DB_PORT:-5432}:5432"
```

-> The error happened due to the wrongfully shortening command dcup

13:54 - Checked api health endpoint under /api/health under localhost/docs
13:55 - Checkend endpoints to compare to given database of SKU -> 1:1 identical
14:10 - Got stuck for a few minutes due to not seeing jq as an requirement got error before through terminal:

bash consistency_check.sh -> result below

```bash
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL  SKU-001  no answer from http://localhost:8080/api/inventory/SKU-001
FAIL  SKU-002  no answer from http://localhost:8080/api/inventory/SKU-002
FAIL  SKU-003  no answer from http://localhost:8080/api/inventory/SKU-003
```

Tried running from terminal:

```bash
 docker compose ps
 docker compose logs app | tail -30
 curl -v http://localhost:8080/api/health
```

-> Resulted in success, containers running, logs looking nornal, curl returned healthy "UP"

14:13 -> Reviewed the scripts section in readme + asked ChatGPT on that topic got a command

```bash
sudo apt install jq
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
OK    SKU-001  total=1800   expected=1800   WAREHOUSE-A=1000  WAREHOUSE-B=500  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200
```

Received Expected Result

14:15 -> Made sure that 100 means quantity through api reviewing, and

```bash

bash scripts/burst_test.sh
Sending 100 transfers of SKU-001 (10 units each), 20 at a time, to http://localhost:8080
Finished in 0s. HTTP status codes:
      100 200
```

14:20 -> Full picture,

Run ./scripts/consistency_check.sh to compare the totals.

```bash

(inventory-transfer-service-py3.12) ➜ inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
OK SKU-001 total=1800 expected=1800 WAREHOUSE-A=1000 WAREHOUSE-B=500 WAREHOUSE-C=300
OK SKU-002 total=3500 expected=3500 WAREHOUSE-A=2000 WAREHOUSE-B=1500
OK SKU-003 total=700 expected=700 WAREHOUSE-A=500 WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜ inventory-transfer-python git:(main) ✗ bash scripts/burst_test.sh
Sending 100 transfers of SKU-001 (10 units each), 20 at a time, to http://localhost:8080
Finished in 0s. HTTP status codes:
100 200

Run ./scripts/consistency_check.sh to compare the totals.
(inventory-transfer-service-py3.12) ➜ inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL SKU-001 total=1700 expected=1800 WAREHOUSE-A=980 WAREHOUSE-B=420 WAREHOUSE-C=300
OK SKU-002 total=3500 expected=3500 WAREHOUSE-A=2000 WAREHOUSE-B=1500
OK SKU-003 total=700 expected=700 WAREHOUSE-A=500 WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜ inventory-transfer-python git:(main) ✗

```

14:22 -> Reviewing(ChatGPT usage) burst test line by line
14:35 -> Figuring out concurency and it's impact (Talking to Claude on this whole situation asking why did we got chipped 10% of stock out of nowhere) (Claude explained the mechanism and I verified it by running the burst test) question is below.

```txt
so based on what I nderstood in our hypothetical situation we had
OK    SKU-001  total=1800   expected=1800   WAREHOUSE-A=1000  WAREHOUSE-B=500  WAREHOUSE-C=300

We had 20 streams(concurency) each one of them is taking 10 Units per stream,  and we have like 100 requests like this.
But I can't understand why did we lose only 100 units, so in total we transfered without changing the amount like 1000 units but got 10% lost in system due. Or I kinda understanding a little by little so we were chipping little by litle only at like every tenth request that, right?

FAIL  SKU-001  total=1700   expected=1800   WAREHOUSE-A=980  WAREHOUSE-B=420  WAREHOUSE-C=300
```

-> (lost update from overlapping read-modify-write),I marked as unconfirmed until reading thoroughly the code.

14:56 - After talking to my rubber duck and running burst testing a few times, I got my theory on only every 10% of stock dissapearing destroyed. At first thought it was a fixed leak rate, then realized it’s nondeterministic.

The biggest problem for the moment it fails silently, thowing me an success message

```bash
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
OK    SKU-001  total=1800   expected=1800   WAREHOUSE-A=1000  WAREHOUSE-B=500  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗  bash scripts/burst_test.sh
Sending 100 transfers of SKU-001 (10 units each), 20 at a time, to http://localhost:8080
Finished in 0s. HTTP status codes:
      100 200

Run ./scripts/consistency_check.sh to compare the totals.
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL  SKU-001  total=1700   expected=1800   WAREHOUSE-A=980  WAREHOUSE-B=420  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL  SKU-001  total=1700   expected=1800   WAREHOUSE-A=980  WAREHOUSE-B=420  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/burst_test.sh
Sending 100 transfers of SKU-001 (10 units each), 20 at a time, to http://localhost:8080
Finished in 0s. HTTP status codes:
      100 200

Run ./scripts/consistency_check.sh to compare the totals.
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL  SKU-001  total=1640   expected=1800   WAREHOUSE-A=950  WAREHOUSE-B=390  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/burst_test.sh
Sending 100 transfers of SKU-001 (10 units each), 20 at a time, to http://localhost:8080
Finished in 1s. HTTP status codes:
      100 200

Run ./scripts/consistency_check.sh to compare the totals.
(inventory-transfer-service-py3.12) ➜  inventory-transfer-python git:(main) ✗ bash scripts/consistency_check.sh
FAIL  SKU-001  total=1550   expected=1800   WAREHOUSE-A=920  WAREHOUSE-B=330  WAREHOUSE-C=300
OK    SKU-002  total=3500   expected=3500   WAREHOUSE-A=2000  WAREHOUSE-B=1500
OK    SKU-003  total=700    expected=700    WAREHOUSE-A=500  WAREHOUSE-C=200

```

15:10 -> leak_test.sh result (pool stuck at 5 active, #6-#10 returned 500 after about 5s) -> docker compose restart app should fix that for a while based on assumption

```bash
Pool while the requests are running:
{"max":5,"total":5,"active":5,"idle":0,"waiting":5}

Responses (status, time):
  #1  404 0.002954s
  #2  400 0.031444s
  #3  400 0.035231s
  #4  404 0.012900s
  #5  400 0.022321s
  #6  500 5.020799s
  #7  500 5.008856s
  #8  500 5.007833s
  #9  500 5.009271s
  #10  500 5.008153s
```

15:30 - So basically here happens something like back in C/C++ when user opens the file by getconn(in this way) and holding it till he succeddes in writing e.g. 1000 characters, as we are limiting ourself with five users each one of them writes in his own file, it takes time, so by the time next users comes there still prev users working. (My question on results of the test to CLaude) -> I got it a little bit wrong here: the problem isn’t that users hold a connection for a long time. Each request would only hold it for about 10ms. The problem is that the failing requests never close the file at all. Slowness would clear itself as users finish. A leak never clears, because nobody is left to release the handle. That’s why the pool stays at active=5 with zero traffic.

So in my opinion briefly reading your view we need to give back our stream on success or no success like here (sketched) -> then reviewed added try ... finally block :

```python
async def transfer(req: TransferRequest):
    conn = await db.getconn()

    levels = await repository.get_stock_levels(conn, req.sku)
    if not levels:
        # HERE: BEFORE FINISHING CLOSING
        return error(404, f"unknown SKU {req.sku}")

    for location in (req.from_location, req.to_location):
        if location not in levels:
            # HERE: BEFORE FINISHING CLOSING. somewhere here
            return error(404, f"{req.sku} is not stocked at {location}")

    problem = await check_transfer_allowed(
        req.sku, req.from_location, req.to_location, req.quantity
    )
    if problem:
        # HERE: BEFORE FINISHING CLOSING
        return error(400, problem)

    available = levels[req.from_location]
    if available < req.quantity:
        message = (
            f"insufficient stock at {req.from_location}: "
            f"available {available}, requested {req.quantity}"
        )
        # HERE: BEFORE FINISHING CLOSING
        return error(400, message)

    await repository.move_stock(conn, req.sku, req.from_location, req.to_location, req.quantity)
    await db.putconn(conn)

    return {
        "status": "COMPLETED",
        "sku": req.sku,
        "fromLocation": req.from_location,
        "toLocation": req.to_location,
        "quantity": req.quantity,
    }
```

15:39 - Results on second problem:

```txt
Responses (status, time):
#1 404 0.003256s
#2 400 0.002355s
#3 400 0.014330s
#4 404 0.003556s
#5 400 0.002677s
#6 400 0.014080s
#7 404 0.002959s
#8 400 0.004834s
#9 400 0.014185s
#10 404 0.001626s
```

15:40 - Commiting to a new branch, pushing, merging
15:43 - Reviewing Bug 1 stock inconsistency, talking to Claude on this topic

```txt
Okay, so basically reading what you wrote I think the idea of ordering them anyhow is a good one, we can either index them(the concurent requests) to sort or sort them like you proposed by alphabet location based, The first thign I would read then write, A->B read, A->B write, then B-> A read, B->A write, during the read process we check stocks. I think it would be wiser to roll back during some missmatch with data

-> Got it wrong the summary on my viewing

We don’t order the requests, we order the locks. Requests aren’t queued globally. Each request takes its two row locks in alphabetical order (A before B, always). Transfers touching different rows still run in parallel, and only transfers sharing a row wait for each other. This is also the deadlock protection from before.
The read has to be a locking read. A plain SELECT doesn’t stop anyone else from changing the row. It must be SELECT ... FOR UPDATE, so the “read” is also the “take the lock”. My wording “read then write” is right only if the read holds the lock until the write is done.
The write is quantity = quantity - n, applied to the value in the database, not a value you calculated from your own earlier read.
```

16:10 -> fixed that by acquiring multiple row locks in a consistent order to prevent racing and added Error prevent acquiring units from empty stock

```sql
            "SELECT location, quantity FROM inventory "
            "WHERE sku = %s AND location IN (%s, %s) ORDER BY location FOR UPDATE",
            (sku, from_location, to_location),
```
