import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept":        "application/json",
    "Content-Type":  "application/json"
}

# Upstox instrument keys for F&O (futures — needed for Nifty/BankNifty trading)
# These change every expiry — update the expiry date accordingly
INSTRUMENT_KEYS = {
    "NIFTY":     "NSE_FO|26000",   # replace with current Nifty futures instrument key
    "BANKNIFTY": "NSE_FO|26009"    # replace with current BankNifty futures instrument key
}

BASE_URL = "https://api.upstox.com/v2"


class OrderManager:
    """
    Places, modifies, and cancels orders on Upstox.
    All actions are logged with timestamp and order ID.
    Set paper_trade=True to simulate without real orders.
    """

    def __init__(self, paper_trade: bool = True):
        self.paper_trade = paper_trade
        self.order_log: list[dict] = []

        if self.paper_trade:
            print("[OrderManager] Running in PAPER TRADE mode — no real orders placed")
        else:
            print("[OrderManager] Running in LIVE mode — real orders will be placed")


    # ─── Place order ──────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol:       str,
        action:       str,    # "BUY" or "SELL"
        qty:          int,
        order_type:   str = "MARKET",
        price:        float = 0,
        product:      str = "D"   # D = intraday, I = delivery
    ) -> dict:

        payload = {
            "quantity":        qty,
            "product":         product,
            "validity":        "DAY",
            "price":           price,
            "tag":             "ORB_STRATEGY",
            "instrument_token": INSTRUMENT_KEYS[symbol],
            "order_type":      order_type,
            "transaction_type": action,
            "disclosed_quantity": 0,
            "trigger_price":   0,
            "is_amo":          False
        }

        if self.paper_trade:
            fake_order_id = f"PAPER_{datetime.now().strftime('%H%M%S%f')}"
            result = {
                "order_id":  fake_order_id,
                "symbol":    symbol,
                "action":    action,
                "qty":       qty,
                "status":    "PAPER_EXECUTED",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            self._log(result)
            print(f"  [PAPER] {action} {qty} {symbol} @ MARKET")
            return result

        # Live order
        response = requests.post(
            f"{BASE_URL}/order/place",
            headers=HEADERS,
            json=payload
        )
        data = response.json()

        if data.get("status") == "success":
            order_id = data["data"]["order_id"]
            result = {
                "order_id":  order_id,
                "symbol":    symbol,
                "action":    action,
                "qty":       qty,
                "status":    "PLACED",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            self._log(result)
            print(f"  [LIVE] {action} {qty} {symbol} — order_id: {order_id}")
            return result

        else:
            error = data.get("errors", data)
            print(f"  [ERROR] Order failed: {error}")
            return {"status": "FAILED", "error": error}


    # ─── Cancel order ─────────────────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> dict:
        if self.paper_trade:
            print(f"  [PAPER] Cancel order {order_id}")
            return {"status": "PAPER_CANCELLED", "order_id": order_id}

        response = requests.delete(
            f"{BASE_URL}/order/cancel",
            headers=HEADERS,
            params={"order_id": order_id}
        )
        data = response.json()
        print(f"  [LIVE] Cancel response: {data}")
        return data


    # ─── Get order status ─────────────────────────────────────────────────────

    def get_order_status(self, order_id: str) -> dict:
        if self.paper_trade:
            return {"order_id": order_id, "status": "COMPLETE"}

        response = requests.get(
            f"{BASE_URL}/order/details",
            headers=HEADERS,
            params={"order_id": order_id}
        )
        return response.json().get("data", {})


    # ─── Get open positions ───────────────────────────────────────────────────

    def get_positions(self) -> list:
        if self.paper_trade:
            return []

        response = requests.get(f"{BASE_URL}/portfolio/short-term-positions", headers=HEADERS)
        return response.json().get("data", [])


    # ─── Process action from strategy engine ──────────────────────────────────

    def execute_action(self, action_dict: dict) -> dict:
        """
        Takes an action dict from ORBStrategy.tick() and executes the right order.

        action_dict format:
        { "action": "BUY"|"SELL"|"EXIT_PARTIAL"|"EXIT_ALL",
          "symbol": "NIFTY", "qty": 25, "price": 22500, "reason": "..." }
        """
        action  = action_dict["action"]
        symbol  = action_dict["symbol"]
        qty     = action_dict["qty"]
        price   = action_dict["price"]
        reason  = action_dict["reason"]

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Executing: {action} {qty} {symbol} — {reason}")

        if action == "BUY":
            return self.place_order(symbol, "BUY", qty)

        elif action == "SELL":
            return self.place_order(symbol, "SELL", qty)

        elif action in ["EXIT_PARTIAL", "EXIT_ALL"]:
            # For a long position exit = SELL, for short exit = BUY
            # The strategy engine tracks direction so we infer from reason
            # We'll pass direction explicitly in next step when wiring to main
            # For now default to SELL (long exit) — will fix in main.py
            return self.place_order(symbol, "SELL", qty)

        return {"status": "UNKNOWN_ACTION"}


    # ─── Log ──────────────────────────────────────────────────────────────────

    def _log(self, entry: dict):
        self.order_log.append(entry)


# ─── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    om = OrderManager(paper_trade=True)

    print("\n=== Test: Execute a BUY action ===")
    result = om.execute_action({
        "action":    "BUY",
        "symbol":    "NIFTY",
        "qty":       50,
        "price":     22500,
        "reason":    "ORH_BREAKOUT",
        "timestamp": "09:16:00"
    })
    print("Result:", result)

    print("\n=== Test: Execute partial exit ===")
    result = om.execute_action({
        "action":    "EXIT_PARTIAL",
        "symbol":    "NIFTY",
        "qty":       12,
        "price":     22600,
        "reason":    "TARGET_1",
        "timestamp": "09:20:00"
    })
    print("Result:", result)

    print("\n=== Order log ===")
    for entry in om.order_log:
        print(entry)