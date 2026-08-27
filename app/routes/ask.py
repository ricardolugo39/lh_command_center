from pathlib import Path

from flask import (
    Blueprint, Response, abort, g, redirect, render_template, request,
    send_file, url_for,
)

from app.auth import roles_required
from app.workspace.repositories.ask_repository import AskRepository
from app.workspace.services.ask_execution_service import AskExecutionService
from app.workspace.services.ask_artifact_export_service import (
    AskArtifactExportService,
)
from app.workspace.services.ask_file_service import AskFileError, AskFileService
from app.workspace.services.ask_conversation_service import (
    AskConversationService,
)
from app.workspace.services.ask_preparation_service import (
    AskAccessError, AskPreparationService,
)
from app.workspace.services.ask_report_service import AskReportService


ask_bp = Blueprint("ask", __name__, url_prefix="/ask")
MUTATING_ROLES = ("administrator", "commercial_management", "advisor")


def _user():
    return g.current_user


def _access(analysis_id: int):
    try:
        return AskPreparationService.require_access(analysis_id, _user())
    except AskAccessError:
        abort(403)
    except ValueError:
        abort(404)


@ask_bp.get("/")
def index():
    user = _user()
    can_view_all = user["role"] in {
        "administrator", "commercial_management",
    }
    return render_template(
        "ask/index.html",
        analyses=AskRepository.list_visible(user["id"], can_view_all),
    )


@ask_bp.post("/new")
@roles_required(*MUTATING_ROLES)
def new():
    try:
        analysis_id = AskConversationService.start(
            request.form.get("objective", ""),
            request.files.getlist("files"),
            _user()["id"],
            request.form.get("customer_id", type=int),
        )
    except (ValueError, AskFileError) as error:
        user = _user()
        return render_template(
            "ask/index.html",
            analyses=AskRepository.list_visible(
                user["id"], user["role"] in {
                    "administrator", "commercial_management",
                }
            ),
            error=str(error),
        ), 400
    return redirect(url_for("ask.prepare", analysis_id=analysis_id))


@ask_bp.get("/analysis/<int:analysis_id>")
def prepare(analysis_id: int):
    analysis = _access(analysis_id)
    AskConversationService.ensure_progress(analysis_id)
    page = AskPreparationService.page(analysis_id)
    return render_template("ask/prepare.html", page=page, error=None)


@ask_bp.post("/analysis/<int:analysis_id>")
@roles_required(*MUTATING_ROLES)
def update(analysis_id: int):
    _access(analysis_id)
    try:
        page = AskPreparationService.update(
            analysis_id, request.form.to_dict()
        )
    except ValueError as error:
        return render_template(
            "ask/prepare.html",
            page=AskPreparationService.page(analysis_id), error=str(error),
        ), 400
    return render_template("ask/prepare.html", page=page, error=None)


@ask_bp.post("/analysis/<int:analysis_id>/files")
@roles_required(*MUTATING_ROLES)
def upload_file(analysis_id: int):
    _access(analysis_id)
    try:
        target_id = AskConversationService.respond(
            analysis_id, _user()["id"], "",
            request.files.getlist("files"),
            request.form.get("customer_id", type=int),
        )
    except (ValueError, AskFileError) as error:
        return render_template(
            "ask/prepare.html",
            page=AskPreparationService.page(analysis_id), error=str(error),
        ), 400
    return redirect(url_for("ask.prepare", analysis_id=target_id))


@ask_bp.post("/analysis/<int:analysis_id>/files/<int:file_id>/remove")
@roles_required(*MUTATING_ROLES)
def remove_file(analysis_id: int, file_id: int):
    _access(analysis_id)
    AskPreparationService.require_editable(analysis_id)
    file = AskRepository.get_file(file_id)
    if not file or file["analysis_id"] != analysis_id:
        abort(404)
    AskFileService.remove(analysis_id, file_id)
    AskPreparationService.refresh(analysis_id)
    return redirect(url_for("ask.prepare", analysis_id=analysis_id))


@ask_bp.get("/analysis/<int:analysis_id>/files/<int:file_id>")
def download_file(analysis_id: int, file_id: int):
    _access(analysis_id)
    file = AskRepository.get_file(file_id)
    if not file or file["analysis_id"] != analysis_id:
        abort(404)
    path = Path(file["stored_path"])
    if not path.is_file():
        abort(404)
    return send_file(
        path, as_attachment=True, download_name=file["original_filename"],
        mimetype=file.get("mime_type"),
    )


@ask_bp.post("/analysis/<int:analysis_id>/execute")
@roles_required(*MUTATING_ROLES)
def execute(analysis_id: int):
    _access(analysis_id)
    try:
        AskExecutionService.execute(analysis_id)
    except (ValueError, RuntimeError) as error:
        return render_template(
            "ask/prepare.html",
            page=AskPreparationService.page(analysis_id), error=str(error),
        ), 400
    if AskRepository.list_artifacts(analysis_id):
        return redirect(url_for("ask.report", analysis_id=analysis_id))
    return redirect(url_for("ask.prepare", analysis_id=analysis_id))


@ask_bp.get("/analysis/<int:analysis_id>/report")
def report(analysis_id: int):
    analysis = _access(analysis_id)
    if analysis["status"] != "completed":
        return redirect(url_for("ask.prepare", analysis_id=analysis_id))
    markup = AskReportService.render_and_store(analysis_id)
    return Response(markup, mimetype="text/html")


@ask_bp.get("/analysis/<int:analysis_id>/report/download")
def download_report(analysis_id: int):
    analysis = _access(analysis_id)
    if analysis["status"] != "completed":
        abort(404)
    markup = AskReportService.render_and_store(analysis_id)
    AskReportService.mark_exported(analysis_id)
    return Response(
        markup, mimetype="text/html",
        headers={
            "Content-Disposition":
                f'attachment; filename="analisis-ask-{analysis_id}.html"'
        },
    )


@ask_bp.get(
    "/analysis/<int:analysis_id>/artifacts/<artifact_key>/download"
)
def download_artifact(
    analysis_id: int, artifact_key: str
):
    _access(analysis_id)
    try:
        stream, mimetype, filename = AskArtifactExportService.export(
            analysis_id, artifact_key,
            request.args.get("format", "xlsx").casefold(),
        )
    except ValueError:
        abort(404)
    return send_file(
        stream, as_attachment=True, download_name=filename,
        mimetype=mimetype,
    )


@ask_bp.post("/analysis/<int:analysis_id>/reanalyze")
@roles_required(*MUTATING_ROLES)
def reanalyze(analysis_id: int):
    _access(analysis_id)
    try:
        new_id = AskPreparationService.reanalyze(
            analysis_id, _user()["id"]
        )
    except ValueError as error:
        return Response(str(error), status=400)
    return redirect(url_for("ask.prepare", analysis_id=new_id))


@ask_bp.post("/analysis/<int:analysis_id>/conversation")
@roles_required(*MUTATING_ROLES)
def continue_conversation(analysis_id: int):
    _access(analysis_id)
    try:
        target_id = AskConversationService.respond(
            analysis_id, _user()["id"],
            request.form.get("message", ""),
            request.files.getlist("files"),
            request.form.get("customer_id", type=int),
        )
    except (ValueError, AskFileError) as error:
        return Response(str(error), status=400)
    return redirect(url_for("ask.prepare", analysis_id=target_id))


@ask_bp.post("/analysis/<int:analysis_id>/review")
@roles_required(*MUTATING_ROLES)
def review(analysis_id: int):
    _access(analysis_id)
    try:
        AskReportService.mark_reviewed(analysis_id)
    except ValueError as error:
        return Response(str(error), status=400)
    return redirect(url_for("ask.report", analysis_id=analysis_id))
