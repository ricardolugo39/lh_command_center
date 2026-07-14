from flask import Blueprint
from flask import render_template

from app.services.purchase_history_service import (
    PurchaseHistoryService,
)

purchase_history_bp = Blueprint(
    "purchase_history",
    __name__,
)


@purchase_history_bp.route(
    "/purchase-history"
)
def purchase_history():

    df = PurchaseHistoryService.get_history(
        customer="CARTONES AMERICA S.A.",
        family_id="5000",
        group_id="5070",
        months=18,
    )

    return render_template(
        "purchase_history.html",
        rows=df.to_dict(orient="records"),
    )