"""Tests hors-ligne (sans clés, sans réseau) : python -m pytest test_bot.py"""
import importlib

import pandas as pd
import pytest


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_CLAUDE", "false")
    monkeypatch.setenv("MIN_TRADES_TO_RANK", "2")
    import bot as b
    b = importlib.reload(b)
    monkeypatch.setattr(b, "STATE_FILE", tmp_path / "state.json")
    return b


def series(values):
    idx = pd.date_range("2025-01-02 14:30", periods=len(values), freq="15min")
    return pd.Series(values, index=idx, dtype=float)


def test_claude_disabled(bot):
    assert "claude" not in bot.STRATEGIES
    assert set(bot.STRATEGIES) == {"sma_cross", "rsi_reversion", "breakout"}


def test_portfolio_buy_sell(bot):
    p = bot.Portfolio(name="t")
    p.buy("SPY", 100.0)
    assert "SPY" in p.positions and p.n_trades == 1
    p.mark({"SPY": 100.0})
    spent = bot.START_CASH - p.cash
    assert spent == pytest.approx(bot.START_CASH * bot.MAX_POS_PCT)
    p.buy("SPY", 100.0)                      # déjà en position : ignoré
    assert p.n_trades == 1
    p.sell("SPY", 110.0)
    assert p.positions == {} and p.n_trades == 2
    assert p.ret() > 0


def test_drawdown_tracked(bot):
    p = bot.Portfolio(name="t")
    p.buy("SPY", 100.0)
    p.mark({"SPY": 100.0})
    p.mark({"SPY": 50.0})
    assert p.max_dd > 0


def test_score_needs_min_trades(bot):
    p = bot.Portfolio(name="t")
    assert p.score() is None
    p.buy("SPY", 100.0); p.mark({"SPY": 100.0}); p.sell("SPY", 100.0)
    assert p.score() is not None


def test_sma_cross_signals(bot):
    up = series([100 - i * 0.5 for i in range(30)] + [90 + i * 2 for i in range(15)])
    assert bot.strat_sma_cross("X", up, False) == "buy"
    down = series([100 + i * 0.5 for i in range(30)] + [115 - i * 2 for i in range(15)])
    assert bot.strat_sma_cross("X", down, True) == "sell"
    assert bot.strat_sma_cross("X", series([100] * 10), False) == "hold"


def test_rsi_reversion_signals(bot):
    falling = series([100 - i for i in range(30)])
    assert bot.strat_rsi_reversion("X", falling, False) == "buy"
    rising = series([50 + i for i in range(30)])
    assert bot.strat_rsi_reversion("X", rising, True) == "sell"


def test_breakout_signals(bot):
    flat = [100.0] * 24
    assert bot.strat_breakout("X", series(flat + [105.0]), False) == "buy"
    assert bot.strat_breakout("X", series(flat + [95.0]), True) == "sell"
    assert bot.strat_breakout("X", series(flat + [100.0]), False) == "hold"


def test_state_roundtrip(bot):
    pf = bot.load_state()
    pf["sma_cross"].buy("SPY", 100.0)
    pf["sma_cross"].mark({"SPY": 101.0})
    bot.save_state(pf)
    again = bot.load_state()
    assert again["sma_cross"].positions == pf["sma_cross"].positions
    assert again["sma_cross"].equity() == pytest.approx(pf["sma_cross"].equity())


def test_leaderboard_and_leader(bot):
    pf = bot.load_state()
    assert bot.current_leader(pf) is None          # pas assez de trades
    win, lose = pf["sma_cross"], pf["breakout"]
    win.buy("SPY", 100.0); win.mark({"SPY": 100.0}); win.sell("SPY", 120.0); win.mark({"SPY": 120.0})
    lose.buy("SPY", 100.0); lose.mark({"SPY": 100.0}); lose.sell("SPY", 80.0); lose.mark({"SPY": 80.0})
    assert bot.current_leader(pf).name == "sma_cross"
    assert bot.leaderboard(pf)[0].name == "sma_cross"
    bot.print_board(pf)


def test_main_loop_with_fake_alpaca(bot, monkeypatch):
    """Un cycle complet de run() avec un faux Alpaca, puis arrêt."""
    class Clock:
        is_open = True

    class Trading:
        calls = []
        def get_clock(self): return Clock()
        def get_all_positions(self): return []
        def get_account(self):
            class A: equity = "10000"; last_equity = "10000"
            return A()
        def submit_order(self, req): self.calls.append(req)
        def close_position(self, s): self.calls.append(("close", s))
        def close_all_positions(self, **k): self.calls.append("close_all")

    closes = series([100 - i * 0.5 for i in range(30)] + [90 + i * 2 for i in range(15)])
    fake = Trading()
    monkeypatch.setattr(bot, "clients", lambda: (fake, object()))
    monkeypatch.setattr(bot, "fetch_bars", lambda d: {"SPY": closes})
    monkeypatch.setattr(bot, "_running", True)

    def stop_after_first_sleep(_):
        bot._running = False
    monkeypatch.setattr(bot, "sleep_interruptible", stop_after_first_sleep)
    monkeypatch.setattr(bot, "STOP_FILE", bot.STATE_FILE.parent / "STOP")
    monkeypatch.setattr(bot.signal, "signal", lambda *a: None)
    bot.run()
    assert bot.STATE_FILE.exists()
    assert bot.load_state()["sma_cross"].positions            # a acheté SPY
