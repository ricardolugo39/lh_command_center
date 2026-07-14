from flask import Flask

from app.routes import register_blueprints
from app.routes.api.customers import customers_api


app = Flask(
    __name__,
    template_folder="app/templates",
    static_folder="app/static",
)

register_blueprints(app)
app.register_blueprint(customers_api)


if __name__ == "__main__":
    app.run(debug=True)