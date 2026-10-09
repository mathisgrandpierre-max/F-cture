#!/usr/bin/env bash
# Installe tout et lance le bot (Mac / Linux). Usage : ./start.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 n'est pas installé. Installe-le depuis https://www.python.org/downloads puis relance."
  exit 1
fi

if [ ! -d .venv ]; then
  echo ">> Création de l'environnement Python..."
  python3 -m venv .venv
fi
source .venv/bin/activate

echo ">> Installation des dépendances..."
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo
  echo ">> Configuration (une seule fois). Clés Alpaca PAPER : https://app.alpaca.markets"
  read -r -p "ALPACA_API_KEY : " ak
  read -r -s -p "ALPACA_SECRET_KEY (invisible) : " sk
  echo
  read -r -p "Clé Anthropic (laisse vide pour désactiver la stratégie Claude) : " ck
  {
    echo "ALPACA_API_KEY=$ak"
    echo "ALPACA_SECRET_KEY=$sk"
    if [ -z "$ck" ]; then
      echo "ENABLE_CLAUDE=false"
    else
      echo "ANTHROPIC_API_KEY=$ck"
    fi
  } > .env
  chmod 600 .env
  echo ">> .env créé."
fi

echo ">> Lancement du bot (Ctrl+C pour arrêter)"
python bot.py run
