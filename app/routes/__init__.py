from app.routes.home import home_bp
from app.routes.purchase_history import (
    purchase_history_bp,
)
from app.routes.workspace import (
    workspace_bp,
)
from app.routes.imports import imports_bp
from app.routes.activities import activities_bp
from app.routes.rfqs import rfqs_bp
from app.routes.integrations import integrations_bp
from app.routes.ask import ask_bp
from app.routes.quotes import quotes_bp
from app.routes.stock_planning import stock_planning_bp


def register_blueprints(app):

    app.register_blueprint(home_bp)

    app.register_blueprint(
        purchase_history_bp
    )

    app.register_blueprint(
        workspace_bp
    )

    app.register_blueprint(imports_bp)
    app.register_blueprint(activities_bp)
    app.register_blueprint(rfqs_bp)
    app.register_blueprint(integrations_bp)
    app.register_blueprint(ask_bp)
    app.register_blueprint(quotes_bp)
    app.register_blueprint(stock_planning_bp)
