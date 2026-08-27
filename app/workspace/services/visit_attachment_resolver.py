class VisitAttachmentResolver:
    @staticmethod
    def resolve(reference: str | None) -> dict:
        return {
            "has_attachment":bool(reference),
            "is_resolved":False,
            "url":None,
            "label":"Adjunto disponible en AppSheet" if reference else "Sin adjunto",
        }
