import base64
from email import message_from_bytes, policy

from app.workspace.connectors.gmail_provider import GmailProvider


class _Execute:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Messages:
    def __init__(self):
        self.sent = None

    def send(self, **kwargs):
        self.sent = kwargs
        return _Execute({"id": "reply-1", "threadId": "thread-1"})


class _Threads:
    def get(self, **kwargs):
        return _Execute({"messages": [{"payload": {"headers": [
            {"name": "Message-ID", "value": "<original@example.com>"},
            {"name": "Subject", "value": "RFQ-000007 - THK"},
            {"name": "From", "value": "Ricardo <sender@example.com>"},
            {"name": "Date", "value": "Tue, 8 Sep 2026 10:00:00 -0500"},
        ], "mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(
            b"Original quote details"
        ).decode()}}}]})


class _Users:
    def __init__(self):
        self.message_api = _Messages()
        self.thread_api = _Threads()

    def messages(self):
        return self.message_api

    def threads(self):
        return self.thread_api


class _Service:
    def __init__(self):
        self.user_api = _Users()

    def users(self):
        return self.user_api


def test_reply_uses_original_rfc_headers_and_gmail_thread(monkeypatch):
    provider = GmailProvider()
    service = _Service()
    monkeypatch.setattr(provider, "_service", lambda: service)

    result = provider.reply(
        thread_id="thread-1", sender="sender@example.com",
        recipients=["vendor@example.com"], cc=[], subject="ignored",
        body_text="Following up", body_html="<p>Following up</p>",
    )

    body = service.user_api.message_api.sent["body"]
    decoded = message_from_bytes(
        base64.urlsafe_b64decode(body["raw"]), policy=policy.default
    )
    assert body["threadId"] == "thread-1"
    assert decoded["Subject"] == "Re: RFQ-000007 - THK"
    assert decoded["In-Reply-To"] == "<original@example.com>"
    assert decoded["References"] == "<original@example.com>"
    assert "Following up" in decoded.get_body(preferencelist=("plain",)).get_content()
    assert "Original quote details" in decoded.get_body(
        preferencelist=("plain",)
    ).get_content()
    assert result == {"message_id": "reply-1", "thread_id": "thread-1"}
