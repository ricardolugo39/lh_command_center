from flask import Flask, render_template
from app.services.purchase_history_service import PurchaseHistoryService
from pathlib import Path
from flask import request
from werkzeug.utils import secure_filename


app = Flask(

    __name__,

    template_folder="app/templates",

    static_folder="app/static",

)


@app.route("/purchase-history")
def purchase_history():
    df = PurchaseHistoryService.get_history(
        customer="CARTONES AMERICA S.A.",
        family_id="5000",
        group_id="5070",
        months=18,
    )

    rows = df.to_dict(orient="records")

    return render_template(
        "purchase_history.html",
        rows=rows,
    )

@app.route("/")
def home():
    return """
    <h1>Commercial Command Center</h1>
    <p>Version 0.1</p>
    <p>Sprint 0</p>
    """

if __name__ == "__main__":
    app.run(debug=True)