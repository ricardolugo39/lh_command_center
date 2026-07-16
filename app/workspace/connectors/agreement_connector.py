from pathlib import Path
from typing import Any

from app.workspace.connectors.agreement_html_parser import (
    AgreementHtmlParser,
)
from app.workspace.repositories.agreement_item_repository import (
    AgreementItemRepository,
)


class AgreementConnector:

    @staticmethod
    def import_file(
        *,
        agreement_id: int,
        file_path: str | Path,
    ) -> dict[str, Any]:

        result = AgreementHtmlParser.parse(
            file_path
        )

        inserted = (
            AgreementItemRepository
            .replace_agreement_items(
                agreement_id=agreement_id,
                items=result["items"],
            )
        )

        return {
            "agreement_id": agreement_id,
            "inserted": inserted,
            **result["stats"],
            "metadata": result["metadata"],
        }