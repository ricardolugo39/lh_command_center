from __future__ import annotations

from datetime import date

from flask import (
    Blueprint, abort, g, redirect, render_template, request, send_file,
    session, url_for,
)
from app.database.transaction import transaction

from app.auth import roles_required
from app.workspace.stock_planning.repository import StockPlanningRepository
from app.workspace.stock_planning.service import StockPlanningFoundationService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.exports import MIMETYPE, StockPlanningExportService
from app.workspace.stock_planning.replenishment import StockReplenishmentService


stock_planning_bp = Blueprint(
    "stock_planning", __name__, url_prefix="/stock-planning"
)


def _profile_id() -> int | None:
    raw = request.values.get("profile_id")
    return int(raw) if raw and raw.isdigit() else None


def _redirect(message: str = "", *, profile_id: int | None = None):
    parameters = {}
    if message:
        parameters["message"] = message
    if profile_id:
        parameters["profile_id"] = profile_id
    return redirect(url_for("stock_planning.index", **parameters))


@stock_planning_bp.get("/")
@roles_required("administrator")
def index():
    profile_id = _profile_id()
    if profile_id:
        session["stock_planning_profile_id"] = profile_id
    else:
        remembered = session.get("stock_planning_profile_id")
        profile_id = int(remembered) if str(remembered or "").isdigit() else None
    page = StockPlanningFoundationService.dashboard(profile_id)
    page["replenishment"] = StockReplenishmentService.inbox()
    return render_template(
        "stock_planning/index.html",
        page=page,
        message=request.args.get("message"),
    )


@stock_planning_bp.post("/replenishment/run")
@roles_required("administrator")
def run_replenishment():
    profile_code = request.form.get("profile_code", "")
    try:
        coverage_days = int(request.form.get("coverage_days", "90"))
        results = StockReplenishmentService.run_due(
            triggered_by=str(g.current_user["email"]), force=True,
            profile_code=profile_code, coverage_days=coverage_days,
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=_profile_id())
    completed = sum(item.get("status") == "completed" for item in results)
    skipped = sum(item.get("status") == "skipped" for item in results)
    return _redirect(
        f"Análisis de {profile_code.upper()} terminado con {coverage_days} días: "
        f"{completed} procesado y {skipped} omitido por datos incompletos.",
        profile_id=_profile_id(),
    )


@stock_planning_bp.post("/replenishment/requests/<int:request_id>/status")
@roles_required("administrator")
def update_import_request(request_id: int):
    status = request.form.get("status", "")
    if status not in {"reviewed", "dismissed", "resolved"}:
        abort(400)
    with transaction(write=True) as connection:
        connection.execute(
            """UPDATE stock_planning_import_requests
            SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (status, request_id),
        )
    return _redirect("Solicitud actualizada.", profile_id=_profile_id())


@stock_planning_bp.post("/vendors")
@roles_required("administrator")
def create_vendor():
    try:
        profile_id = StockPlanningFoundationService.create_vendor_profile(
            vendor_name=request.form.get("vendor_name"),
            profile_code=request.form.get("profile_code"),
            inventory_brand_codes=_csv(request.form.get("inventory_brand_codes")),
            sales_suffixes=_csv(request.form.get("sales_suffixes")),
            default_manufacturing_days=_optional_int("default_manufacturing_days"),
            default_shipping_days=_optional_int("default_shipping_days"),
            default_receiving_days=_optional_int("default_receiving_days"),
            default_cali_transfer_days=_optional_int("default_cali_transfer_days"),
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception))
    return _redirect("Proveedor configurado.", profile_id=profile_id)


@stock_planning_bp.post("/branches")
@roles_required("administrator")
def save_branch():
    try:
        StockPlanningFoundationService.register_branch(
            branch_code=request.form.get("branch_code"),
            branch_name=request.form.get("branch_name"),
            is_primary_receipt=bool(request.form.get("is_primary_receipt")),
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=_profile_id())
    return _redirect("Bodega configurada.", profile_id=_profile_id())


@stock_planning_bp.post("/catalog")
@roles_required("administrator")
def save_catalog_product():
    profile_id = _profile_id()
    if not profile_id:
        return _redirect("Seleccione un proveedor.")
    try:
        StockPlanningFoundationService.register_catalog_product(
            profile_id,
            internal_sku=request.form.get("internal_sku"),
            vendor_sku=request.form.get("vendor_sku"),
            product_name=request.form.get("product_name"),
            purchase_uom=request.form.get("purchase_uom"),
            units_per_pack=_optional_float("units_per_pack"),
            source="ui",
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return _redirect("Producto guardado.", profile_id=profile_id)


@stock_planning_bp.post("/transit")
@roles_required("administrator")
def save_transit():
    profile_id = _profile_id()
    if not profile_id:
        return _redirect("Seleccione un proveedor.")
    try:
        StockPlanningFoundationService.register_transit_supply(
            profile_id,
            branch_code=request.form.get("branch_code"),
            internal_sku=request.form.get("internal_sku"),
            quantity=float(request.form.get("quantity") or 0),
            expected_date=request.form.get("expected_date") or None,
            purchase_order_reference=request.form.get("purchase_order_reference") or None,
            source="ui",
            created_by=str(g.current_user["email"]),
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return _redirect("Tránsito registrado.", profile_id=profile_id)


@stock_planning_bp.post("/families")
@roles_required("administrator")
def save_family():
    profile_id = _profile_id()
    if not profile_id:
        return _redirect("Seleccione un proveedor.")
    try:
        StockPlanningFoundationService.register_family(
            profile_id,
            family_code=request.form.get("family_code"),
            family_name=request.form.get("family_name"),
            source="ui",
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return _redirect("Familia guardada.", profile_id=profile_id)


@stock_planning_bp.post("/family-members")
@roles_required("administrator")
def save_family_member():
    profile_id = _profile_id()
    try:
        StockPlanningFoundationService.register_family_member(
            int(request.form.get("family_id") or 0),
            internal_sku=request.form.get("internal_sku"),
            relationship_role=request.form.get("relationship_role") or "member",
            source="ui", reviewed_by=str(g.current_user["email"]),
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return _redirect("Producto agregado a la familia.", profile_id=profile_id)


@stock_planning_bp.post("/transformations")
@roles_required("administrator")
def save_transformation():
    profile_id = _profile_id()
    if not profile_id:
        return _redirect("Seleccione un proveedor.")
    try:
        StockPlanningFoundationService.register_transformation(
            profile_id,
            transformation_code=request.form.get("transformation_code"),
            transformation_type=request.form.get("transformation_type"),
            purchase_sku=request.form.get("purchase_sku"),
            purchase_quantity=float(request.form.get("purchase_quantity") or 1),
            waste_rate=float(request.form.get("waste_rate") or 0) / 100,
            status="draft",
            created_by=str(g.current_user["email"]),
            inputs=[{
                "sales_sku": request.form.get("sales_sku"),
                "sales_quantity": float(request.form.get("sales_quantity") or 1),
                "normalized_consumption": float(
                    request.form.get("normalized_consumption") or 0
                ),
            }],
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return _redirect("Transformación guardada como borrador.", profile_id=profile_id)


@stock_planning_bp.post("/snapshots")
@roles_required("administrator")
def create_snapshot():
    profile_id = _profile_id()
    if not profile_id:
        return _redirect("Seleccione un proveedor.")
    session["stock_planning_profile_id"] = profile_id
    profile = StockPlanningRepository.get_vendor_profile(profile_id)
    if profile and profile.get("planning_purpose") == "replenishment":
        return _redirect(
            "Esta marca se analiza desde Reabastecimiento quincenal; no genera pedidos de proveedor.",
            profile_id=profile_id,
        )
    try:
        snapshot = StockPlanningFoundationService.create_snapshot(
            profile_id=profile_id,
            as_of_date=date.today(),
            created_by=str(g.current_user["email"]),
            assumptions={
                "manufacturing_days": request.form.get("manufacturing_days"),
                "international_shipping_days": request.form.get(
                    "international_shipping_days"
                ),
                "receiving_days": request.form.get("receiving_days"),
                "cali_transfer_days": request.form.get("cali_transfer_days"),
                "coverage_months": request.form.get("coverage_months"),
            },
        )
    except (TypeError, ValueError) as exception:
        return _redirect(str(exception), profile_id=profile_id)
    return redirect(url_for("stock_planning.snapshot", snapshot_id=snapshot.snapshot_id))


@stock_planning_bp.post("/snapshots/<int:snapshot_id>/archive")
@roles_required("administrator")
def archive_snapshot(snapshot_id: int):
    archived = StockPlanningRepository.archive_snapshot(
        snapshot_id, str(g.current_user["email"])
    )
    if not archived:
        abort(404)
    session["stock_planning_profile_id"] = archived["vendor_profile_id"]
    return _redirect(
        "Análisis eliminado de la lista. La evidencia se conserva para auditoría.",
        profile_id=archived["vendor_profile_id"],
    )


@stock_planning_bp.get("/snapshots/<int:snapshot_id>")
@roles_required("administrator")
def snapshot(snapshot_id: int):
    page = StockPlanningRepository.snapshot_detail(snapshot_id)
    if not page:
        abort(404)
    if page["snapshot"].get("planning_purpose") == "replenishment":
        return redirect(url_for(
            "stock_planning.replenishment_report", snapshot_id=snapshot_id
        ))
    page["forecast"] = (
        _present_forecast(StockPlanningDecisionService.present(
            snapshot_id, StockForecastEngine.analyze(snapshot_id)
        ))
        if page["inputs"] else None
    )
    page["message"] = request.args.get("message")
    return render_template("stock_planning/snapshot.html", page=page)


@stock_planning_bp.get("/replenishment/reports/<int:snapshot_id>")
@roles_required("administrator")
def replenishment_report(snapshot_id: int):
    page = StockPlanningRepository.snapshot_detail(snapshot_id)
    if not page or page["snapshot"].get("planning_purpose") != "replenishment":
        abort(404)
    page["replenishment"] = StockReplenishmentService.report(snapshot_id)
    page["message"] = request.args.get("message")
    return render_template("stock_planning/replenishment_report.html", page=page)


@stock_planning_bp.get("/snapshots/<int:snapshot_id>/products/<path:sku>")
@roles_required("administrator")
def product_analysis(snapshot_id: int, sku: str):
    page = StockPlanningRepository.snapshot_detail(snapshot_id)
    if not page or not page["inputs"]:
        abort(404)
    branch = str(request.args.get("branch", "1"))
    forecast = StockPlanningDecisionService.present(
        snapshot_id, StockForecastEngine.analyze(snapshot_id)
    )
    row = next(
        (item for item in forecast["rows"]
         if item["sku"] == sku.upper() and item["branch"] == branch),
        None,
    )
    if not row:
        abort(404)
    try:
        movement_months = int(request.args.get("months", "36"))
    except ValueError:
        movement_months = 36
    movements = StockPlanningRepository.product_sales_movements(
        snapshot_id, sku, branch, movement_months
    )
    customer_units = {}
    for movement in movements["rows"]:
        name = movement["customer_name"]
        customer_units[name] = customer_units.get(name, 0) + max(
            float(movement["quantity"]), 0
        )
    largest_customer = max(customer_units, key=customer_units.get) if customer_units else None
    high_quantity = max(2.0, float(row["monthly_forecast"]) * 3)
    for movement in movements["rows"]:
        movement["is_return"] = float(movement["quantity"]) < 0
        movement["is_high_quantity"] = float(movement["quantity"]) >= high_quantity
        movement["is_main_customer"] = (
            largest_customer is not None
            and movement["customer_name"] == largest_customer
            and float(row["customer_concentration"]) >= .70
        )
    return render_template(
        "stock_planning/product_analysis.html", page=page, result=row,
        movements=movements, message=request.args.get("message"),
    )


@stock_planning_bp.post("/snapshots/<int:snapshot_id>/purchase-decisions")
@roles_required("administrator")
def save_purchase_decision(snapshot_id: int):
    sku = request.form.get("sku", "")
    branch = request.form.get("branch", "")
    try:
        StockPlanningDecisionService.save_purchase(
            snapshot_id, sku, branch, float(request.form.get("quantity", "")),
            str(g.current_user["email"]), request.form.get("note", ""),
        )
        message = "Decisión de compra guardada."
    except (TypeError, ValueError) as exception:
        message = str(exception)
    if request.form.get("return_to") == "product":
        return redirect(url_for(
            "stock_planning.product_analysis", snapshot_id=snapshot_id,
            sku=sku, branch=branch, message=message,
            _anchor="purchase-decision",
        ))
    return redirect(url_for(
        "stock_planning.snapshot", snapshot_id=snapshot_id, message=message,
        _anchor="purchase-decisions",
    ))


@stock_planning_bp.post("/snapshots/<int:snapshot_id>/transfer-decisions")
@roles_required("administrator")
def save_transfer_decision(snapshot_id: int):
    try:
        StockPlanningDecisionService.save_transfer(
            snapshot_id, request.form.get("sku", ""),
            request.form.get("from_branch", ""), request.form.get("to_branch", ""),
            float(request.form.get("quantity", "")), str(g.current_user["email"]),
            request.form.get("note", ""),
        )
        message = "Decisión de traslado guardada."
    except (TypeError, ValueError) as exception:
        message = str(exception)
    endpoint = (
        "stock_planning.replenishment_report"
        if request.form.get("return_to") == "replenishment"
        else "stock_planning.snapshot"
    )
    parameters = {"snapshot_id": snapshot_id, "message": message}
    if endpoint == "stock_planning.snapshot":
        parameters["_anchor"] = "transfer-decisions"
    return redirect(url_for(endpoint, **parameters))


@stock_planning_bp.post("/snapshots/<int:snapshot_id>/transfer-decisions/approve-all")
@roles_required("administrator")
def approve_all_transfers(snapshot_id: int):
    count = StockPlanningDecisionService.approve_all_transfers(
        snapshot_id, str(g.current_user["email"])
    )
    return redirect(url_for(
        "stock_planning.snapshot", snapshot_id=snapshot_id,
        message=f"{count} traslado(s) aprobados.",
        _anchor="transfer-decisions",
    ))


@stock_planning_bp.get("/snapshots/<int:snapshot_id>/exports/purchase-order.xlsx")
@roles_required("administrator")
def export_purchase_order(snapshot_id: int):
    try:
        stream, filename = StockPlanningExportService.purchase_order(snapshot_id)
    except ValueError as exception:
        return redirect(url_for(
            "stock_planning.snapshot", snapshot_id=snapshot_id, message=str(exception)
        ))
    return send_file(stream, mimetype=MIMETYPE, as_attachment=True, download_name=filename)


@stock_planning_bp.get("/snapshots/<int:snapshot_id>/exports/transfers.xlsx")
@roles_required("administrator")
def export_transfers(snapshot_id: int):
    try:
        stream, filename = StockPlanningExportService.transfers(snapshot_id)
    except ValueError as exception:
        return redirect(url_for(
            "stock_planning.snapshot", snapshot_id=snapshot_id, message=str(exception)
        ))
    return send_file(stream, mimetype=MIMETYPE, as_attachment=True, download_name=filename)


@stock_planning_bp.get(
    "/snapshots/<int:snapshot_id>/exports/replenishment-uncovered.xlsx"
)
@roles_required("administrator")
def export_replenishment_uncovered(snapshot_id: int):
    try:
        stream, filename = StockPlanningExportService.replenishment_uncovered(
            snapshot_id
        )
    except ValueError as exception:
        return redirect(url_for(
            "stock_planning.replenishment_report", snapshot_id=snapshot_id,
            message=str(exception),
        ))
    return send_file(
        stream, mimetype=MIMETYPE, as_attachment=True, download_name=filename
    )


def _present_forecast(forecast: dict) -> dict:
    """Organize immutable engine evidence for an operational decision screen."""
    rows = forecast["rows"]
    forecast["actionable_review"] = [
        row for row in rows
        if row["recommended_order"] > 0 and row["requires_review"]
    ]
    forecast["suggested"] = [
        row for row in rows
        if row["recommended_order"] > 0 and not row["requires_review"]
    ]
    forecast["no_order"] = [
        row for row in rows if row["recommended_order"] == 0
    ]
    category_rows = {}
    for row in rows:
        category = row["abc"] + row["xyz"]
        summary = category_rows.setdefault(category, {
            "category": category, "products": set(), "order_units": 0,
            "review": 0,
        })
        summary["products"].add(row["sku"])
        summary["order_units"] += row["recommended_order"]
        if row["recommended_order"] > 0 and row["requires_review"]:
            summary["review"] += 1
    forecast["categories"] = [
        {**summary, "products": len(summary["products"])}
        for _, summary in sorted(category_rows.items())
    ]
    return forecast


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _optional_int(name: str) -> int | None:
    value = request.form.get(name)
    return int(value) if value else None


def _optional_float(name: str) -> float | None:
    value = request.form.get(name)
    return float(value) if value else None
