from datetime import datetime
from enum import Enum


class Signal(Enum):
    BUY  = "BUY"
    SELL = "SELL"
    NONE = "NONE"


class TradeState(Enum):
    IDLE         = "IDLE"          # no position
    LONG         = "LONG"          # in a buy trade
    SHORT        = "SHORT"         # in a sell trade
    COMPLETED    = "COMPLETED"     # trade fully exited


class ORBStrategy:
    """
    9:15 Opening Range Breakout strategy engine.
    Stateful — one instance per symbol per day.
    Call tick() on every live LTP update.
    """

    def __init__(self, symbol: str, total_qty: int = 50):
        self.symbol       = symbol
        self.total_qty    = total_qty
        self.qty_per_part = total_qty // 4   # 25% of total

        # Opening range
        self.ORH: float = None
        self.ORL: float = None
        self.risk: float = None

        # Trade tracking
        self.state        = TradeState.IDLE
        self.entry_price  = None
        self.current_sl   = None
        self.trail_sl     = None
        self.sl_trailed   = False            # True after 1:2 target reached

        # Partial exit tracking
        self.targets_hit  = {1: False, 2: False, 3: False}
        self.qty_remaining = total_qty

        # Candle close tracking (for SL validation)
        self.last_candle_close: float = None
        self.last_candle_time:  str   = None

        # Action log for dashboard / agent
        self.actions: list[dict] = []


    # ─── Step 1: Set opening range ────────────────────────────────────────────

    def set_opening_range(self, orh: float, orl: float):
        self.ORH  = orh
        self.ORL  = orl
        self.risk = round(orh - orl, 2)
        self._log(f"Opening range set — ORH: {orh}, ORL: {orl}, Risk: {self.risk}")


    # ─── Step 2: Update candle close (called on every 1-min candle close) ────

    def update_candle_close(self, close: float, candle_time: str):
        self.last_candle_close = close
        self.last_candle_time  = candle_time

        # Check candle-close-based stop loss
        if self.state == TradeState.LONG:
            sl_level = self.trail_sl if self.sl_trailed else self.ORL
            if close <= sl_level:
                self._log(
                    f"STOP LOSS triggered — candle closed at {close} "
                    f"<= SL {sl_level}"
                )
                return self._exit_action("SL_HIT", self.qty_remaining, close)

        elif self.state == TradeState.SHORT:
            sl_level = self.trail_sl if self.sl_trailed else self.ORH
            if close >= sl_level:
                self._log(
                    f"STOP LOSS triggered — candle closed at {close} "
                    f">= SL {sl_level}"
                )
                return self._exit_action("SL_HIT", self.qty_remaining, close)

        return None


    # ─── Step 3: Process live tick ────────────────────────────────────────────

    def tick(self, ltp: float, timestamp: str) -> dict | None:
        """
        Main method. Call on every live LTP update.
        Returns an action dict if something needs to be executed, else None.

        Action dict format:
        {
            "action":    "BUY" | "SELL" | "EXIT_PARTIAL" | "EXIT_ALL",
            "symbol":    "NIFTY",
            "qty":       25,
            "price":     ltp,
            "reason":    "ORH_BREAKOUT" | "TARGET_1" | ... | "EOD",
            "timestamp": "09:17:34"
        }
        """

        if not self.ORH or not self.ORL:
            return None   # Opening range not set yet

        if self.state == TradeState.COMPLETED:
            return None

        # ── No position yet: watch for breakout ───────────────────────────────

        if self.state == TradeState.IDLE:
            if ltp >= self.ORH:
                self.state       = TradeState.LONG
                self.entry_price = ltp
                self.current_sl  = self.ORL
                self._log(f"BUY signal at {ltp} — ORH breakout")
                return self._action("BUY", self.total_qty, ltp, "ORH_BREAKOUT")

            if ltp <= self.ORL:
                self.state       = TradeState.SHORT
                self.entry_price = ltp
                self.current_sl  = self.ORH
                self._log(f"SELL signal at {ltp} — ORL breakdown")
                return self._action("SELL", self.total_qty, ltp, "ORL_BREAKDOWN")

        # ── In a LONG position: check targets ─────────────────────────────────

        elif self.state == TradeState.LONG:
            t1 = self.entry_price + (1 * self.risk)
            t2 = self.entry_price + (2 * self.risk)
            t3 = self.entry_price + (3 * self.risk)

            if not self.targets_hit[3] and ltp >= t3:
                self.targets_hit[3] = True
                self.qty_remaining -= self.qty_per_part
                self._log(f"TARGET 3 hit at {ltp} — exit 25%")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_3")

            if not self.targets_hit[2] and ltp >= t2:
                self.targets_hit[2] = True
                self.qty_remaining -= self.qty_per_part
                # Trail SL to entry (break-even)
                self.sl_trailed = True
                self.trail_sl   = self.entry_price
                self._log(f"TARGET 2 hit at {ltp} — exit 25%, SL trailed to {self.entry_price}")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_2_TRAIL_SL")

            if not self.targets_hit[1] and ltp >= t1:
                self.targets_hit[1] = True
                self.qty_remaining -= self.qty_per_part
                self._log(f"TARGET 1 hit at {ltp} — exit 25%")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_1")

        # ── In a SHORT position: check targets ────────────────────────────────

        elif self.state == TradeState.SHORT:
            t1 = self.entry_price - (1 * self.risk)
            t2 = self.entry_price - (2 * self.risk)
            t3 = self.entry_price - (3 * self.risk)

            if not self.targets_hit[3] and ltp <= t3:
                self.targets_hit[3] = True
                self.qty_remaining -= self.qty_per_part
                self._log(f"TARGET 3 hit at {ltp} — cover 25%")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_3")

            if not self.targets_hit[2] and ltp <= t2:
                self.targets_hit[2] = True
                self.qty_remaining -= self.qty_per_part
                self.sl_trailed = True
                self.trail_sl   = self.entry_price
                self._log(f"TARGET 2 hit at {ltp} — cover 25%, SL trailed to {self.entry_price}")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_2_TRAIL_SL")

            if not self.targets_hit[1] and ltp <= t1:
                self.targets_hit[1] = True
                self.qty_remaining -= self.qty_per_part
                self._log(f"TARGET 1 hit at {ltp} — cover 25%")
                return self._action("EXIT_PARTIAL", self.qty_per_part, ltp, "TARGET_1")

        return None


    # ─── End of day square-off ────────────────────────────────────────────────

    def end_of_day_exit(self, ltp: float) -> dict | None:
        if self.state in [TradeState.LONG, TradeState.SHORT] and self.qty_remaining > 0:
            self._log(f"EOD square-off — exiting {self.qty_remaining} qty at {ltp}")
            self.state = TradeState.COMPLETED
            return self._action("EXIT_ALL", self.qty_remaining, ltp, "EOD")
        return None


    # ─── Status snapshot (for dashboard / agent) ──────────────────────────────

    def get_status(self) -> dict:
        return {
            "symbol":         self.symbol,
            "state":          self.state.value,
            "ORH":            self.ORH,
            "ORL":            self.ORL,
            "risk":           self.risk,
            "entry_price":    self.entry_price,
            "current_sl":     self.trail_sl if self.sl_trailed else self.current_sl,
            "sl_trailed":     self.sl_trailed,
            "targets_hit":    self.targets_hit,
            "qty_remaining":  self.qty_remaining,
            "total_qty":      self.total_qty,
        }


    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _action(self, action: str, qty: int, price: float, reason: str) -> dict:
        entry = {
            "action":    action,
            "symbol":    self.symbol,
            "qty":       qty,
            "price":     price,
            "reason":    reason,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self.actions.append(entry)
        return entry

    def _exit_action(self, reason: str, qty: int, price: float) -> dict:
        self.state = TradeState.COMPLETED
        return self._action("EXIT_ALL", qty, price, reason)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.symbol}] {msg}")