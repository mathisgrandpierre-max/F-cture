"""
bot.py - Boucle principale (live sur COMPTE DÉMO). Lance-le avec :  python main.py run

À chaque nouvelle bougie H1 clôturée, pour chaque symbole actif :
  1. calcule le signal de la stratégie choisie par selection.py ;
  2. ferme / ouvre selon le signal, APRÈS validation par RiskManager (stop-loss, limites, news, session) ;
  3. journalise tout et envoie les alertes.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import config as C
import mt5_io as io
import notifier
import reporting
import risk
from monitor import check_health
from strategies import compute_signal
import indicators as ind

log = logging.getLogger("bot")
STATE_FILE = C.STATE_DIR / "bot_state.json"


def setup_logging():
    C.LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(C.LOG_DIR / "decisions.log", encoding="utf-8"), logging.StreamHandler()])


def load_state() -> dict:
    s = {"last_bar": {}, "positions": {}, "blocked": {}, "disabled_until": {}, "last_retest": None,
         "last_weekly": None, "last_monthly": None}
    if STATE_FILE.exists():
        s.update(json.loads(STATE_FILE.read_text()))
    return s


def save_state(s):
    C.STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


def load_selection() -> dict:
    p = C.STATE_DIR / "selection.json"
    return json.loads(p.read_text())["symbols"] if p.exists() else {}


def flatten(reason: str):
    for p in io.my_positions():
        if io.close_position(p):
            notifier.send(f"Position {p.symbol} fermée ({reason})")


def reconcile(state: dict, risk_mgr):
    """Détecte les positions fermées (SL/TP/manuel) et les écrit dans le journal."""
    open_ids = {str(p.ticket) for p in io.my_positions()}
    for tid, info in list(state["positions"].items()):
        if tid in open_ids:
            continue
        res = io.closed_position_result(int(tid))
        if res is None:
            continue
        row = dict(entry_time=info["time"], exit_time=res["exit_time"], symbol=info["symbol"], strategy=info["strategy"],
                   dir=info["dir"], lots=info["lots"], entry=info["entry"], exit=res["exit"], pnl=round(res["pnl"], 2),
                   pnl_pct=res["pnl"] / info["equity"], r=res["pnl"] / info["risk_money"], reason=res["reason"])
        reporting.journal_trade(row)
        if res["reason"] == "SL":
            state["blocked"][info["symbol"]] = info["dir"]
        notifier.send(f"Trade clôturé {info['symbol']} {info['strategy']} : {res['pnl']:+.2f} {C.ACCOUNT_CURRENCY} ({res['reason']})")
        del state["positions"][tid]


def health_checks(state: dict, sel: dict, now):
    """Désactive automatiquement une stratégie qui se dégrade en réel."""
    j = reporting.load_journal()
    for sym, r in sel.items():
        d = r["decision"]
        if d["status"] != "ACTIVE" or sym in state["disabled_until"] or j.empty:
            continue
        g = j[(j["symbol"] == sym) & (j["strategy"] == d["strategy"])]
        ok, why = check_health(g, d.get("expected_dd", 0.1))
        if not ok:
            state["disabled_until"][sym] = (now + timedelta(days=14)).isoformat()
            notifier.send(f"⚠️ Stratégie {d['strategy']} DÉSACTIVÉE sur {sym} : {why}. Pause 14 jours minimum.")


def process_symbol(sym, decision, state, risk_mgr, now):
    spec = C.SYMBOLS[sym]
    df = io.recent_closed_bars(sym)
    last = str(df.index[-1])
    if state["last_bar"].get(sym) == last:
        return                                               # pas de nouvelle bougie
    state["last_bar"][sym] = last
    mine = [p for p in io.my_positions() if p.symbol == sym + C.SYMBOL_SUFFIX]
    active = decision["status"] == "ACTIVE" and sym not in state["disabled_until"]
    sig = int(compute_signal(decision["strategy"], df, decision["params"])[-1]) if active else 0
    if state["blocked"].get(sym) and sig != state["blocked"][sym]:
        state["blocked"].pop(sym)
    friday_close = spec.asset_class != "crypto" and now.weekday() == 4 and now.hour >= spec.close_friday_hour
    for p in mine:                                           # sortie sur changement de signal
        cur = 1 if p.type == 0 else -1
        if sig != cur or friday_close:
            log.info("%s: fermeture (signal=%s, position=%s)", sym, sig, cur)
            io.close_position(p)
    if mine and sig == (1 if mine[0].type == 0 else -1):
        return
    if sig == 0 or not active or sig == state["blocked"].get(sym) or [p for p in io.my_positions() if p.symbol == sym + C.SYMBOL_SUFFIX]:
        return
    info, t, acc = io.symbol_info(sym), io.tick(sym), io.account()
    a = float(ind.atr(df).iloc[-1])
    sl_dist = decision["params"]["sl_atr"] * a
    entry = t.ask if sig > 0 else t.bid
    sl = entry - sig * sl_dist
    rr = decision["params"].get("rr", 0.0)
    tp = entry + sig * sl_dist * rr if rr > 0 else 0.0
    spread = t.ask - t.bid
    ok, why = risk_mgr.can_open(sym, now, len(io.my_positions()), sl, spread / spec.pip_size, spec.default_spread_pips)
    if not ok:
        log.info("%s: signal %s REFUSÉ par le risque: %s", sym, sig, why)
        return
    lots = risk.position_size(acc.equity, sl_dist, spread, spec.slippage_pips * spec.pip_size, info.trade_tick_size,
                              info.trade_tick_value, info.volume_min, info.volume_step, info.volume_max)
    if lots <= 0 or not io.margin_ok(sym, sig, lots, entry):
        log.info("%s: taille nulle ou marge insuffisante -> pas de trade", sym)
        return
    res = io.open_market(sym, sig, lots, round(sl, info.digits), round(tp, info.digits) if tp else 0.0, decision["strategy"])
    if res:
        risk_mgr.register_open()
        risk_money = lots * (sl_dist + spread) / info.trade_tick_size * info.trade_tick_value
        state["positions"][str(res.order)] = dict(symbol=sym, strategy=decision["strategy"], dir=sig, lots=lots, entry=res.price,
                                                  time=now.isoformat(), equity=acc.equity, risk_money=risk_money)
        notifier.send(f"Ouverture {sym} {'ACHAT' if sig > 0 else 'VENTE'} {lots} lot | SL {sl:.5f} | {decision['strategy']} | risque {risk_money:.2f}")


def maybe_retest(state, now):
    """Chaque semaine : retélécharge l'historique et relance la sélection complète."""
    last = state["last_retest"]
    if last and now - datetime.fromisoformat(last) < timedelta(days=C.RETEST_EVERY_DAYS):
        return
    import data_tools
    import selection
    data = {}
    for s in C.ACTIVE_SYMBOLS:
        df = io.fetch_history(s)
        data_tools.save_csv(s, df)
        data[s] = df
    out = selection.run_selection(data)
    state["last_retest"] = now.isoformat()
    notifier.send("Re-test hebdomadaire terminé:\n" + "\n".join(f"{s}: {r['decision']['status']} {r['decision'].get('strategy', '')}" for s, r in out["symbols"].items()))


def run():
    setup_logging()
    io.connect()
    risk_mgr, state = risk.RiskManager(), load_state()
    notifier.send("Bot démarré (DÉMO).")
    while True:
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            maybe_retest(state, now)
            sel = load_selection()
            acc = io.account()
            reconcile(state, risk_mgr)
            msg = risk_mgr.update(acc.equity, now)
            if msg:
                flatten("limite de perte")
                notifier.send("🛑 " + msg)
            if not risk_mgr.is_halted(now):
                health_checks(state, sel, now)
                for sym in C.ACTIVE_SYMBOLS:
                    if sym in sel:
                        process_symbol(sym, sel[sym]["decision"], state, risk_mgr, now)
            if now.weekday() == 0 and state["last_weekly"] != now.strftime("%G-%V"):
                notifier.send(reporting.build_report("weekly", now)); state["last_weekly"] = now.strftime("%G-%V")
            if now.day == 1 and state["last_monthly"] != now.strftime("%Y-%m"):
                notifier.send(reporting.build_report("monthly", now)); state["last_monthly"] = now.strftime("%Y-%m")
            save_state(state)
        except KeyboardInterrupt:
            notifier.send("Bot arrêté (Ctrl+C). Les stop-loss restent actifs chez le broker.")
            break
        except Exception as e:
            log.exception("Erreur de cycle: %s", e)
            notifier.send(f"Erreur du bot: {e}")
            time.sleep(60)
        time.sleep(C.HEARTBEAT_SECONDS)
