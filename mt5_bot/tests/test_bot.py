"""Tests automatiques :  cd mt5_bot && python -m pytest -q"""
import dataclasses
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config as C
import risk
import selection
from engine import run_backtest
from strategies import STRATEGIES, compute_signal, param_grid
from synthetic import make_prices, make_trending

EURUSD = C.SYMBOLS["EURUSD"]


# ------------------------------------------------------------------ risque
def test_position_size_respects_one_percent():
    # stop 20 pips sur EURUSD : tick 0.00001, valeur du tick ~0.9 EUR par lot
    lots = risk.position_size(10_000, 0.0020, 0.0001, 0.00002, 0.00001, 0.9, 0.01, 0.01, 100)
    loss = (0.0020 + 0.0001 + 0.00004) / 0.00001 * 0.9 * lots
    assert 0 < lots and loss <= 100.0 + 1e-6          # 1 % de 10 000 = 100


def test_position_size_never_rounds_up_to_minimum():
    assert risk.position_size(200, 0.0050, 0.0001, 0, 0.00001, 0.9, 0.01, 0.01, 100) == 0.0


def test_risk_cap_cannot_be_raised():
    assert risk.position_size(10_000, 0.002, 0, 0, 0.00001, 0.9, 0.01, 0.01, 100, risk_pct=0.5) <= \
        risk.position_size(10_000, 0.002, 0, 0, 0.00001, 0.9, 0.01, 0.01, 100, risk_pct=0.01)


def test_daily_loss_halts(tmp_path):
    rm = risk.RiskManager(tmp_path / "r.json")
    t0 = datetime(2026, 3, 10, 8, 0)
    assert rm.update(10_000, t0) == ""
    assert "JOURNALIÈRE" in rm.update(10_000 * (1 - C.MAX_DAILY_LOSS - 0.001), t0.replace(hour=12))
    assert rm.is_halted(t0.replace(hour=13))
    assert not rm.is_halted(datetime(2026, 3, 11, 0, 1))


def test_stop_loss_mandatory_and_news_block(tmp_path):
    news = tmp_path / "news.csv"
    news.write_text("time_utc,currency,impact,event\n2026-03-10T13:30:00,USD,high,CPI\n")
    now = datetime(2026, 3, 10, 13, 10, tzinfo=timezone.utc)
    import os, time
    os.utime(news, (time.time(), time.time()))
    assert risk.news_blocked("EURUSD", now, news)[0]
    assert not risk.news_blocked("EURUSD", now.replace(hour=9), news)[0]
    assert risk.news_blocked("EURUSD", now, tmp_path / "absent.csv")[0]     # fichier absent -> blocage
    rm = risk.RiskManager(tmp_path / "r.json")
    ok, why = rm.can_open("EURUSD", datetime(2026, 3, 10, 9), 0, None, 1, 1)
    assert not ok and "stop-loss" in why


# ------------------------------------------------------------------ moteur
def test_oracle_profits_and_costs_hurt():
    df = make_prices(n_days=200)
    sig = np.sign(df["close"].shift(-1) - df["open"].shift(-1)).fillna(0).astype(int).to_numpy()
    free = dataclasses.replace(EURUSD, commission_per_lot=0, slippage_pips=0, swap_long_pips=0, swap_short_pips=0)
    d0 = df.assign(spread=0)
    assert run_backtest(d0, sig, free, 0, len(df), sl_atr=50)["pnl"].sum() > 0
    costly = run_backtest(df, sig, EURUSD, 0, len(df), sl_atr=50)["pnl"].sum()
    assert costly < run_backtest(d0, sig, free, 0, len(df), sl_atr=50)["pnl"].sum()


def test_no_lookahead_future_change_does_not_alter_past_trades():
    df = make_trending(n_days=200)
    p = param_grid("sma_cross", "fx")[0]
    a = run_backtest(df, compute_signal("sma_cross", df, p), EURUSD, 0, 3000, p["sl_atr"], p["rr"])
    df2 = df.copy()
    df2.iloc[3500:, :4] *= 1.3                                  # on modifie l'avenir
    b = run_backtest(df2, compute_signal("sma_cross", df2, p), EURUSD, 0, 3000, p["sl_atr"], p["rr"])
    pd.testing.assert_frame_equal(a, b)


def test_loss_at_stop_close_to_one_percent():
    df = make_prices(n_days=300, seed=5)
    p = param_grid("range_breakout", "fx")[0]
    t = run_backtest(df, compute_signal("range_breakout", df, p), EURUSD, 0, len(df), p["sl_atr"], 0.0)
    sl_losses = t[t["reason"] == "SL"]["pnl_pct"]
    assert len(sl_losses) > 5 and sl_losses.min() > -0.0125      # jamais bien au-delà de 1 % (gaps exclus)


def test_all_strategies_return_valid_signals():
    df = make_trending(n_days=120)
    for name in STRATEGIES:
        for ac in ("fx", "crypto"):
            for p in param_grid(name, ac):
                s = compute_signal(name, df, p)
                assert len(s) == len(df) and set(np.unique(s)) <= {-1, 0, 1}


# ------------------------------------------------------------------ sélection (anti-surapprentissage)
def test_random_walk_yields_no_active_strategy():
    for seed in (1, 2, 3):
        r = selection.evaluate_symbol(make_prices(seed=seed), EURUSD)
        assert r["decision"]["status"] == "NONE", f"seed {seed}: une stratégie a été validée sur du pur hasard"


def test_real_edge_is_found_and_holdout_confirms():
    r = selection.evaluate_symbol(make_trending(seed=3), EURUSD)
    assert r["decision"]["status"] == "ACTIVE"
    assert r["decision"]["strategy"] in ("sma_cross", "range_breakout", "momentum_atr")


def test_sharpe_hurdle_grows_with_trials():
    assert selection.sharpe_hurdle(100, 1.0) > selection.sharpe_hurdle(5, 1.0) > 0


def test_health_monitor_disables_degraded_strategy():
    from monitor import check_health
    n = 30
    bad = pd.DataFrame({"pnl": [-10.0] * 20 + [5.0] * 10, "pnl_pct": [-0.001] * 20 + [0.0005] * 10, "r": 0.0,
                        "entry_time": pd.date_range("2026-01-01", periods=n, freq="D"),
                        "exit_time": pd.date_range("2026-01-01", periods=n, freq="D")})
    assert not check_health(bad, 0.10)[0]
