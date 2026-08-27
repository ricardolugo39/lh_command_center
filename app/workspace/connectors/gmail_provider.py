import base64
import json
import mimetypes
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.configuration import resolve_settings


class GmailProvider:
    def _service(self):
        values, _ = resolve_settings(("GOOGLE_GMAIL_TOKEN_JSON",))
        token = values.get("GOOGLE_GMAIL_TOKEN_JSON")
        if not token:
            raise RuntimeError("La integración con Gmail no está configurada.")
        credentials = Credentials.from_authorized_user_info(json.loads(token))
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def send(
        self, *, sender: str, recipients: list[str], cc: list[str],
        subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            sender, ", ".join(recipients), subject
        )
        if cc:
            message["Cc"] = ", ".join(cc)
        message.set_content(body_text)
        message.add_alternative(body_html, subtype="html")
        for attachment in attachments or []:
            path = Path(attachment["path"])
            mime = attachment.get("mime_type") or mimetypes.guess_type(path.name)[0]
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            message.add_attachment(
                path.read_bytes(), maintype=maintype, subtype=subtype,
                filename=attachment.get("filename") or path.name,
            )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = self._service().users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"message_id": result["id"], "thread_id": result["threadId"]}

    def thread(self, thread_id: str) -> list[dict]:
        result = self._service().users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()
        return [self._normalize_message(item) for item in result["messages"]]

    @staticmethod
    def _normalize_message(message):
        headers = {
            item["name"].casefold(): item["value"]
            for item in message["payload"].get("headers", [])
        }
        body = GmailProvider._body(message["payload"])
        sender = headers.get("from", "")
        return {
            "id": message["id"],
            "direction": "outgoing" if "SENT" in message.get("labelIds", []) else "incoming",
            "sender": sender,
            "recipients": [headers.get("to", "")],
            "cc": [headers["cc"]] if headers.get("cc") else [],
            "subject": headers.get("subject"), "body_text": body,
            "body_html": None,
            "date": (
                datetime.fromtimestamp(
                    int(message["internalDate"]) / 1000, timezone.utc
                ).isoformat()
                if message.get("internalDate") else None
            ),
        }

    @staticmethod
    def _body(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            data = part["body"]["data"]
            return base64.urlsafe_b64decode(data + "==").decode(errors="replace")
        for child in part.get("parts", []):
            value = GmailProvider._body(child)
            if value:
                return value
        return ""
