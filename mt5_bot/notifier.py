"""notifier.py - Alertes Telegram (et journal si Telegram n'est pas configuré)."""
import json
import logging
import os
import urllib.request

log = logging.getLogger("bot")


def send(text: str):
    """Envoie un message Telegram. Variables d'environnement : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    log.info("ALERTE: %s", text.replace("\n", " | "))
    if not token or not chat:
        return
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text[:4000]}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:                       # une alerte qui échoue ne doit jamais faire planter le bot
        log.warning("Telegram indisponible: %s", e)
