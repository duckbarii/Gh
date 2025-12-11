# aio_bomb.py — asyncio + aiohttp high-concurrency load generator
import asyncio
import aiohttp
import time
import sys

TARGET = "https://vehicleinfotrial.hackathonjce001.workers.dev"
CONCURRENCY = 2000   # number of concurrent coroutines (reduce if machine runs out of sockets)
TOTAL_REQUESTS = 20000
TIMEOUT = 30

sem = asyncio.Semaphore(CONCURRENCY)

async def fetch(session, url, idx):
    async with sem:
        try:
            async with session.get(url, timeout=TIMEOUT) as resp:
                await resp.read()   # read full body to exercise server
                return resp.status
        except Exception as e:
            return f"ERR:{e}"

async def worker(session, q, results):
    while True:
        i = await q.get()
        if i is None:
            break
        status = await fetch(session, TARGET, i)
        results.append(status)
        q.task_done()

async def main():
    q = asyncio.Queue()
    for i in range(TOTAL_REQUESTS):
        q.put_nowait(i)

    results = []
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    conn = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        tasks = []
        # spawn workers equal to concurrency (workers share the semaphore)
        for _ in range(CONCURRENCY):
            t = asyncio.create_task(worker(session, q, results))
            tasks.append(t)

        start = time.time()
        await q.join()
        end = time.time()

        # stop workers
        for _ in range(CONCURRENCY):
            q.put_nowait(None)
        await asyncio.gather(*tasks, return_exceptions=True)

    print(f"Requests: {len(results)}, Duration: {end-start:.2f}s")
    ok = sum(1 for r in results if isinstance(r, int) and 200 <= r < 400)
    errs = len(results) - ok
    print(f"OK: {ok}, ERR: {errs}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
