from __future__ import annotations

import logging
from threading import Event, Thread

from app.workspace.stock_planning.replenishment import StockReplenishmentService


_started = False


def start_stock_replenishment_scheduler() -> None:
    """Start one idempotent checker for the production single-worker process."""
    global _started
    if _started:
        return
    _started = True
    Thread(target=_loop, name="stock-replenishment", daemon=True).start()


def _loop() -> None:
    waiter = Event()
    waiter.wait(45)
    while True:
        try:
            StockReplenishmentService.run_due()
        except Exception:
            logging.getLogger(__name__).exception(
                "No fue posible ejecutar el reabastecimiento quincenal."
            )
        waiter.wait(6 * 60 * 60)
