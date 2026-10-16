from __future__ import annotations

import logging
from threading import Event, Thread

from flask import Flask

from app.workspace.services.initiative_campaign_service import (
    InitiativeCampaignService,
)


_started = False
_INITIAL_DELAY_SECONDS = 60
_INTERVAL_SECONDS = 60 * 60


def start_initiative_campaign_scheduler(application: Flask) -> None:
    global _started
    if _started:
        return
    _started = True
    Thread(
        target=_loop,
        args=(application,),
        name="initiative-campaign-sync",
        daemon=True,
    ).start()


def _loop(application: Flask) -> None:
    waiter = Event()
    waiter.wait(_INITIAL_DELAY_SECONDS)
    while True:
        try:
            with application.app_context():
                result = InitiativeCampaignService.sync_all_from_onedrive()
                application.logger.info(
                    "Sincronización horaria de campañas: %s", result
                )
        except Exception:
            logging.exception("Falló la sincronización horaria de campañas")
        waiter.wait(_INTERVAL_SECONDS)
