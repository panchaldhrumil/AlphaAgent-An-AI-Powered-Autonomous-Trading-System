import os
import asyncio
from datetime import datetime, time
from dotenv import load_dotenv

from data.feed import live_feed, get_candle_ohlc
from strategy.orb import ORBStrategy, TradeState
from orders.manager import OrderManager

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

SYMBOLS    = ["NIFTY", "BANKNIFTY"]
QUANTITIES = {
    "NIFTY":     50,    # adjust to your risk appetite
    "BANKNIFTY": 25
}

OPENING_RANGE_TIME = time(9, 15)
ORB_FETCH_TIME     = time(9, 16)   # fetch 9:15 candle after it fully closes
EOD_EXIT_TIME      = time(15, 20)  # square off 10 min before close


# ─── Global state ─────────────────────────────────────────────────────────────

strategies: dict[str, ORBStrategy] = {}
order_manager = OrderManager(paper_trade=True)  # set False for live trading

opening_range_set  = {s: False for s in SYMBOLS}
eod_done           = {s: False for s in SYMBOLS}

# Tracks last candle minute seen — to trigger candle-close SL checks
last_candle_min: dict[str, int] = {s: -1 for s in SYMBOLS}


# ─── Initialise strategy instances ────────────────────────────────────────────

def init_strategies():
    for symbol in SYMBOLS:
        strategies[symbol] = ORBStrategy(symbol, total_qty=QUANTITIES[symbol])
    print(f"[{now()}] Strategies initialised for {SYMBOLS}")


# ─── Fetch and set opening range ──────────────────────────────────────────────

def fetch_opening_range(symbol: str):
    candle = get_candle_ohlc(symbol, "09:15")
    if candle:
        strategies[symbol].set_opening_range(
            orh=candle["high"],
            orl=candle["low"]
        )
        opening_range_set[symbol] = True
        print(f"[{now()}] {symbol} — ORH: {candle['high']}, ORL: {candle['low']}")
    else:
        print(f"[{now()}] {symbol} — Could not fetch 9:15 candle, retrying...")


# ─── Main tick handler (called on every live LTP update) ─────────────────────

async def on_tick(symbol: str, ltp: float, ts: str):
    now_time = datetime.now().time()

    # 1. Fetch opening range at 9:16 (once per symbol)
    if now_time >= ORB_FETCH_TIME and not opening_range_set[symbol]:
        fetch_opening_range(symbol)
        return

    # 2. Skip if opening range not ready
    if not opening_range_set[symbol]:
        return

    strategy = strategies[symbol]

    # 3. EOD square-off at 15:20
    if now_time >= EOD_EXIT_TIME and not eod_done[symbol]:
        action = strategy.end_of_day_exit(ltp)
        if action:
            eod_done[symbol] = True
            execute(action, strategy)
        return

    # 4. Candle-close SL check (fires once per minute on the new candle open)
    current_min = datetime.now().minute
    if current_min != last_candle_min[symbol]:
        last_candle_min[symbol] = current_min
        if strategy.last_candle_close is not None:
            action = strategy.update_candle_close(
                strategy.last_candle_close,
                datetime.now().strftime("%H:%M")
            )
            if action:
                execute(action, strategy)
                return

    # Update last seen close with current LTP
    # (approximation until we wire real candle closes)
    strategy.last_candle_close = ltp

    # 5. Process tick through strategy engine
    action = strategy.tick(ltp, ts)
    if action:
        execute(action, strategy)


# ─── Execute action via order manager ────────────────────────────────────────

def execute(action: dict, strategy: ORBStrategy):
    # Determine correct exit direction based on trade state
    if action["action"] in ["EXIT_PARTIAL", "EXIT_ALL"]:
        if strategy.state == TradeState.LONG or strategy.qty_remaining == 0:
            action["exit_side"] = "SELL"
        else:
            action["exit_side"] = "BUY"

    result = order_manager.execute_action(action)
    print(f"[{now()}] Order result: {result}")


# ─── Scheduler: runs alongside the feed ──────────────────────────────────────

async def scheduler():
    """
    Polls time every second for scheduled tasks.
    Keeps running until EOD.
    """
    while True:
        now_time = datetime.now().time()

        # Stop scheduler after EOD
        if now_time >= time(15, 31):
            print(f"[{now()}] Market closed. Bot shutting down.")
            break

        await asyncio.sleep(1)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main():
    print(f"[{now()}] AlgoBot starting...")
    print(f"[{now()}] Mode: {'PAPER TRADE' if order_manager.paper_trade else 'LIVE'}")

    init_strategies()

    # Run feed and scheduler concurrently
    await asyncio.gather(
        live_feed(on_tick, symbols=SYMBOLS),
        scheduler()
    )

    # Print end of day summary
    print(f"\n[{now()}] ===== EOD Summary =====")
    for symbol in SYMBOLS:
        status = strategies[symbol].get_status()
        print(f"\n{symbol}:")
        for k, v in status.items():
            print(f"  {k}: {v}")

    print(f"\n[{now()}] Order log:")
    for entry in order_manager.order_log:
        print(f"  {entry}")


def now():
    return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    asyncio.run(main())