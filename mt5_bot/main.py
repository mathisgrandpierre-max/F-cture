"""
main.py - Point d'entrée.   python main.py <commande>

  download                  télécharge l'historique depuis MT5 (Windows, terminal ouvert)
  select                    teste les stratégies sur les CSV de data/ et écrit state/selection.json
  backtest SYMBOL STRAT     backtest complet d'une stratégie (paramètres par défaut de la grille) + coûts
  run                       lance le bot en live sur le compte DÉMO
  report weekly|monthly     affiche le rapport de performance
"""
import sys

import config as C


def cmd_download():
    import data_tools
    import mt5_io
    mt5_io.connect()
    for s in C.ACTIVE_SYMBOLS:
        df = mt5_io.fetch_history(s)
        data_tools.save_csv(s, df)
        print(f"{s}: {len(df)} bougies, {df.index[0]} -> {df.index[-1]}")


def cmd_select():
    import data_tools
    import selection
    data = {s: data_tools.load_csv(s) for s in C.ACTIVE_SYMBOLS}
    print(selection.format_report(selection.run_selection(data)))


def cmd_backtest(symbol, strat):
    import data_tools
    import metrics
    from engine import run_backtest
    from strategies import compute_signal, param_grid
    df, spec = data_tools.load_csv(symbol), C.SYMBOLS[symbol]
    p = param_grid(strat, spec.asset_class)[0]
    t = run_backtest(df, compute_signal(strat, df, p), spec, 0, len(df), p["sl_atr"], p["rr"], C.RISK_PER_TRADE, C.START_EQUITY)
    print(p, metrics.compute(t, C.START_EQUITY, len(df) / 24))


if __name__ == "__main__":
    a = sys.argv[1:] or ["help"]
    if a[0] == "download": cmd_download()
    elif a[0] == "select": cmd_select()
    elif a[0] == "backtest" and len(a) == 3: cmd_backtest(a[1], a[2])
    elif a[0] == "run":
        import bot; bot.run()
    elif a[0] == "report" and len(a) == 2:
        import reporting; print(reporting.build_report(a[1]))
    else:
        print(__doc__)
