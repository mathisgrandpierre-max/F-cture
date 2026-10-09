# Bot MT5 multi-stratégies (DÉMO) — Guide complet

> ⚠️ **Je ne suis pas conseiller financier agréé.** Le trading (Forex, CFD, Bitcoin) comporte un risque élevé de **perte totale du capital**. Ce projet sert à **apprendre et valider en démo**. Aucun bot ne garantit un revenu.

Ce dossier (`mt5_bot/`) est indépendant du bot Alpaca (actions US) qui se trouve dans le `README.md` à la racine du dépôt.

## 0. Hypothèses prises (tu peux me corriger)

Je n'ai pas bloqué ma réponse sur des questions, j'ai pris des valeurs par défaut raisonnables :

1. **Windows** : le paquet Python `MetaTrader5` ne fonctionne que sous Windows (sur Mac/Linux : machine virtuelle ou VPS Windows).
2. **Bougies H1** (1 heure) : peu de bruit, peu de trades, compatible avec tes cours (le bot tourne seul, tu regardes 30 min par semaine).
3. **Broker inconnu** : les spreads/commissions/swaps de `config.py` sont des exemples ; tu dois les remplacer par ceux de **ton** compte démo.

## 1. Ce qu'on peut raisonnablement attendre d'un bot

Mini-glossaire (première apparition) :
- **Pip / lot** : un pip = plus petit mouvement « standard » d'un prix (0,0001 sur EURUSD) ; 1 lot = 100 000 unités de la devise de base.
- **Spread** : écart entre le prix d'achat et de vente ; c'est un coût payé à chaque trade.
- **Slippage (glissement)** : écart entre le prix demandé et le prix obtenu (pire pendant les news).
- **Swap** : frais (ou gain) pour garder une position ouverte la nuit.
- **Drawdown** : la plus grosse baisse du capital entre un sommet et le creux suivant (−20 % = tu as perdu 20 % depuis ton plus haut).
- **Profit factor (PF)** : somme des gains ÷ somme des pertes. PF 1,0 = on ne gagne rien ; 1,3 = correct ; > 2 sur peu de trades = suspect.
- **Ratio de Sharpe** : rendement moyen ÷ variabilité des rendements (gagner régulièrement vaut mieux que gagner par à-coups).
- **Levier** : emprunt qui multiplie gains **et** pertes. 30:1 = 1 000 € contrôlent 30 000 €.

**Pourquoi la plupart des bots perdent en réel** : (1) les coûts (spread + commission + swap) mangent un petit avantage ; (2) les backtests sont sur-optimisés : on a « appris » le passé par cœur (*overfitting*, surapprentissage) ; (3) les marchés changent de régime ; (4) le levier amplifie les erreurs ; (5) l'exécution réelle est moins parfaite qu'en démo. Les brokers européens doivent afficher que **environ 70 à 80 % des comptes particuliers perdent de l'argent** en CFD.

### Tableau de réalisme (ordres de grandeur, **pas** des promesses)

| Capital simulé | Rendement mensuel *réaliste* (net de coûts, si le bot a un vrai avantage) | Drawdown probable | En euros |
|---|---|---|---|
| 500 € | 0 à 3 % | 10 à 25 % | 0 à 15 €/mois ; creux de −50 à −125 € |
| 1 000 € | 0 à 3 % | 10 à 25 % | 0 à 30 €/mois ; creux de −100 à −250 € |
| 5 000 € | 0 à 3 % | 10 à 25 % | 0 à 150 €/mois ; creux de −500 à −1 250 € |
| 10 000 € | 0 à 3 % | 10 à 25 % | 0 à 300 €/mois ; creux de −1 000 à −2 500 € |
| 100 000 € | 0 à 3 % | 10 à 25 % | 0 à 3 000 €/mois ; creux de −10 à −25 k€ |

À lire ainsi : **la borne basse (0 %, voire négatif) est la plus fréquente**. Pour gagner 1 000 €/mois à 1,5 %/mois il faudrait ≈ 67 000 € de capital — et supporter un creux de plusieurs milliers d'euros. Un rendement « 10 %/mois » promis quelque part est soit de la martingale (qui explose un jour), soit une arnaque.

## 2. Architecture et choix technique

```
mt5_bot/
  config.py      ← TOUS les paramètres (capital, risque, symboles, seuils)
  indicators.py  ← SMA, RSI, Bollinger, ATR, Donchian
  strategies.py  ← 4 stratégies + grilles de paramètres par classe d'actif
  engine.py      ← backtest réaliste (spread, commission, swap, slippage)
  metrics.py     ← PF, drawdown, Sharpe, Monte-Carlo
  selection.py   ← walk-forward + holdout + anti-biais de sélection
  risk.py        ← gestion du risque NON désactivable
  monitor.py     ← désactivation auto d'une stratégie qui se dégrade
  mt5_io.py      ← connexion MT5 (refuse les comptes réels)
  bot.py         ← boucle live        main.py ← commandes
  notifier.py    ← Telegram           reporting.py ← journal + rapports
  tests/         ← 13 tests automatiques
```

**Python plutôt qu'un Expert Advisor MQL5** : le backtest rigoureux (walk-forward, Monte-Carlo, classement, rapports, Telegram) est bien plus simple et lisible en Python, et on peut le tester sans MT5. Un EA MQL5 s'exécute *dans* MT5 (plus proche du broker, pas besoin de script externe) mais le Strategy Tester MT5 rend le walk-forward et l'analyse statistique pénibles. Choix : **Python pilote MT5**. Les ordres partent toujours **avec stop-loss placé chez le broker** : si ton PC plante, le stop reste actif.

## 3. Les 4 stratégies

| Stratégie | Logique | Forces | Faiblesses | Quand elle échoue |
|---|---|---|---|---|
| `sma_cross` (tendance) | Achat si moyenne rapide > lente (avec marge en ATR), vente sinon | Capte les grosses tendances (XAUUSD, BTC) | Nombreux petits stops, retard à l'entrée | Marché en range : « coups de fouet » répétés |
| `rsi_bollinger` (retour à la moyenne) | Achat si prix sous la bande basse **et** RSI survendu ; sortie à la moyenne | Bon en range (EURUSD en session calme) | Un seul gros mouvement de tendance = grosse perte | Forte tendance, news, cassures de volatilité |
| `range_breakout` (cassure) | Achat si clôture > plus haut de N bougies ; ouverture limitée aux sessions londonienne/US pour le Forex | Simple, robuste, bon sur les ouvertures de session | Fausses cassures fréquentes | Marché sans direction, spreads larges |
| `momentum_atr` (momentum + volatilité) | Suit un mouvement fort (> k×ATR) seulement si la volatilité est au-dessus de sa médiane | Évite les périodes mortes | Entre tard, retournements brutaux | Retournement après un pic de volatilité |

**Adaptation à la paire** (automatique) : spread/commission/swap/slippage propres à chaque symbole (`config.SYMBOLS`) ; sessions d'ouverture (Forex : 7h–20h UTC, jamais le week-end, fermeture forcée le vendredi soir) ; Bitcoin : 24h/24, 7j/7, stops plus larges (3–4 ATR), fenêtres plus longues, coûts de glissement très supérieurs.

## 4. Sélection automatique de la meilleure stratégie

1. **Backtest avec coûts** : achat à l'ask, vente au bid (spread réel de la colonne `spread` de MT5), commission, swap (×3 le mercredi), slippage. Si stop et objectif sont touchés dans la même bougie → on compte le stop (pessimiste). Signal calculé à la clôture, exécuté à l'**ouverture suivante** (un test automatique vérifie qu'il n'y a pas de triche sur le futur).
2. **Walk-forward** : on optimise les paramètres sur 180 jours, on mesure sur les 60 jours **suivants jamais vus** (*out-of-sample*), on fait glisser. Seuls les résultats de test comptent.
3. **Holdout** : les 25 % de données les plus récentes ne sont **pas utilisés** pour choisir ; une seule vérification finale.
4. **Biais de sélection** : si tu essaies 40 combinaisons, la meilleure paraît bonne par pur hasard. Le Sharpe du test doit dépasser le meilleur Sharpe qu'on obtiendrait **au hasard** avec ce nombre d'essais (« Sharpe déflaté » simplifié).
5. **Classement** par note de robustesse (PF plafonné à 3, pénalité si peu de trades ou drawdown élevé, % de fenêtres gagnantes), **pas** par profit brut. Filtres : ≥ 60 trades, PF ≥ 1,2, drawdown ≤ 15 %, ≥ 60 % de fenêtres gagnantes, drawdown Monte-Carlo (ordre des trades mélangé 1 000 fois) ≤ 20 %.
6. **Re-test** chaque semaine (historique frais) et **désactivation automatique** en live si le PF des 30 derniers trades < 0,9 ou si le drawdown dépasse 1,5× celui du test (pause minimale de 14 jours).

**Résultat « NONE » = normal et sain** : le bot reste à plat plutôt que de trader du bruit. Vérifié par test : sur 3 marches aléatoires (aucun avantage possible), **aucune** stratégie n'est validée ; sur des données avec tendance persistante, elle l'est.

## 5. Gestion du risque (non désactivable)

| Règle | Valeur | Où |
|---|---|---|
| Risque par trade | ≤ 1 % du capital (plafond dur, `config` ne peut que baisser) | `risk.position_size` |
| Stop-loss | obligatoire ; l'ordre est refusé / fermé s'il n'est pas posé | `risk.can_open`, `mt5_io.open_market` |
| Taille de position | calculée auto, arrondie **vers le bas** ; si le lot minimum dépasse le risque → pas de trade | `risk.py` |
| Perte journalière | −3 % → fermeture + arrêt jusqu'à demain (plafond dur 5 %) | `RiskManager.update` |
| Perte mensuelle | −8 % → arrêt jusqu'au mois suivant (plafond dur 15 %) | idem |
| Trades ouverts | max 3 (plafond dur 5), 6 nouveaux trades/jour | `can_open` |
| Marge | max 30 % de la marge libre | `mt5_io.margin_ok` |
| Spread anormal | refus si > 3× le spread normal | `can_open` |
| News | aucun trade ±30 min autour d'une news « high » ; calendrier absent ou > 8 jours → **pas de trade** | `news_blocked` |
| Sessions / week-end | entrées uniquement pendant les heures de la paire | `engine.entry_mask` |
| Compte réel | **refusé** (`ALLOW_REAL_ACCOUNT=False`) | `mt5_io.connect` |

## 6. Guide d'installation pas à pas (première fois)

1. **Choisir un broker régulé** (voir §9) proposant MetaTrader 5 et un **compte démo** gratuit.
2. **Ouvrir le compte démo** : sur le site du broker, « Compte démo » → plateforme **MT5** → note le *login*, le *mot de passe* et le *serveur*. Choisis la devise **EUR** et un capital de démo de 10 000.
3. **Installer MT5** (lien fourni par le broker), ouvrir, *Fichier → Se connecter à un compte de trading* avec tes identifiants.
4. **Activer le trading algo** : *Outils → Options → Expert Advisors* → coche « Autoriser le trading algorithmique ». Le bouton **Algo Trading** de la barre du haut doit être **vert**.
5. **Historique complet** : *Outils → Options → Graphiques* → « Max. de barres dans le graphique » = *Illimité*. Ouvre un graphique H1 de chaque paire (le terminal télécharge l'historique).
6. **Installer Python 3.12 (64 bits)** depuis python.org en cochant **« Add Python to PATH »**.
7. **Récupérer le projet** : `git clone https://github.com/mathisgrandpierre-max/F-cture` puis `git checkout claude/modest-ride-xpmtwm`, ou bouton *Code → Download ZIP*. Dans un terminal : `cd F-cture\mt5_bot` puis `pip install -r requirements.txt`.
8. **Vérifier que tout fonctionne** : `python -m pytest -q` → « 13 passed ».
9. **Adapter `config.py`** : `SYMBOL_SUFFIX` (si ton broker écrit `EURUSD.pro`, mets `".pro"`), et remplace spreads/commissions/swaps par ceux de ton compte (*clic droit sur le symbole → Spécification*).
10. **Calendrier de news** : copie `data/news.csv.example` en `data/news.csv` et remplis-le chaque semaine avec les news « high impact » de la semaine (colonnes `time_utc,currency,impact,event` ; source gratuite : calendrier économique de ton broker ou d'un site public). 10 min par semaine ; sans cela le bot ne trade pas (sécurité voulue).
11. **Télécharger l'historique** : `python main.py download`.
12. **Lancer le backtest / la sélection** : `python main.py select`. Lecture d'une ligne :

    | Champ | Signification | Bon signe |
    |---|---|---|
    | `n` | nombre de trades de test | ≥ 60 |
    | `PF` | profit factor | 1,2 à 2 (méfiance au-delà de 3) |
    | `DD` | drawdown max | < 15 % |
    | `Sharpe (seuil X)` | doit dépasser le seuil « hasard » | Sharpe > seuil |
    | `fenêtres+` | % de fenêtres de test gagnantes | ≥ 60 % |
    | `OK` / `REFUSÉ: …` | décision et motifs | `NONE` est une réponse valide |

13. **Telegram (optionnel)** : dans Telegram, parle à `@BotFather` → `/newbot` → copie le token ; envoie un message à ton bot puis ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` pour lire ton `chat id`. Dans PowerShell : `setx TELEGRAM_BOT_TOKEN "…"` et `setx TELEGRAM_CHAT_ID "…"` (puis rouvre le terminal). Ne mets **jamais** ces valeurs dans le code ni sur GitHub.
14. **Premier test réel en démo** : mets `MAX_OPEN_TRADES = 1`, lance `python main.py run`, et vérifie dans MT5 (onglet *Trade*) que la première position a bien un **S/L** et une taille cohérente avec 1 % de risque. (La couche `mt5_io.py` n'a pas pu être testée sur un vrai terminal pendant l'écriture : ce test est indispensable.)
15. **Laisser tourner** : PC allumé et MT5 ouvert (un VPS Windows évite les coupures, mais coûte quelques €/mois et ne se justifie qu'après le backtest). Arrêt : `Ctrl+C` (les stops restent chez le broker). Rapports : `python main.py report weekly`.

Routine hebdomadaire (30 min) : mettre à jour `news.csv`, lire le rapport, vérifier `logs/decisions.log`, ne **rien modifier** dans la stratégie en cours de test.

## 7. Protocole de validation avant tout passage au réel

| Étape | Durée | Critère de passage |
|---|---|---|
| 1. Tests automatiques | 1 min | 13 tests verts |
| 2. Backtest + walk-forward + holdout | 1 h | Stratégie `ACTIVE` : ≥ 60 trades test, PF ≥ 1,2, DD ≤ 15 %, ≥ 60 % de fenêtres gagnantes, holdout PF ≥ 1,1 |
| 3. Test technique (0,01 lot) | 1 semaine | Chaque ordre a un S/L, tailles correctes, alertes reçues, aucun bug |
| 4. Démo | **≥ 3 mois** | ≥ 100 trades cumulés (sinon prolonger), PF > 1,3, DD < 15 %, au moins 2 mois sur 3 positifs, aucune désactivation de sécurité, résultats proches du backtest |
| 5. Revue de l'écart démo/backtest | 1 semaine | Écart de PF < 25 % ; sinon retour à l'étape 2 |
| 6. Réel micro-capital | ≥ 3 mois | Capital que tu peux perdre **entièrement** sans conséquence (ex. ≤ 200–500 €), risque ramené à 0,5 %/trade |

**Ce que la démo cache** : exécution toujours parfaite, pas de vrai slippage (surtout aux news), spreads plus stables, pas de rejets d'ordres, pas de stress. Compte au moins 20–30 % de performance en moins en réel, et vérifie sur ton compte réel que spread et slippage réels ≤ ceux du backtest.

## 8. Pièges classiques et comment le bot les évite

| Piège | Pourquoi c'est dangereux | Dans ce bot |
|---|---|---|
| **Martingale** (doubler après une perte) | Un mauvais enchaînement détruit le compte | Absente ; la taille dépend uniquement du risque fixe de 1 % |
| **Grid sans stop** | Positions perdantes accumulées | Un seul trade par symbole, stop obligatoire |
| **Sur-optimisation** | Stratégie parfaite sur le passé, nulle demain | Grilles minuscules, walk-forward, holdout, seuil « hasard » |
| **Backtest trop beau** | Coûts ou triche sur le futur | Spread/commission/swap/slippage, exécution à la bougie suivante, test anti-triche |
| **Peu de trades** | Chance ≠ talent | ≥ 60 trades exigés, PF plafonné dans la note |
| **VPS / coupure** | Position sans surveillance | Stops chez le broker, alerte d'erreur, limites de perte |
| **Broker non régulé** | Retraits bloqués, prix truqués | Voir §9 |
| **Signaux « miracle » payants** | Résultats truqués, aucune garantie | Aucun signal externe ; tout est vérifiable dans `logs/` |
| **Levier excessif** | Perte rapide de tout le capital | Levier effectif ≤ 10 en backtest, marge limitée à 30 % |
| **Trader les news** | Slippage énorme | Filtre ±30 min |

## 9. Contexte France

- **Broker régulé** : vérifie qu'il est agréé **AMF/ACPR** (registre REGAFI) ou dans l'UE avec passeport européen (CySEC, etc.) et absent de la **liste noire de l'AMF**. Méfie-toi de tout broker qui promet de contourner le levier limité.
- **Levier ESMA (client particulier)** : 30:1 sur les paires Forex majeures, 20:1 sur les autres paires, l'or et les grands indices, 10:1 sur les autres matières premières, **2:1 sur les cryptos**. Protection contre le solde négatif et clôture automatique à 50 % de marge. Les « 500:1 » sont réservés aux entités offshore non protégées : à éviter.
- **Fiscalité** (à vérifier avec impots.gouv.fr ou un expert-comptable, je ne suis pas fiscaliste) : en principe, les gains de CFD/Forex d'un particulier sont des plus-values soumises au **prélèvement forfaitaire unique d'environ 30 %** (impôt + prélèvements sociaux, dont le taux a évolué récemment), déclarés avec le formulaire 2074 ; les comptes ouverts chez un broker **à l'étranger** se déclarent (formulaire 3916). Une activité très régulière peut être requalifiée en BNC. Garde le journal `logs/trades.csv` : il sert de justificatif. Les **pertes** ne sont déductibles que des gains du même type.
- **Risque de perte totale** : ne mets jamais d'argent dont tu as besoin (loyer, études). En démo il n'y a aucun risque financier.

## 10. Limites honnêtes de ce projet

- Testé uniquement sur **données synthétiques** (13 tests) : il prouve que la mécanique fonctionne et qu'elle refuse le hasard, **pas** que tu gagneras sur de vrais marchés.
- `mt5_io.py` n'a pas été exécuté contre un vrai MT5 (pas de Windows ici) : fais le test technique de l'étape 3.
- Valeur du pip et swaps fixes dans le backtest (en live, ce sont les vraies valeurs MT5) ; drawdown calculé sur les trades clôturés ; les news ne sont pas simulées en backtest.
- Les coûts d'exemple de `config.py` doivent être remplacés par ceux de ton broker.

## Mes 3 actions à faire cette semaine

1. Choisir un broker régulé (vérifier AMF/REGAFI), ouvrir un **compte démo MT5**, activer l'Algo Trading.
2. Installer Python, cloner le projet, lancer `python -m pytest -q` puis `python main.py download` et `python main.py select`; envoie-moi le résultat (même « NONE »).
3. Créer `data/news.csv` et le bot Telegram, puis faire le **test technique à 0,01 lot** (étape 3) en vérifiant le S/L sur chaque position.

## 3 questions pour affiner la suite

1. Quel système utilises-tu (Windows, Mac, Linux) et as-tu déjà choisi un broker ?
2. Préfères-tu garder H1 (peu de temps) ou tester aussi M15/H4 ?
3. Veux-tu inclure XAUUSD et BTCUSD dès maintenant, ou valider d'abord uniquement le Forex ?
