from orb import ORBStrategy

def test_buy_trade():
    print("\n=== TEST: Full buy trade simulation ===")
    s = ORBStrategy("NIFTY", total_qty=100)
    s.set_opening_range(orh=22500, orl=22400)  # risk = 100

    # Simulate price touching ORH — should trigger BUY
    action = s.tick(22500, "09:16:00")
    assert action["action"] == "BUY", f"Expected BUY, got {action}"
    print(f"  BUY triggered at entry {s.entry_price}")

    # Target 1 (22500 + 100 = 22600)
    action = s.tick(22600, "09:20:00")
    assert action["reason"] == "TARGET_1"
    print(f"  Target 1 hit — exited 25 qty")

    # Target 2 (22700) — should also trail SL
    action = s.tick(22700, "09:25:00")
    assert action["reason"] == "TARGET_2_TRAIL_SL"
    assert s.sl_trailed == True
    assert s.trail_sl == 22500  # SL moved to entry
    print(f"  Target 2 hit — SL trailed to {s.trail_sl}")

    # Target 3 (22800)
    action = s.tick(22800, "09:30:00")
    assert action["reason"] == "TARGET_3"
    print(f"  Target 3 hit — 25 qty runner remaining")

    # Candle closes below trail SL — runner should exit
    action = s.update_candle_close(22499, "09:45")
    assert action["action"] == "EXIT_ALL"
    assert action["reason"] == "SL_HIT"
    print(f"  Runner stopped out at trail SL")

    print("  PASS")


def test_sell_trade():
    print("\n=== TEST: Full sell trade simulation ===")
    s = ORBStrategy("BANKNIFTY", total_qty=40)
    s.set_opening_range(orh=48200, orl=48000)  # risk = 200

    action = s.tick(48000, "09:16:00")
    assert action["action"] == "SELL"
    print(f"  SELL triggered at {s.entry_price}")

    # Target 1 (48000 - 200 = 47800)
    action = s.tick(47800, "09:22:00")
    assert action["reason"] == "TARGET_1"
    print(f"  Target 1 hit")

    # Target 2 (47600) — trail SL to entry
    action = s.tick(47600, "09:28:00")
    assert action["reason"] == "TARGET_2_TRAIL_SL"
    assert s.trail_sl == 48000
    print(f"  Target 2 hit — SL trailed to entry {s.trail_sl}")

    # EOD exit for runner
    action = s.end_of_day_exit(47550)
    assert action["reason"] == "EOD"
    print(f"  EOD square-off executed")

    print("  PASS")


if __name__ == "__main__":
    test_buy_trade()
    test_sell_trade()
    print("\nAll tests passed.")