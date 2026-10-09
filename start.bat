@echo off
rem Installe tout et lance le bot (Windows). Double-clique sur ce fichier.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe. Installe-le depuis https://www.python.org/downloads
  echo en cochant "Add Python to PATH", puis relance ce fichier.
  pause
  exit /b 1
)

if not exist .venv (
  echo ^>^> Creation de l'environnement Python...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo ^>^> Installation des dependances...
pip install -q -r requirements.txt

if not exist .env (
  echo.
  echo ^>^> Configuration ^(une seule fois^). Cles Alpaca PAPER : https://app.alpaca.markets
  set /p AK=ALPACA_API_KEY :
  set /p SK=ALPACA_SECRET_KEY :
  set /p CK=Cle Anthropic ^(laisse vide pour desactiver la strategie Claude^) :
  > .env echo ALPACA_API_KEY=%AK%
  >> .env echo ALPACA_SECRET_KEY=%SK%
  if "%CK%"=="" (
    >> .env echo ENABLE_CLAUDE=false
  ) else (
    >> .env echo ANTHROPIC_API_KEY=%CK%
  )
  echo ^>^> .env cree.
)

echo ^>^> Lancement du bot ^(Ctrl+C pour arreter^)
python bot.py run
pause
