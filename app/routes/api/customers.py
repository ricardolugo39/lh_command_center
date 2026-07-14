from flask import Blueprint, jsonify, request

from app.workspace.repositories.customer_lookup_repository import (
    CustomerLookupRepository,
)

customers_api = Blueprint(
    "customers_api",
    __name__,
)


@customers_api.get("/api/customers/search")
def search_customers():

    query = request.args.get(
        "q",
        "",
    )

    customers = CustomerLookupRepository.search(
        text=query,
        limit=20,
    )

    return jsonify(customers)