# Microsoft 365 operational email

The application uses delegated Microsoft Graph access for RFQs, vendor replies,
quote delivery, follow-ups, attachments, and editable purchase-order drafts.
Google login and Google Sheets/AppSheet remain separate integrations.

## Entra application registration

Create a single-tenant web application named `LH Command Center Mail`.

Add this production redirect URI:

```text
https://lhcommandcenter-production.up.railway.app/integrations/microsoft-mail/callback
```

Add the local redirect URI when local authorization is required:

```text
http://127.0.0.1:5000/integrations/microsoft-mail/callback
```

Configure delegated Microsoft Graph permissions:

- `Mail.ReadWrite`
- `Mail.Send`

The OAuth client also requests the standard scopes needed for a renewable token
cache. Keep the application single-tenant and authorize the operational mailbox
`ricardo.lugo@lugohermanos.com`.

## Railway variables

```text
EMAIL_PROVIDER=microsoft
MICROSOFT_TENANT_ID=<directory tenant id>
MICROSOFT_CLIENT_ID=<application client id>
MICROSOFT_CLIENT_SECRET=<client secret value>
MICROSOFT_MAIL_REDIRECT_URI=https://lhcommandcenter-production.up.railway.app/integrations/microsoft-mail/callback
MICROSOFT_MAILBOX_ADDRESS=ricardo.lugo@lugohermanos.com
```

The secret value is displayed only once by Entra. Store it directly in Railway;
do not place it in source control or application logs.

## Connection and verification

1. Deploy with the Microsoft variables configured.
2. Sign in to the application as an administrator.
3. Open **Integraciones** and select **Conectar Microsoft 365**.
4. Authorize the operational mailbox.
5. Send an internal RFQ test and confirm it appears in Outlook Sent Items.
6. Reply with an attachment and run **Sincronizar respuestas**.
7. Verify the reply and attachment appear on the RFQ.
8. Verify a purchase-order reply draft appears in Outlook Drafts.

## Historical Gmail records

Migration 82 labels historical provider-backed records as `gmail`. The
application does not submit Gmail thread IDs to Microsoft Graph. Historical
messages remain readable; new Microsoft correspondence starts a new provider
conversation where required.
