import asyncio

async def sleep(secs):
    await asyncio.sleep(secs)
    return f"You just sleeped for {secs} secs"

SLEEP_TOOLS = {
    "sleep":sleep
}