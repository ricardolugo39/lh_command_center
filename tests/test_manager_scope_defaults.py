from flask import Flask

from app.routes.workspace import _requested_office


def test_manager_scope_defaults_to_configured_office_when_missing():
    app = Flask(__name__)
    app.config["DEFAULT_COMMERCIAL_OFFICE"] = "Cali"

    with app.test_request_context("/workspace/projects"):
        assert _requested_office() == "Cali"


def test_manager_scope_preserves_explicit_consolidated_or_other_office():
    app = Flask(__name__)
    app.config["DEFAULT_COMMERCIAL_OFFICE"] = "Cali"

    with app.test_request_context("/workspace/projects?office="):
        assert _requested_office() == ""

    with app.test_request_context("/workspace/projects?office=Bogot%C3%A1"):
        assert _requested_office() == "Bogotá"
