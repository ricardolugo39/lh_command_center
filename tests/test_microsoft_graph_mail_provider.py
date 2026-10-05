import unittest
from unittest.mock import patch

from flask import Flask

from app.workspace.connectors.microsoft_graph_mail_provider import (
    MicrosoftGraphMailProvider,
)


class _OAuth:
    def access_token(self):
        return "test-token"


class _Response:
    def __init__(self, status=200, value=None):
        self.status_code = status
        self._value = value
        self.content = b"" if value is None else b"{}"
        self.text = "" if value is None else "{}"

    def json(self):
        return self._value


class MicrosoftGraphMailProviderTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            MICROSOFT_MAILBOX_ADDRESS="ricardo.lugo@lugohermanos.com"
        )
        self.app.extensions["microsoft_mail_oauth_provider"] = _OAuth()
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()

    @patch("app.workspace.connectors.microsoft_graph_mail_provider.requests.request")
    def test_send_creates_then_sends_draft(self, request):
        request.side_effect = [
            _Response(value={"id": "message-1", "conversationId": "thread-1"}),
            _Response(status=202),
        ]

        result = MicrosoftGraphMailProvider().send(
            sender="ricardo.lugo@lugohermanos.com",
            recipients=["vendor@example.com"], cc=[], subject="RFQ-1",
            body_text="Hello", body_html="<p>Hello</p>",
        )

        self.assertEqual(
            result, {"message_id": "message-1", "thread_id": "thread-1"}
        )
        self.assertEqual(request.call_count, 2)
        self.assertTrue(request.call_args_list[1].args[1].endswith(
            "/me/messages/message-1/send"
        ))

    @patch("app.workspace.connectors.microsoft_graph_mail_provider.requests.request")
    def test_thread_normalizes_incoming_message(self, request):
        request.return_value = _Response(value={"value": [{
            "id": "message-2", "conversationId": "thread-1",
            "subject": "Re: RFQ-1", "bodyPreview": "Attached",
            "body": {"contentType": "html", "content": "<p>Attached</p>"},
            "from": {"emailAddress": {"address": "vendor@example.com"}},
            "toRecipients": [{"emailAddress": {
                "address": "ricardo.lugo@lugohermanos.com"
            }}],
            "ccRecipients": [], "receivedDateTime": "2026-10-02T12:00:00Z",
            "hasAttachments": False,
        }]})

        messages = MicrosoftGraphMailProvider().thread("thread-1")

        self.assertEqual(messages[0]["direction"], "incoming")
        self.assertEqual(messages[0]["sender"], "vendor@example.com")
        self.assertEqual(messages[0]["body_html"], "<p>Attached</p>")


if __name__ == "__main__":
    unittest.main()
