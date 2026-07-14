from app.routes.home import home_bp
from app.routes.purchase_history import (
    purchase_history_bp,
)
from app.routes.workspace import (
    workspace_bp,
)


def register_blueprints(app):

    app.register_blueprint(home_bp)

    app.register_blueprint(
        purchase_history_bp
    )

    app.register_blueprint(
        workspace_bp
    )