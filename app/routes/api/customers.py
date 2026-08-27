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

    limit = min(max(request.args.get("limit", 10, type=int), 1), 20)
    if request.args.get("scope") == "workspace":
        customers = CustomerLookupRepository.search_workspace_customers(
            text=query, limit=limit,
        )
    else:
        customers = CustomerLookupRepository.search(text=query, limit=limit)

    return jsonify(customers)
