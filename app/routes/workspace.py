from app.workspace.services.initiative_service import (
    InitiativeService,
)

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
     send_file,
)

from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.repositories.project_repository import (
    ProjectRepository,
)
from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)

from app.workspace.repositories.followup_repository import (
    FollowupRepository,
)
from app.workspace.repositories.activity_repository import ActivityRepository

from app.workspace.services.quote_service import (
    QuoteService,
)
from app.workspace.services.commercial_interest_quote_service import (
    CommercialInterestQuoteService,
)

from app.workspace.services.workspace_dashboard_service import (
    WorkspaceDashboardService,
)

from app.workspace.services.customer_detail_service import (
    CustomerDetailService,
)

from app.workspace.repositories.initiative_repository import (
    InitiativeRepository,
)


from app.workspace.services.project_file_service import (

    ProjectFileService,

)

from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.services.agreement_service import (
    AgreementService,
)

from app.workspace.services.project_closure_service import (
    ProjectClosureService,
)
from app.workspace.services.opportunity_list_service import (
    OpportunityListService,
)
from app.workspace.services.opportunity_bulk_service import (
    OpportunityBulkUpdateService,
)
from app.workspace.services.opportunity_export_service import (
    OpportunityExportService,
)
from app.workspace.services.strategic_account_service import (
    StrategicAccountService,
)
from app.workspace.services.company_sales_dashboard_service import CompanySalesDashboardService
from app.workspace.services.agreement_import_service import (
    AgreementImportError,
    AgreementImportService,
)
from app.workspace.services.customer_portfolio_service import (
    CustomerPortfolioService,
)
from app.workspace.services.commercial_approval_service import (
    CommercialApprovalService,
)
from app.workspace.services.commercial_visit_service import CommercialVisitService
from app.workspace.repositories.contact_repository import ActivityFormRepository
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.rfq_service import RFQService
from app.auth import roles_required

workspace_bp = Blueprint(
    "workspace",
    __name__,
)


@workspace_bp.route("/workspace/projects")
def project_list():
    query = request.args.to_dict()
    query.setdefault("office", _default_office())
    page = OpportunityListService.get_page(query)

    return render_template(
        "workspace/project_list.html",
        page=page,
    )


@workspace_bp.get("/workspace/projects/export.xlsx")
@roles_required("administrator", "commercial_management", "advisor")
def project_list_export():
    query = request.args.to_dict()
    query.setdefault("office", _default_office())
    stream, filename = OpportunityExportService.build(query)
    return send_file(
        stream,
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        as_attachment=True,
        download_name=filename,
    )


@workspace_bp.post("/workspace/projects/bulk-update")
@roles_required("administrator", "commercial_management", "advisor")
def project_bulk_update():
    try:
        result = OpportunityBulkUpdateService.apply(
            project_ids=[
                int(value) for value in request.form.getlist("project_ids")
            ],
            new_status=request.form.get("new_status", ""),
            followup_date=request.form.get("followup_date", ""),
            followup_description=request.form.get("followup_description", ""),
            actor=current_app.config.get("CURRENT_USER", "system"),
        )
    except (TypeError, ValueError) as exc:
        return str(exc), 400
    filters = {
        key: request.form.get(key, "")
        for key in (
            "status", "include_closed", "origin", "sales_rep",
            "office", "health", "customer_name", "attention",
        )
        if request.form.get(key, "")
    }
    return redirect(url_for(
        "workspace.project_list",
        **filters,
        bulk_updated=result["selected"],
        statuses_updated=result["changed_statuses"],
        followups_created=result["created_followups"],
    ))


@workspace_bp.get("/analytics/sales")
def company_sales_dashboard():
    page = CompanySalesDashboardService.get_page(
        _requested_office()
    )
    return render_template("workspace/company_sales_dashboard.html", page=page)


@workspace_bp.route("/workspace/projects/<int:project_id>")
def project_detail(project_id: int):
    try:
        workspace = ProjectWorkspaceService.get_workspace(
            project_id
        )
    except ValueError:
        abort(404)

    return render_template(
        "workspace/project_detail.html",
        workspace=workspace,
    )


@workspace_bp.get("/workspace/projects/<int:project_id>/approvals")
def commercial_approval_list(project_id: int):
    try:
        page = CommercialApprovalService.get_page(
            project_id,status=request.args.get("status","").strip(),
            page=max(request.args.get("page",1,type=int),1))
    except ValueError:
        abort(404)
    return render_template("workspace/commercial_approval_list.html",page=page)


@workspace_bp.route("/workspace/projects/<int:project_id>/approvals/new",methods=["GET","POST"])
def commercial_approval_new(project_id: int):
    try:
        workspace = ProjectWorkspaceService.get_workspace(project_id)
    except ValueError:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            approval_id = CommercialApprovalService.create(
                project_id,request.form.to_dict(),actor=current_app.config.get("CURRENT_USER","system"))
            return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id))
        except (ValueError,TypeError) as exc:error=str(exc)
    defaults = request.form if request.method == "POST" else CommercialApprovalService.get_form_defaults(project_id)
    return render_template("workspace/commercial_approval_form.html",workspace=workspace,
                           approval=None,reasons=CommercialApprovalService.REASONS,
                           form_data=defaults,error=error)


@workspace_bp.route("/workspace/approvals/<int:approval_id>/edit",methods=["GET","POST"])
def commercial_approval_edit(approval_id: int):
    try:
        page=CommercialApprovalService.get_detail(approval_id)
        workspace=ProjectWorkspaceService.get_workspace(page["approval"]["project_id"])
        if request.method == "POST":
            CommercialApprovalService.update(approval_id,request.form.to_dict(),actor=current_app.config.get("CURRENT_USER","system"))
            return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id))
    except ValueError as exc:
        if request.method == "POST":
            return render_template("workspace/commercial_approval_form.html",workspace=workspace,
                approval=page["approval"],reasons=CommercialApprovalService.REASONS,
                form_data=request.form,error=str(exc)),400
        abort(404)
    return render_template("workspace/commercial_approval_form.html",workspace=workspace,
        approval=page["approval"],reasons=CommercialApprovalService.REASONS,
        form_data=page["approval"],error=None)


@workspace_bp.get("/workspace/approvals/<int:approval_id>")
def commercial_approval_detail(approval_id: int):
    try:page=CommercialApprovalService.get_detail(approval_id)
    except ValueError:abort(404)
    return render_template("workspace/commercial_approval_detail.html",page=page,
        approval_updated=request.args.get("updated")=="1",
        updated_amount=request.args.get("amount"),
        updated_currency=request.args.get("currency"))


@workspace_bp.post("/workspace/approvals/<int:approval_id>/submit")
def commercial_approval_submit(approval_id: int):
    try:CommercialApprovalService.submit(approval_id,actor=current_app.config.get("CURRENT_USER","system"))
    except ValueError as exc:return str(exc),400
    return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id))


@workspace_bp.post("/workspace/approvals/<int:approval_id>/decision")
def commercial_approval_decision(approval_id: int):
    try:
        discount=request.form.get("approved_discount","").strip()
        result=CommercialApprovalService.decide(approval_id,decision=request.form.get("decision",""),
            approver=CommercialApprovalService.APPROVER_NAME,comments=request.form.get("comments",""),
            approved_discount=discount or None,
            expiration_date=request.form.get("expiration_date") or None,
            role="approver")
    except (ValueError,PermissionError) as exc:return str(exc),403 if isinstance(exc,PermissionError) else 400
    return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id,
                            updated=1 if result else 0,
                            amount=result.get("approved_total_amount") if result else None,
                            currency=result.get("currency") if result else None))


@workspace_bp.post("/workspace/approvals/<int:approval_id>/cancel")
def commercial_approval_cancel(approval_id: int):
    try:CommercialApprovalService.cancel(approval_id,actor=current_app.config.get("CURRENT_USER","system"),comments=request.form.get("comments",""))
    except ValueError as exc:return str(exc),400
    return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id))


@workspace_bp.post("/workspace/approvals/<int:approval_id>/expire")
def commercial_approval_expire(approval_id: int):
    try:
        CommercialApprovalService.expire(
            approval_id, actor=CommercialApprovalService.APPROVER_NAME,
            role="approver")
    except (ValueError,PermissionError) as exc:
        return str(exc),403 if isinstance(exc,PermissionError) else 400
    return redirect(url_for("workspace.commercial_approval_detail",approval_id=approval_id))


@workspace_bp.route("/workspace/customers")
def customer_list():
    page = CustomerPortfolioService.get_dashboard(
        search=request.args.get("q", "").strip(),
        quick_filter=request.args.get("filter", "").strip(),
        office=_requested_office(),
        advisor=request.args.get("advisor", "").strip(),
        current_advisor=current_app.config.get("CURRENT_SALES_REP"),
        sort=request.args.get("sort", "sales").strip(),
        direction=request.args.get("direction", "desc").strip(),
        page=max(request.args.get("page", 1, type=int), 1),
    )

    return render_template(
        "workspace/customer_list.html",
        page=page,
    )


def _default_office() -> str:
    return str(
        current_app.config.get("DEFAULT_COMMERCIAL_OFFICE", "Cali") or ""
    ).strip()


def _requested_office() -> str:
    if "office" in request.args:
        return request.args.get("office", "").strip()
    return _default_office()


@workspace_bp.get("/workspace/customers/erp/<erp_customer_id>")
def open_erp_customer(erp_customer_id: str):
    try:
        customer_id = CustomerPortfolioService.resolve_workspace(erp_customer_id)
    except ValueError:
        abort(404)
    return redirect(url_for("workspace.strategic_account_overview",
                            customer_id=customer_id))

@workspace_bp.route(
    "/workspace/projects/new",
    methods=["GET", "POST"],
)
def new_project():
    error = None
    form_data = request.form.to_dict() if request.method == "POST" else request.args.to_dict()

    if request.method == "POST":
        try:
            brands = request.form.getlist("brands")

            other_brand = request.form.get(
                "other_brand",
                "",
            ).strip()

            if other_brand:
                brands.append(other_brand)

            quote_amount_text = request.form.get(
                "quote_amount",
                "",
            ).strip()

            quote_amount = (
                float(quote_amount_text)
                if quote_amount_text
                else None
            )

            workspace = (
                ProjectWorkspaceService.create_project_mvp(
                    erp_customer_id=request.form.get(
                        "customer_id",
                        "",
                    ),
                    customer_site_id=request.form.get(
                        "customer_site_id",
                        "",
                    ),
                    project_name=request.form.get(
                        "project_name",
                        "",
                    ),
                    objective=request.form.get(
                        "objective",
                        "",
                    ),
                    sales_rep=request.form.get(
                        "sales_rep",
                        "",
                    ),
                    status=request.form.get(
                        "status",
                        "prospect",
                    ),
                    proposed_solution=request.form.get(
                        "proposed_solution",
                        "",
                    ),
                    current_blocker=request.form.get(
                        "current_blocker",
                        "",
                    ),
                    brands=brands,
                    quote_prefix=request.form.get(
                        "quote_prefix",
                        "CTC",
                    ),
                    quote_number=request.form.get(
                        "quote_number",
                        "",
                    ),
                    quote_date=request.form.get(
                        "quote_date",
                        "",
                    ),
                    quote_amount=quote_amount,
                    source_visit_id=request.form.get("source_visit_id",type=int),
                )
            )

            return redirect(
                url_for(
                    "workspace.project_detail",
                    project_id=workspace["project"]["id"],
                )
            )

        except ValueError as exc:
            error = str(exc)

    return render_template(
        "workspace/new_project.html",
        error=error,
        form_data=form_data,
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/activity"
)
def add_project_activity(project_id: int):
    try:
        ProjectWorkspaceService.add_activity(
            project_id=project_id,
            activity_type=request.form.get(
                "activity_type",
                "",
            ),
            details=request.form.get(
                "details",
                "",
            ),
            followup_due_date=request.form.get(
                "followup_due_date"
            ) or None,
            followup_description=request.form.get(
                "followup_description"
            ) or None,
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )

@workspace_bp.route(
    "/workspace/projects/<int:project_id>/edit",
    methods=["GET", "POST"],
)
def edit_project(project_id: int):
    try:
        workspace = ProjectWorkspaceService.get_workspace(
            project_id
        )
    except ValueError:
        abort(404)

    if workspace["is_read_only"]:
        return redirect(
            url_for(
                "workspace.project_detail",
                project_id=project_id,
            )
        )

    error = None

    if request.method == "POST":
        try:
            brands = request.form.getlist("brands")

            other_brand = request.form.get(
                "other_brand",
                "",
            ).strip()

            if other_brand:
                brands.append(other_brand)

            quote_amount_text = request.form.get(
                "quote_amount",
                "",
            ).strip()

            quote_amount = (
                float(quote_amount_text)
                if quote_amount_text
                else None
            )

            ProjectWorkspaceService.update_project_details(
                project_id=project_id,
                project_name=request.form.get(
                    "project_name",
                    "",
                ),
                objective=request.form.get(
                    "objective",
                    "",
                ),
                proposed_solution=request.form.get(
                    "proposed_solution",
                    "",
                ),
                current_blocker=request.form.get(
                    "current_blocker",
                    "",
                ),
                sales_rep=request.form.get(
                    "sales_rep",
                    "",
                ),
                brands=brands,
                quote_prefix=request.form.get(
                    "quote_prefix",
                    "CTC",
                ),
                quote_number=request.form.get(
                    "quote_number",
                    "",
                ),
                quote_date=request.form.get(
                    "quote_date",
                    "",
                ),
                quote_amount=quote_amount,
            )

            return redirect(
                url_for(
                    "workspace.project_detail",
                    project_id=project_id,
                )
            )

        except ValueError as exc:
            error = str(exc)

            workspace = (
                ProjectWorkspaceService.get_workspace(
                    project_id
                )
            )

    return render_template(
        "workspace/edit_project.html",
        workspace=workspace,
        error=error,
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/status"
)
def change_project_status(project_id: int):
    try:
        ProjectWorkspaceService.change_status(
            project_id=project_id,
            new_status=request.form.get(
                "new_status",
                "",
            ),
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )

@workspace_bp.post(
    "/workspace/followups/<int:followup_id>/complete"
)
def complete_followup(followup_id: int):

    followup = FollowupRepository.get_followup(
        followup_id
    )

    if followup is None:
        abort(404)

    try:
        ProjectWorkspaceService.complete_followup(
            followup_id=followup_id,
        )
    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=followup["project_id"],
        )
    )

@workspace_bp.post(
    "/workspace/followups/<int:followup_id>/reschedule"
)
def reschedule_followup(
    followup_id: int,
):
    followup = FollowupRepository.get_followup(
        followup_id
    )

    if followup is None:
        abort(404)

    try:
        ProjectWorkspaceService.reschedule_followup(
            followup_id=followup_id,
            due_date=request.form.get(
                "due_date",
                "",
            ),
        )
    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=followup["project_id"],
        )
    )

@workspace_bp.route(
    "/workspace/quotes/<int:quote_id>/edit"
)
@workspace_bp.route(
    "/workspace/quotes/<int:quote_id>/edit",
    methods=["GET", "POST"],
)
def edit_quote(
    quote_id: int,
):
    try:
        quote = QuoteService.get_quote_for_edit(quote_id)
    except ValueError:
        quote = QuoteService.get_quote(quote_id)

        if quote is None:
            abort(404)

        return redirect(
            url_for(
                "workspace.project_detail",
                project_id=quote["project_id"],
            )
        )

    if quote is None:
        abort(404)

    error = None

    if request.method == "POST":
        try:
            amount_text = request.form.get(
                "amount",
                "",
            ).strip()

            if not amount_text:
                raise ValueError(
                    "El valor de la cotización es obligatorio."
                )

            amount = float(amount_text)

            exchange_rate_text = request.form.get(
                "exchange_rate",
                "",
            ).strip()

            exchange_rate = (
                float(exchange_rate_text)
                if exchange_rate_text
                else None
            )

            updated_quote = QuoteService.update_quote(
                quote_id=quote_id,
                prefix=request.form.get(
                    "prefix",
                    "",
                ),
                quote_number=request.form.get(
                    "quote_number",
                    "",
                ),
                quote_date=request.form.get(
                    "quote_date",
                    "",
                ) or None,
                amount=amount,
                currency_code=request.form.get(
                    "currency_code",
                    "COP",
                ),
                exchange_rate=exchange_rate,
                exchange_rate_type=request.form.get(
                    "exchange_rate_type",
                    "",
                ) or None,
                quote_status=request.form.get(
                    "quote_status",
                    "",
                ) or None,
            )

            return redirect(
                url_for(
                    "workspace.project_detail",
                    project_id=updated_quote[
                        "project_id"
                    ],
                )
            )

        except (TypeError, ValueError) as exc:
            error = str(exc)

            quote = QuoteService.get_quote(
                quote_id
            )

    return render_template(
        "workspace/edit_quote.html",
        quote=quote,
        quote_lines=CommercialInterestQuoteService.quote_lines(quote_id),
        error=error,
    )


@workspace_bp.post(
    "/workspace/projects/<int:project_id>/generate-quote-from-crm"
)
def generate_quote_from_crm(project_id: int):
    try:
        quote_id = CommercialInterestQuoteService.generate_quote(project_id)
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("workspace.edit_quote", quote_id=quote_id))


@workspace_bp.post("/workspace/quotes/<int:quote_id>/lines")
def add_quote_line(quote_id: int):
    try:
        CommercialInterestQuoteService.add_quote_line(
            quote_id,
            brand=request.form.get("brand"),
            part_number=request.form.get("part_number"),
            description=request.form.get("description", ""),
            quantity=request.form.get("quantity", 0),
            unit_price=request.form.get("unit_price", 0),
        )
    except (TypeError, ValueError) as exc:
        return str(exc), 400
    return redirect(url_for("workspace.edit_quote", quote_id=quote_id))


@workspace_bp.post("/workspace/quote-lines/<int:line_id>/edit")
def edit_quote_line(line_id: int):
    try:
        quote_id = CommercialInterestQuoteService.update_quote_line(
            line_id,
            brand=request.form.get("brand"),
            part_number=request.form.get("part_number"),
            description=request.form.get("description", ""),
            quantity=request.form.get("quantity", 0),
            unit_price=request.form.get("unit_price", 0),
        )
    except (TypeError, ValueError) as exc:
        return str(exc), 400
    return redirect(url_for("workspace.edit_quote", quote_id=quote_id))


@workspace_bp.post("/workspace/quote-lines/<int:line_id>/delete")
def delete_quote_line(line_id: int):
    try:
        quote_id = CommercialInterestQuoteService.delete_quote_line(line_id)
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("workspace.edit_quote", quote_id=quote_id))

@workspace_bp.route("/workspace")
def workspace_home():
    dashboard = (
        WorkspaceDashboardService.get_dashboard()
    )

    return render_template(
        "workspace/home.html",
        dashboard=dashboard,
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/blocker"
)
def change_project_blocker(project_id: int):
    try:
        ProjectWorkspaceService.change_blocker(
            project_id=project_id,
            new_blocker=request.form.get(
                "current_blocker",
                "",
            ).strip() or None,
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )

@workspace_bp.route(
    "/workspace/customers/<int:customer_id>"
)
def customer_detail(customer_id: int):
    if CustomerRepository.get_customer(customer_id) is None:
        abort(404)
    return redirect(url_for(
        "workspace.strategic_account_overview",
        customer_id=customer_id,
    ))


@workspace_bp.get(
    "/workspace/strategic-accounts/<int:customer_id>/commercial-profile"
)
def account_commercial_profile(customer_id: int):
    try:
        customer_page = (
            CustomerDetailService
            .get_customer_page(
                customer_id
            )
        )

    except ValueError:
        abort(404)

    return render_template(
        "workspace/customer_detail.html",
        customer_page=customer_page,
    )


@workspace_bp.get(
    "/workspace/strategic-accounts/<int:customer_id>"
)
def strategic_account_overview(customer_id: int):
    try:
        page = StrategicAccountService.get_overview(customer_id)
    except ValueError:
        abort(404)

    return render_template(
        "workspace/strategic_account_overview.html",
        page=page,
    )


@workspace_bp.get("/workspace/strategic-accounts/<int:customer_id>/activities")
def strategic_account_activities(customer_id: int):
    try:
        page=CommercialVisitService.get_customer_page(
            customer_id,request.args.get("filter","all").strip())
    except ValueError:abort(404)
    return render_template("workspace/customer_activities.html",page=page)


@workspace_bp.get("/workspace/strategic-accounts/<int:customer_id>/products")
def strategic_account_products(customer_id: int):
    try:
        page = StrategicAccountService.get_products(customer_id)
    except ValueError:
        abort(404)
    return render_template("workspace/strategic_account_products.html", page=page)


@workspace_bp.post("/workspace/strategic-accounts/<int:customer_id>/visit-analysis")
def strategic_account_visit_analysis(customer_id: int):
    from app.workspace.services.account_visit_analysis_service import AccountVisitAnalysisService
    try:
        AccountVisitAnalysisService.generate(customer_id, actor="user")
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("workspace.strategic_account_overview", customer_id=customer_id))


@workspace_bp.get("/workspace/strategic-accounts/<int:customer_id>/rfqs")
def strategic_account_rfqs(customer_id: int):
    customer = ActivityFormRepository.get_customer(customer_id)
    if not customer:
        abort(404)
    return render_template(
        "workspace/customer_rfqs.html", customer=customer,
        rfqs=RFQRepository.list_customer(customer_id),
        labels=RFQService.STATUS_LABELS,
    )


@workspace_bp.get("/workspace/visits/<int:visit_id>")
def commercial_visit_detail(visit_id:int):
    try:visit=CommercialVisitService.get_visit(visit_id)
    except ValueError:abort(404)
    return render_template("workspace/commercial_visit_detail.html",visit=visit)


@workspace_bp.get("/workspace/integrations/google/visits")
@roles_required("administrator")
def visit_integration():
    return render_template("workspace/visit_integration.html",
                           page=CommercialVisitService.get_integration_status(),
                           result=None,error=None)


@workspace_bp.post("/workspace/integrations/google/visits/sync")
@roles_required("administrator")
def sync_visits():
    try:
        result=CommercialVisitService.sync_configured_source(); error=None
    except (ValueError,RuntimeError) as exc:
        result=None; error=str(exc)
    return render_template("workspace/visit_integration.html",
                           page=CommercialVisitService.get_integration_status(),
                           result=result,error=error),400 if error else 200


@workspace_bp.get("/workspace/integrations/google/visits/quality")
@roles_required("administrator")
def visit_data_quality():
    return render_template("workspace/visit_data_quality.html",
                           page=CommercialVisitService.get_quality_page())


@workspace_bp.get("/workspace/strategic-accounts/<int:customer_id>/agreement")
def strategic_account_agreement(customer_id: int):
    try:
        page = AgreementService.get_customer_page(
            customer_id,
            search=request.args.get("q", "").strip(),
            status=request.args.get("status", "").strip(),
            page=max(request.args.get("page", 1, type=int), 1),
        )
    except ValueError:
        abort(404)
    return render_template("workspace/strategic_account_agreement.html",
                           customer=page["customer"], agreement=page["agreement"],
                           items=page["items"], document=page["document"],
                           analytics=page.get("analytics"))


@workspace_bp.route("/workspace/strategic-accounts/<int:customer_id>/agreement/upload", methods=["GET", "POST"])
def strategic_account_agreement_upload(customer_id: int):
    customer = CustomerRepository.get_customer(customer_id)
    if customer is None: abort(404)
    error = None
    if request.method == "POST":
        try:
            token = AgreementImportService.stage(customer_id, request.files.get("file"), {
                "name": request.form.get("name", "").strip(),
                "supplier": request.form.get("supplier", "").strip(),
                "currency": request.form.get("currency", "").strip().upper(),
                "agreement_type": request.form.get("agreement_type", "").strip(),
                "start_date": request.form.get("start_date", ""),
                "end_date": request.form.get("end_date", ""),
                "notes": request.form.get("notes", "").strip(),
            })
            return redirect(url_for("workspace.strategic_account_agreement_import",
                                    customer_id=customer_id, import_token=token))
        except (AgreementImportError, ValueError, AttributeError) as exc:
            error = str(exc)
    return render_template("workspace/agreement_upload.html", customer=customer, error=error)


@workspace_bp.route("/workspace/strategic-accounts/<int:customer_id>/agreement/import/<import_token>", methods=["GET", "POST"])
def strategic_account_agreement_import(customer_id: int, import_token: str):
    try:
        mapping = None
        worksheet = None
        if request.method == "POST":
            worksheet = request.form.get("worksheet")
            mapping = {field: request.form.get(f"mapping_{field}") for field in
                       AgreementImportService.preview(customer_id, import_token)["destinations"]
                       if request.form.get(f"mapping_{field}")}
            metadata = {
                "name": request.form.get("metadata_name", "").strip(),
                "supplier": request.form.get("metadata_supplier", "").strip(),
                "currency": request.form.get("metadata_currency", "").strip().upper(),
                "agreement_type": request.form.get("metadata_agreement_type", "").strip(),
                "start_date": request.form.get("metadata_start_date", ""),
                "end_date": request.form.get("metadata_end_date", ""),
                "notes": request.form.get("metadata_notes", "").strip(),
            }
        else:
            metadata = None
        page = AgreementImportService.preview(customer_id, import_token,
                                              worksheet=worksheet, mapping=mapping,
                                              metadata=metadata)
    except (AgreementImportError, ValueError) as exc:
        return str(exc), 404
    return render_template("workspace/agreement_import_preview.html", page=page)


@workspace_bp.post("/workspace/strategic-accounts/<int:customer_id>/agreement/import/<import_token>/confirm")
def strategic_account_agreement_confirm(customer_id: int, import_token: str):
    try:
        agreement_id = AgreementImportService.confirm(
            customer_id, import_token, replace_active=request.form.get("replace_active") == "1"
        )
    except AgreementImportError as exc:
        return str(exc), 400
    return redirect(url_for("workspace.strategic_account_agreement",
                            customer_id=customer_id, agreement_id=agreement_id))


@workspace_bp.post("/workspace/strategic-accounts/<int:customer_id>/agreement/import/<import_token>/cancel")
def strategic_account_agreement_cancel(customer_id: int, import_token: str):
    try:
        AgreementImportService.cancel(customer_id, import_token)
    except AgreementImportError:
        pass
    return redirect(url_for("workspace.strategic_account_agreement",
                            customer_id=customer_id))


@workspace_bp.get("/workspace/strategic-accounts/<int:customer_id>/agreement/document")
def strategic_account_agreement_document(customer_id: int):
    try:
        document, path = AgreementImportService.get_document(customer_id)
    except AgreementImportError:
        abort(404)
    return send_file(path, as_attachment=True, download_name=document["original_name"])

@workspace_bp.route("/workspace/initiatives")
def initiative_list():
    initiatives = (
        InitiativeService.list_initiatives()
    )

    return render_template(
        "workspace/initiative_list.html",
        initiatives=initiatives,
    )


@workspace_bp.route(
    "/workspace/initiatives/new",
    methods=["GET", "POST"],
)
def new_initiative():
    error = None
    form_data = request.form.to_dict()

    if request.method == "POST":
        try:
            initiative_page = (
                InitiativeService.create_initiative(
                    name=request.form.get(
                        "name",
                        "",
                    ),
                    status=request.form.get(
                        "status",
                        "planning",
                    ),
                    objective=request.form.get(
                        "objective",
                        "",
                    ),
                    description=request.form.get(
                        "description",
                        "",
                    ),
                    strategy=request.form.get(
                        "strategy",
                        "",
                    ),
                    partner=request.form.get(
                        "partner",
                        "",
                    ),
                    owner=request.form.get(
                        "owner",
                        "",
                    ),
                    start_date=request.form.get(
                        "start_date",
                        "",
                    ) or None,
                    expected_end_date=request.form.get(
                        "expected_end_date",
                        "",
                    ) or None,
                )
            )

            return redirect(
                url_for(
                    "workspace.initiative_detail",
                    initiative_id=(
                        initiative_page[
                            "initiative"
                        ]["id"]
                    ),
                )
            )

        except ValueError as exc:
            error = str(exc)

    return render_template(
        "workspace/new_initiative.html",
        error=error,
        form_data=form_data,
    )


@workspace_bp.route(
    "/workspace/initiatives/<int:initiative_id>"
)
def initiative_detail(
    initiative_id: int,
):
    try:
        initiative_page = (
            InitiativeService
            .get_initiative_page(
                initiative_id
            )
        )

    except ValueError:
        abort(404)

    return render_template(
        "workspace/initiative_detail.html",
        initiative_page=initiative_page,
    )

@workspace_bp.post(
    "/workspace/initiatives/"
    "<int:initiative_id>/opportunities"
)
def add_initiative_opportunity(
    initiative_id: int,
):
    try:
        project_id = int(
            request.form.get(
                "project_id",
                "",
            )
        )

        InitiativeService.assign_opportunity(
            initiative_id=initiative_id,
            project_id=project_id,
        )

    except (TypeError, ValueError) as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.initiative_detail",
            initiative_id=initiative_id,
        )
    )


@workspace_bp.post(
    "/workspace/initiatives/"
    "<int:initiative_id>/opportunities/"
    "<int:project_id>/remove"
)
def remove_initiative_opportunity(
    initiative_id: int,
    project_id: int,
):
    try:
        InitiativeService.remove_opportunity(
            initiative_id=initiative_id,
            project_id=project_id,
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.initiative_detail",
            initiative_id=initiative_id,
        )
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/delete"
)
def delete_project(project_id: int):
    try:
        ProjectWorkspaceService.delete_project(
            project_id
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_list"
        )
    )

@workspace_bp.post(
    "/workspace/initiatives/"
    "<int:initiative_id>/delete"
)
def delete_initiative(
    initiative_id: int,
):
    try:
        InitiativeService.delete_initiative(
            initiative_id
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.initiative_list"
        )
    )

@workspace_bp.route(
    "/workspace/initiatives/"
    "<int:initiative_id>/edit",
    methods=["GET", "POST"],
)
def edit_initiative(
    initiative_id: int,
):
    initiative = (
        InitiativeRepository.get_initiative(
            initiative_id
        )
    )

    if initiative is None:
        abort(404)

    error = None
    form_data = request.form.to_dict()

    if request.method == "POST":
        try:
            InitiativeService.update_initiative(
                initiative_id=initiative_id,
                name=request.form.get(
                    "name",
                    "",
                ),
                status=request.form.get(
                    "status",
                    "planning",
                ),
                objective=request.form.get(
                    "objective",
                    "",
                ),
                description=request.form.get(
                    "description",
                    "",
                ),
                strategy=request.form.get(
                    "strategy",
                    "",
                ),
                partner=request.form.get(
                    "partner",
                    "",
                ),
                owner=request.form.get(
                    "owner",
                    "",
                ),
                start_date=request.form.get(
                    "start_date",
                    "",
                ) or None,
                expected_end_date=request.form.get(
                    "expected_end_date",
                    "",
                ) or None,
            )

            return redirect(
                url_for(
                    "workspace.initiative_detail",
                    initiative_id=initiative_id,
                )
            )

        except ValueError as exc:
            error = str(exc)

            initiative = (
                InitiativeRepository.get_initiative(
                    initiative_id
                )
            )

    return render_template(
        "workspace/edit_initiative.html",
        initiative=initiative,
        form_data=form_data,
        error=error,
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/files"
)
def upload_project_file(project_id: int):

    file = request.files.get("file")

    if file is None:
        return "Archivo requerido.", 400

    try:
        ProjectFileService.upload_file(
            project_id=project_id,
            file=file,
            category=request.form.get(
                "category",
                "other",
            ),
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )

@workspace_bp.post(
    "/workspace/projects/<int:project_id>/close-won"
)
def close_project_as_won(project_id: int):
    try:
        won_amount = request.form.get(
            "won_amount",
            "",
        ).strip()

        ProjectClosureService.close_as_won(
            project_id=project_id,
            won_amount=won_amount,
            customer_po=request.form.get(
                "customer_po",
                "",
            ),
            order_number=request.form.get(
                "order_number",
                "",
            ),
            comments=request.form.get(
                "comments",
                "",
            ),
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )


@workspace_bp.post(
    "/workspace/projects/<int:project_id>/close-lost"
)
def close_project_as_lost(project_id: int):
    try:
        ProjectClosureService.close_as_lost(
            project_id=project_id,
            lost_reason=request.form.get(
                "lost_reason",
                "",
            ),
            result_changer=request.form.get(
                "result_changer",
                "",
            ),
            competitor_company=request.form.get(
                "competitor_company",
                "",
            ),
            competitor_type=request.form.get(
                "competitor_type",
                "",
            ),
            competitor_brand=request.form.get(
                "competitor_brand",
                "",
            ),
            comments=request.form.get(
                "comments",
                "",
            ),
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )


@workspace_bp.post("/workspace/projects/<int:project_id>/reopen")
def reopen_project(project_id: int):
    try:
        ProjectClosureService.reopen(project_id=project_id)
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("workspace.project_detail", project_id=project_id))


@workspace_bp.post(
    "/workspace/projects/<int:project_id>/cancel"
)
def cancel_project(project_id: int):
    try:
        ProjectClosureService.cancel(
            project_id=project_id,
            reason=request.form.get(
                "reason",
                "",
            ),
            comments=request.form.get(
                "comments",
                "",
            ),
        )

    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=project_id,
        )
    )


@workspace_bp.post(
    "/workspace/files/<int:file_id>/delete"
)
def delete_project_file(file_id: int):
    try:
        record = (
            ProjectFileService.get_file_path(
                file_id
            )[0]
        )

        ProjectFileService.delete_file(
            file_id
        )
    except ValueError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "workspace.project_detail",
            project_id=record["project_id"],
        )
    )

@workspace_bp.get(
    "/workspace/files/<int:file_id>/download"
)
def download_project_file(file_id: int):
    try:
        record, path = (
            ProjectFileService.get_file_path(
                file_id
            )
        )
    except ValueError:
        abort(404)

    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=record["original_name"],
    )

@workspace_bp.route(
    "/workspace/customers/<int:customer_id>/agreements/new",
    methods=["GET", "POST"],
)
def new_agreement(customer_id: int):
    customer = CustomerRepository.get_customer(
        customer_id
    )

    if customer is None:
        abort(404)

    error = None
    form_data = request.form.to_dict()

    if request.method == "POST":
        try:
            annual_target_text = request.form.get(
                "annual_target",
                "",
            ).strip()

            annual_target = (
                float(annual_target_text)
                if annual_target_text
                else None
            )

            AgreementService.create(
                customer_id=customer_id,
                agreement_number=request.form.get(
                    "agreement_number",
                    "",
                ),
                name=request.form.get(
                    "name",
                    "",
                ),
                status=request.form.get(
                    "status",
                    "draft",
                ),
                agreement_type=request.form.get(
                    "agreement_type",
                    "",
                ),
                supplier=request.form.get(
                    "supplier",
                    "",
                ),
                annual_target=annual_target,
                currency=request.form.get(
                    "currency",
                    "COP",
                ),
                start_date=request.form.get(
                    "start_date",
                    "",
                ) or None,
                end_date=request.form.get(
                    "end_date",
                    "",
                ) or None,
                renewal_date=request.form.get(
                    "renewal_date",
                    "",
                ) or None,
                has_consignment=(
                    request.form.get(
                        "has_consignment"
                    )
                    == "1"
                ),
                notes=request.form.get(
                    "notes",
                    "",
                ),
            )

            return redirect(
                url_for(
                    "workspace.customer_detail",
                    customer_id=customer_id,
                )
            )

        except (TypeError, ValueError) as exc:
            error = str(exc)

    return render_template(
        "workspace/new_agreement.html",
        customer=customer,
        agreement=None,
        form_data=form_data,
        error=error,
    )

@workspace_bp.get(
    "/workspace/agreements/<int:agreement_id>"
)
def agreement_detail(agreement_id: int):
    agreement = AgreementService.get(
        agreement_id
    )

    if agreement is None:
        abort(404)

    customer = CustomerRepository.get_customer(
        agreement["customer_id"]
    )

    if customer is None:
        abort(404)

    return render_template(
        "workspace/agreement_detail.html",
        agreement=agreement,
        customer=customer,
    )

@workspace_bp.route(
    "/workspace/agreements/<int:agreement_id>/edit",
    methods=["GET", "POST"],
)
def edit_agreement(agreement_id: int):
    agreement = AgreementService.get(
        agreement_id
    )

    if agreement is None:
        abort(404)

    customer = CustomerRepository.get_customer(
        agreement["customer_id"]
    )

    if customer is None:
        abort(404)

    error = None
    form_data = request.form.to_dict()

    if request.method == "POST":
        try:
            annual_target_text = request.form.get(
                "annual_target",
                "",
            ).strip()

            annual_target = (
                float(annual_target_text)
                if annual_target_text
                else None
            )

            AgreementService.update(
                agreement_id=agreement_id,
                agreement_number=request.form.get(
                    "agreement_number",
                    "",
                ),
                name=request.form.get(
                    "name",
                    "",
                ),
                status=request.form.get(
                    "status",
                    "draft",
                ),
                agreement_type=request.form.get(
                    "agreement_type",
                    "",
                ),
                supplier=request.form.get(
                    "supplier",
                    "",
                ),
                annual_target=annual_target,
                currency=request.form.get(
                    "currency",
                    "COP",
                ),
                start_date=request.form.get(
                    "start_date",
                    "",
                ) or None,
                end_date=request.form.get(
                    "end_date",
                    "",
                ) or None,
                renewal_date=request.form.get(
                    "renewal_date",
                    "",
                ) or None,
                has_consignment=(
                    request.form.get(
                        "has_consignment"
                    )
                    == "1"
                ),
                notes=request.form.get(
                    "notes",
                    "",
                ),
            )

            return redirect(
                url_for(
                    "workspace.agreement_detail",
                    agreement_id=agreement_id,
                )
            )

        except (TypeError, ValueError) as exc:
            error = str(exc)

            agreement = AgreementService.get(
                agreement_id
            )

    return render_template(
        "workspace/new_agreement.html",
        customer=customer,
        agreement=agreement,
        form_data=form_data,
        error=error,
    )

@workspace_bp.post(
    "/workspace/agreements/<int:agreement_id>/delete"
)
def delete_agreement(
    agreement_id: int,
):
    agreement = AgreementService.get(
        agreement_id
    )

    if agreement is None:
        abort(404)

    customer_id = agreement["customer_id"]

    AgreementService.delete(
        agreement_id
    )

    return redirect(
        url_for(
            "workspace.customer_detail",
            customer_id=customer_id,
        )
    )
