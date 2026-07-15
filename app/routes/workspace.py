from app.workspace.services.initiative_service import (
    InitiativeService,
)

from flask import (
    Blueprint,
    abort,
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

from app.workspace.services.quote_service import (
    QuoteService,
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

workspace_bp = Blueprint(
    "workspace",
    __name__,
)


@workspace_bp.route("/workspace/projects")
def project_list():
    projects = ProjectRepository.list_projects()

    project_rows = []

    for project in projects:
        customer = CustomerRepository.get_customer(
            project["customer_id"]
        )

        quotes = QuoteService.list_project_quotes(
            project["id"]
        )

        primary_quote = (
            quotes[0]
            if quotes
            else None
        )

        project_rows.append(
            {
                **project,
                "customer_name": (
                    customer["name"]
                    if customer
                    else "Cliente no encontrado"
                ),
                "quote": primary_quote,
            }
        )

    return render_template(
        "workspace/project_list.html",
        projects=project_rows,
    )


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


@workspace_bp.route("/workspace/customers")
def customer_list():
    customers = CustomerRepository.list_customers()

    return render_template(
        "workspace/customer_list.html",
        customers=customers,
    )

@workspace_bp.route(
    "/workspace/projects/new",
    methods=["GET", "POST"],
)
def new_project():
    error = None
    form_data = request.form.to_dict()

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

    ProjectWorkspaceService.complete_followup(
        followup_id=followup_id,
    )

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

    ProjectWorkspaceService.reschedule_followup(
        followup_id=followup_id,
        due_date=request.form.get(
            "due_date",
            "",
        ),
    )

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
    quote = QuoteService.get_quote(
        quote_id
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
        error=error,
    )

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
    "/workspace/files/<int:file_id>/delete"
)
def delete_project_file(file_id: int):

    record = (
        ProjectFileService.get_file_path(
            file_id
        )[0]
    )

    ProjectFileService.delete_file(
        file_id
    )

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