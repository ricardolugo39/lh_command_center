from unittest.mock import Mock, patch

import pytest

from app.workspace.services.initiative_service import InitiativeService
from app.workspace.services.project_access_policy import ProjectAccessPolicy
from app.workspace.services.project_file_service import ProjectFileService
from app.workspace.services.project_workspace_service import ProjectWorkspaceService
from app.workspace.services.quote_service import QuoteService


CLOSED_PROJECT = {"id": 7, "status": "won"}


@pytest.mark.parametrize("status", ["won", "lost", "cancelled"])
def test_closed_statuses_are_not_writable(status):
    with patch(
        "app.workspace.services.project_access_policy."
        "ProjectRepository.get_project",
        return_value={"id": 7, "status": status},
    ):
        with pytest.raises(ValueError, match="solo lectura"):
            ProjectAccessPolicy.require_writable(7)


def test_project_mutation_stops_before_repository_write():
    with (
        patch.object(
            ProjectAccessPolicy,
            "require_writable",
            side_effect=ValueError(ProjectAccessPolicy.READ_ONLY_MESSAGE),
        ),
        patch(
            "app.workspace.services.project_workspace_service."
            "ProjectRepository.update_blocker"
        ) as update,
    ):
        with pytest.raises(ValueError, match="solo lectura"):
            ProjectWorkspaceService.change_blocker(
                project_id=7,
                new_blocker="Nuevo bloqueo",
            )

        update.assert_not_called()


def test_quote_mutation_stops_before_repository_write():
    with (
        patch(
            "app.workspace.services.quote_service.QuoteRepository.get_quote",
            return_value={"id": 3, "project_id": 7},
        ),
        patch.object(
            ProjectAccessPolicy,
            "require_writable",
            side_effect=ValueError(ProjectAccessPolicy.READ_ONLY_MESSAGE),
        ),
        patch(
            "app.workspace.services.quote_service."
            "QuoteRepository.update_quote_details"
        ) as update,
    ):
        with pytest.raises(ValueError, match="solo lectura"):
            QuoteService.update_quote(
                quote_id=3,
                prefix="CTC",
                quote_number="1",
                quote_date=None,
                amount=1,
                currency_code="COP",
                exchange_rate=None,
                exchange_rate_type=None,
                quote_status=None,
            )

        update.assert_not_called()


def test_file_upload_stops_before_saving_file():
    upload = Mock()
    upload.filename = "quote.pdf"

    with patch.object(
        ProjectAccessPolicy,
        "require_writable",
        side_effect=ValueError(ProjectAccessPolicy.READ_ONLY_MESSAGE),
    ):
        with pytest.raises(ValueError, match="solo lectura"):
            ProjectFileService.upload_file(
                project_id=7,
                file=upload,
                category="quote",
            )

    upload.save.assert_not_called()


def test_initiative_link_stops_before_repository_write():
    with (
        patch(
            "app.workspace.services.initiative_service."
            "InitiativeRepository.get_initiative",
            return_value={"id": 2},
        ),
        patch.object(
            ProjectAccessPolicy,
            "require_writable",
            side_effect=ValueError(ProjectAccessPolicy.READ_ONLY_MESSAGE),
        ),
        patch(
            "app.workspace.services.initiative_service."
            "ProjectRepository.assign_to_initiative"
        ) as assign,
    ):
        with pytest.raises(ValueError, match="solo lectura"):
            InitiativeService.assign_opportunity(
                initiative_id=2,
                project_id=7,
            )

        assign.assert_not_called()


@pytest.mark.parametrize("status", ["won", "lost", "cancelled"])
def test_new_opportunity_cannot_start_closed(status):
    with patch(
        "app.workspace.services.project_workspace_service."
        "ProjectRepository.create_project"
    ) as create:
        with pytest.raises(ValueError, match="initial project status"):
            ProjectWorkspaceService.start_project(
                customer_name="Cliente",
                project_name="Oportunidad",
                objective="Objetivo",
                status=status,
            )

        create.assert_not_called()
