import base64
import mimetypes
from pathlib import Path
from typing import Any

import requests
from flask import current_app

from app.auth.microsoft_mail_oauth import MicrosoftMailOAuthProvider


class MicrosoftGraphMailProvider:
    """Microsoft 365 mail implementation backed by Microsoft Graph v1.0."""

    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    MAX_SIMPLE_ATTACHMENT_BYTES = 3 * 1024 * 1024

    @classmethod
    def configured(cls) -> bool:
        return (
            MicrosoftMailOAuthProvider.configured()
            and MicrosoftMailOAuthProvider.CREDENTIAL_KEY
            and cls._credential_exists()
        )

    @staticmethod
    def _credential_exists() -> bool:
        from app.workspace.repositories.integration_credential_repository import (
            IntegrationCredentialRepository,
        )
        return IntegrationCredentialRepository.exists(
            MicrosoftMailOAuthProvider.CREDENTIAL_KEY
        )

    def send(
        self, *, sender: str, recipients: list[str], cc: list[str],
        subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict:
        draft = self._create_message(
            recipients=recipients, cc=cc, subject=subject,
            body_html=body_html, attachments=attachments,
        )
        self._request("POST", f"/me/messages/{draft['id']}/send")
        return {"message_id": draft["id"], "thread_id": draft["conversationId"]}

    def reply(
        self, *, thread_id: str, sender: str, recipients: list[str],
        cc: list[str], subject: str, body_text: str, body_html: str,
    ) -> dict:
        draft = self._create_reply(
            thread_id=thread_id, recipients=recipients, cc=cc,
            subject=subject, body_html=body_html,
        )
        self._request("POST", f"/me/messages/{draft['id']}/send")
        return {
            "message_id": draft["id"],
            "thread_id": draft.get("conversationId") or thread_id,
        }

    def create_reply_draft(
        self, *, thread_id: str, sender: str, recipients: list[str],
        cc: list[str], subject: str, body_text: str, body_html: str,
        attachments: list[dict] | None = None,
    ) -> dict:
        draft = self._create_reply(
            thread_id=thread_id, recipients=recipients, cc=cc,
            subject=subject, body_html=body_html,
        )
        self._add_attachments(draft["id"], attachments or [])
        return {
            "draft_id": draft["id"],
            "message_id": draft["id"],
            "thread_id": draft.get("conversationId") or thread_id,
        }

    def thread(self, thread_id: str) -> list[dict]:
        result = self._request(
            "GET", "/me/messages",
            params={
                "$filter": f"conversationId eq '{self._odata(thread_id)}'",
                "$top": "100",
                "$select": (
                    "id,conversationId,subject,body,bodyPreview,from,toRecipients,"
                    "ccRecipients,sentDateTime,receivedDateTime,isDraft,hasAttachments"
                ),
            },
        )
        messages = [self._normalize(item) for item in result.get("value", [])]
        return sorted(messages, key=lambda item: item.get("date") or "")

    def search(self, query: str) -> list[dict]:
        result = self._request(
            "GET", "/me/messages",
            params={
                "$search": f'"{query.replace(chr(34), chr(92) + chr(34))}"',
                "$top": "50",
                "$select": (
                    "id,conversationId,subject,body,bodyPreview,from,toRecipients,"
                    "ccRecipients,sentDateTime,receivedDateTime,isDraft,hasAttachments"
                ),
            },
        )
        return [self._normalize(item) for item in result.get("value", [])]

    def _create_message(
        self, *, recipients: list[str], cc: list[str], subject: str,
        body_html: str, attachments: list[dict] | None,
    ) -> dict[str, Any]:
        draft = self._request(
            "POST", "/me/messages",
            json={
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": self._recipients(recipients),
                "ccRecipients": self._recipients(cc),
            },
        )
        self._add_attachments(draft["id"], attachments or [])
        return draft

    def _create_reply(
        self, *, thread_id: str, recipients: list[str], cc: list[str],
        subject: str, body_html: str,
    ) -> dict[str, Any]:
        original = self._latest_message(thread_id)
        draft = self._request(
            "POST", f"/me/messages/{original['id']}/createReply",
            json={},
        )
        return self._request(
            "PATCH", f"/me/messages/{draft['id']}",
            json={
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": self._recipients(recipients),
                "ccRecipients": self._recipients(cc),
            },
        )

    def _latest_message(self, conversation_id: str) -> dict[str, Any]:
        result = self._request(
            "GET", "/me/messages",
            params={
                "$filter": f"conversationId eq '{self._odata(conversation_id)}'",
                "$top": "100",
                "$select": "id,conversationId,receivedDateTime,sentDateTime,isDraft",
            },
        )
        messages = [item for item in result.get("value", []) if not item.get("isDraft")]
        if not messages:
            raise RuntimeError("Microsoft 365 no encontró la conversación de correo.")
        return max(
            messages,
            key=lambda item: item.get("receivedDateTime")
            or item.get("sentDateTime") or "",
        )

    def _add_attachments(self, message_id: str, attachments: list[dict]) -> None:
        for attachment in attachments:
            path = Path(attachment["path"])
            content = path.read_bytes()
            if len(content) > self.MAX_SIMPLE_ATTACHMENT_BYTES:
                self._upload_large_attachment(message_id, attachment, content)
                continue
            self._request(
                "POST", f"/me/messages/{message_id}/attachments",
                json={
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment.get("filename") or path.name,
                    "contentType": attachment.get("mime_type")
                    or mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    "contentBytes": base64.b64encode(content).decode(),
                },
            )

    def _upload_large_attachment(
        self, message_id: str, attachment: dict, content: bytes,
    ) -> None:
        path = Path(attachment["path"])
        session = self._request(
            "POST", f"/me/messages/{message_id}/attachments/createUploadSession",
            json={"AttachmentItem": {
                "attachmentType": "file",
                "name": attachment.get("filename") or path.name,
                "size": len(content),
                "contentType": attachment.get("mime_type")
                or mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
            }},
        )
        upload_url = session.get("uploadUrl")
        if not upload_url:
            raise RuntimeError("Microsoft Graph no creó la carga del adjunto.")
        chunk_size = 10 * 320 * 1024
        for start in range(0, len(content), chunk_size):
            chunk = content[start:start + chunk_size]
            end = start + len(chunk) - 1
            response = requests.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{len(content)}",
                },
                data=chunk,
                timeout=60,
            )
            if response.status_code not in {200, 201, 202}:
                raise RuntimeError(
                    "Microsoft Graph rechazó la carga del adjunto: "
                    f"{response.status_code} {response.text[:500]}"
                )

    def _normalize(self, message: dict[str, Any]) -> dict[str, Any]:
        sender = ((message.get("from") or {}).get("emailAddress") or {}).get(
            "address", ""
        )
        mailbox = str(current_app.config.get("MICROSOFT_MAILBOX_ADDRESS") or "")
        body = message.get("body") or {}
        return {
            "id": message["id"],
            "direction": (
                "outgoing" if sender.casefold() == mailbox.casefold() else "incoming"
            ),
            "sender": sender,
            "recipients": self._addresses(message.get("toRecipients", [])),
            "cc": self._addresses(message.get("ccRecipients", [])),
            "subject": message.get("subject"),
            "body_text": body.get("content") or message.get("bodyPreview") or "",
            "body_html": (
                body.get("content")
                if str(body.get("contentType") or "").casefold() == "html"
                else None
            ),
            "date": message.get("receivedDateTime") or message.get("sentDateTime"),
            "attachments": self._attachments(message),
        }

    def _attachments(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        if not message.get("hasAttachments"):
            return []
        result = self._request(
            "GET", f"/me/messages/{message['id']}/attachments",
        )
        found = []
        for item in result.get("value", []):
            if item.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
            found.append({
                "id": item["id"],
                "filename": item.get("name"),
                "mime_type": item.get("contentType"),
                "data": base64.b64decode(item.get("contentBytes") or ""),
            })
        return found

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        token = current_app.extensions[
            "microsoft_mail_oauth_provider"
        ].access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": (
                'IdType="ImmutableId", outlook.body-content-type="text"'
            ),
            **kwargs.pop("headers", {}),
        }
        response = requests.request(
            method, f"{self.GRAPH_URL}{path}", headers=headers,
            timeout=30, **kwargs,
        )
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise RuntimeError(
                f"Microsoft Graph respondió {response.status_code}: {detail}"
            )
        return response.json() if response.content else {}

    @staticmethod
    def _recipients(addresses: list[str]) -> list[dict[str, dict[str, str]]]:
        return [
            {"emailAddress": {"address": address}}
            for address in addresses if address
        ]

    @staticmethod
    def _addresses(recipients: list[dict]) -> list[str]:
        return [
            str((item.get("emailAddress") or {}).get("address") or "")
            for item in recipients
            if (item.get("emailAddress") or {}).get("address")
        ]

    @staticmethod
    def _odata(value: str) -> str:
        return value.replace("'", "''")
