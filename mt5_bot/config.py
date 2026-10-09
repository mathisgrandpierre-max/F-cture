"""
config.py - TOUS LES PARAMÈTRES MODIFIABLES SONT ICI.

Rappel : je ne suis pas conseiller financier agréé. Le trading comporte un risque
de perte en capital. Ce code est un outil d'apprentissage, à utiliser en DÉMO.
"""
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"          # historiques CSV (un fichier par symbole)
STATE_DIR = BASE_DIR / "state"        # état du bot (risque, stratégies actives)
LOG_DIR = BASE_DIR / "logs"           # journaux (trades, décisions)
REPORT_DIR = BASE_DIR / "reports"     # rapports hebdo / mensuels
NEWS_FILE = DATA_DIR / "news.csv"     # calendrier économique (voir GUIDE.md)

# ------------------------------------------------------------------ COMPTE / SÉCURITÉ
ACCOUNT_CURRENCY = "EUR"
START_EQUITY = 10_000.0               # capital simulé pour les backtests
ALLOW_REAL_ACCOUNT = False            # False = le bot REFUSE de tourner sur un compte réel
SERVER_UTC_OFFSET_HOURS = 3           # décalage heure du serveur du broker vs UTC (souvent 2 ou 3)
MAGIC_NUMBER = 20260101               # identifie les ordres de CE bot dans MT5

# ------------------------------------------------------------------ RISQUE (voir risk.py)
# Ces valeurs peuvent seulement être RESSERRÉES : risk.py applique des plafonds durs.
RISK_PER_TRADE = 0.01                 # 1 % du capital risqué par trade (plafond dur : 1 %)
MAX_DAILY_LOSS = 0.03                 # -3 % sur la journée -> le bot s'arrête jusqu'à demain
MAX_MONTHLY_LOSS = 0.08               # -8 % sur le mois -> le bot s'arrête jusqu'au mois suivant
MAX_OPEN_TRADES = 3                   # positions ouvertes simultanées (plafond dur : 5)
MAX_TRADES_PER_DAY = 6                # évite le sur-trading
MAX_MARGIN_USAGE = 0.30               # jamais plus de 30 % de la marge libre utilisée
NEWS_BLACKOUT_MIN = 30                # pas de trade ±30 min autour d'une news "high"
MAX_SPREAD_MULT = 3.0                 # pas de trade si le spread actuel > 3 x le spread normal
NEWS_FILE_MAX_AGE_DAYS = 8            # calendrier trop vieux -> le bot ne trade pas (sécurité)

# ------------------------------------------------------------------ DONNÉES / TIMEFRAME
TIMEFRAME = "H1"                      # bougies 1 heure : peu de bruit, peu de temps requis
HISTORY_YEARS = 3                     # profondeur d'historique à télécharger
HEARTBEAT_SECONDS = 30                # fréquence de vérification de la boucle live


@dataclass(frozen=True)
class SymbolSpec:
    """Caractéristiques d'un instrument (valeurs APPROXIMATIVES pour le backtest ;
    en live, le bot lit les vraies valeurs dans MT5)."""
    name: str
    asset_class: str            # "fx" | "metal" | "crypto"
    pip_size: float             # taille d'un pip (0.0001 EURUSD, 0.01 USDJPY, 0.1 XAU, 1.0 BTC)
    point: float                # plus petit mouvement de prix (spread MT5 exprimé en points)
    pip_value: float            # gain/perte en EUR pour 1 lot et 1 pip (APPROXIMATION)
    notional_per_lot: float     # valeur d'1 lot en EUR (APPROXIMATION, pour limiter le levier)
    commission_per_lot: float   # commission EUR par lot et par côté (0 si incluse dans le spread)
    swap_long_pips: float       # swap/nuit en pips pour un achat (négatif = coût)
    swap_short_pips: float      # swap/nuit en pips pour une vente
    slippage_pips: float        # glissement moyen supposé à chaque exécution au marché
    default_spread_pips: float  # spread utilisé si l'historique n'a pas de colonne 'spread'
    session_utc: tuple          # heures UTC autorisées pour OUVRIR un trade (début, fin)
    close_friday_hour: int      # fermeture forcée le vendredi à cette heure UTC (24 = jamais)
    min_lot: float = 0.01
    lot_step: float = 0.01


# ⚠️ Valeurs d'exemple : adapte-les à TON broker (spread/commission/swap réels de son compte démo).
SYMBOLS = {
    "EURUSD": SymbolSpec("EURUSD", "fx", 0.0001, 0.00001, 9.0, 100_000, 3.0, -0.7, -0.2,
                         0.2, 0.8, (7, 20), 21),
    "GBPUSD": SymbolSpec("GBPUSD", "fx", 0.0001, 0.00001, 9.0, 117_000, 3.0, -0.6, -0.3,
                         0.3, 1.1, (7, 20), 21),
    "USDJPY": SymbolSpec("USDJPY", "fx", 0.01, 0.001, 6.0, 92_000, 3.0, 0.4, -1.2,
                         0.3, 1.0, (0, 20), 21),
    "XAUUSD": SymbolSpec("XAUUSD", "metal", 0.1, 0.01, 9.0, 270_000, 3.0, -2.5, 1.0,
                         1.0, 2.5, (7, 20), 21),
    "BTCUSD": SymbolSpec("BTCUSD", "crypto", 1.0, 0.01, 0.9, 85_000, 0.0, -25.0, -25.0,
                         15.0, 30.0, (0, 24), 24),
}
ACTIVE_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]   # symboles traités par le bot (ajoute XAUUSD/BTCUSD plus tard)
SYMBOL_SUFFIX = ""                                 # ex. ".pro" si ton broker nomme EURUSD.pro

# ------------------------------------------------------------------ SÉLECTION DE STRATÉGIE
HOLDOUT_FRACTION = 0.25     # derniers 25 % des données : jamais utilisés pour choisir, test final unique
WF_TRAIN_DAYS = 180         # walk-forward : fenêtre d'entraînement
WF_TEST_DAYS = 60           # walk-forward : fenêtre de test juste après
MIN_TRADES_TRAIN = 15       # une fenêtre d'entraînement avec moins de trades n'est pas fiable
# Critères pour qu'une stratégie soit éligible (mesurés sur l'ensemble des fenêtres de TEST) :
MIN_TRADES_OOS = 60
MIN_PROFIT_FACTOR = 1.20
MAX_DRAWDOWN = 0.15
MIN_POSITIVE_FOLDS = 0.60   # au moins 60 % des fenêtres de test gagnantes
MAX_MC_DRAWDOWN = 0.20      # drawdown au 95e centile des simulations Monte-Carlo
MIN_HOLDOUT_PF = 1.10       # test final sur les données jamais vues
MC_SIMULATIONS = 1000

# ------------------------------------------------------------------ RE-TEST / DÉSACTIVATION
RETEST_EVERY_DAYS = 7             # relance la sélection complète chaque semaine
HEALTH_WINDOW_TRADES = 30         # on juge la forme d'une stratégie sur ses 30 derniers trades
HEALTH_MIN_PF = 0.90              # profit factor live < 0,9 sur la fenêtre -> désactivation
HEALTH_DD_MULTIPLIER = 1.5        # drawdown live > 1,5 x drawdown de test -> désactivation

# ------------------------------------------------------------------ ALERTES (variables d'environnement)
# TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID : voir GUIDE.md. Jamais dans le code, jamais sur GitHub.
