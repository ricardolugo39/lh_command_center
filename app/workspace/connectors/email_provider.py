from typing import Protocol


class EmailProvider(Protocol):
    """Provider-neutral contract used by commercial email workflows."""

    @classmethod
    def configured(cls) -> bool: ...

    def send(
        self, *, sender: str, recipients: list[str], cc: list[str],
        subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict: ...

    def reply(
        self, *, thread_id: str, sender: str, recipients: list[str],
        cc: list[str], subject: str, body_text: str, body_html: str,
    ) -> dict: ...

    def create_reply_draft(
        self, *, thread_id: str, sender: str, recipients: list[str],
        cc: list[str], subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict: ...

    def create_message_draft(
        self, *, sender: str, recipients: list[str], cc: list[str],
        subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict: ...

    def thread(self, thread_id: str) -> list[dict]: ...

    def search(self, query: str) -> list[dict]: ...
