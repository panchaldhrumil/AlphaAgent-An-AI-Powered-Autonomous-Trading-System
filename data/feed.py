import os
import json
import asyncio
import requests
import websockets
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept":        "application/json"
}

INSTRUMENTS = {
    "NIFTY":     "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank"
}


# ─── REST: fetch completed 1-min candles ─────────────────────────────────────

def get_candle_ohlc(symbol: str, candle_time: str) -> dict:
    instrument_key = INSTRUMENTS[symbol]
    today = date.today().isoformat()  # e.g. "2025-06-14"

    url = (
        f"https://api.upstox.com/v2/historical-candle/{instrument_key}"
        f"/1minute/{today}/{today}"
    )

    response = requests.get(url, headers=HEADERS)
    data = response.json()

    candles = data.get("data", {}).get("candles", [])

    for candle in candles:
        ts = candle[0]
        if f"T{candle_time}:00" in ts:
            return {
                "timestamp": ts,
                "open":      candle[1],
                "high":      candle[2],
                "low":       candle[3],
                "close":     candle[4],
                "volume":    candle[5]
            }
    return None


def get_latest_candle(symbol: str) -> dict:
    instrument_key = INSTRUMENTS[symbol]
    today = date.today().isoformat()

    url = (
        f"https://api.upstox.com/v2/historical-candle/{instrument_key}"
        f"/1minute/{today}/{today}"
    )

    response = requests.get(url, headers=HEADERS)
    data = response.json()
    candles = data.get("data", {}).get("candles", [])

    if candles:
        candle = candles[0]
        return {
            "timestamp": candle[0],
            "open":      candle[1],
            "high":      candle[2],
            "low":       candle[3],
            "close":     candle[4],
            "volume":    candle[5]
        }
    return None


# ─── WebSocket: v3 protobuf feed ─────────────────────────────────────────────

async def get_ws_url() -> str:
    url = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    response = requests.get(url, headers=HEADERS)
    return response.json()["data"]["authorizedRedirectUri"]


def decode_feed(raw: bytes) -> list[dict]:
    results = []
    try:
        from upstox_client.feeder.proto.MarketDataFeedV3_pb2 import FeedResponse

        feed = FeedResponse()
        feed.ParseFromString(raw)

        for key, val in feed.feeds.items():
            symbol_name = next(
                (k for k, v in INSTRUMENTS.items() if v == key), key
            )
            try:
                ltp = val.ff.indexFF.ltpc.ltp
                ts  = datetime.now().strftime("%H:%M:%S")
                if ltp:
                    results.append({
                        "symbol":    symbol_name,
                        "ltp":       ltp,
                        "timestamp": ts
                    })
            except Exception:
                # equity instruments use marketFF instead of indexFF
                try:
                    ltp = val.ff.marketFF.ltpc.ltp
                    ts  = datetime.now().strftime("%H:%M:%S")
                    if ltp:
                        results.append({
                            "symbol":    symbol_name,
                            "ltp":       ltp,
                            "timestamp": ts
                        })
                except Exception:
                    pass

    except Exception as e:
        print(f"Decode error: {e}")

    return results

async def live_feed(on_tick: callable, symbols: list = ["NIFTY", "BANKNIFTY"]):
    ws_url = await get_ws_url()

    subscribe_msg = {
        "guid":   "orb-feed-001",
        "method": "sub",
        "data": {
            "mode":            "ltpc",
            "instrumentKeys": [INSTRUMENTS[s] for s in symbols]
        }
    }

    print("Connecting to Upstox v3 WebSocket...")

    async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
        await ws.send(json.dumps(subscribe_msg))
        print(f"Subscribed to: {symbols}")
        print("Waiting for ticks...\n")

        async for raw_message in ws:
            # Binary protobuf frame
            if isinstance(raw_message, bytes):
                ticks = decode_feed(raw_message)
                for tick in ticks:
                    await on_tick(tick["symbol"], tick["ltp"], tick["timestamp"])

            # JSON frame (subscription ack, heartbeat etc.)
            else:
                try:
                    data = json.loads(raw_message)
                    if data.get("type") == "error":
                        print(f"WS error: {data}")
                except Exception:
                    pass


# ─── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("=== Fetching 9:15 candle for NIFTY ===")
    candle = get_candle_ohlc("NIFTY", "09:15")
    print("Result:", candle)

    print("\n=== Fetching latest candle for BANKNIFTY ===")
    latest = get_latest_candle("BANKNIFTY")
    print("Result:", latest)

    print("\n=== Starting live feed (Ctrl+C to stop) ===")

    async def on_tick(symbol, ltp, ts):
        print(f"[{ts}]  {symbol:12s}  LTP: {ltp}")

    asyncio.run(live_feed(on_tick))