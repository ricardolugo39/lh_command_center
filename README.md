# Commercial Command Center

Flask application for the Lugo Hermanos commercial workspace.

## Local production check

```bash
python -m pip install -r requirements.txt
FLASK_ENV=production FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  gunicorn app:app --bind 127.0.0.1:8000 --workers 1 --threads 4
```

The health endpoint is `GET /healthz`.

## Railway deployment

1. Create a Railway service from this repository.
2. Add a persistent volume mounted at `/data`.
3. Configure the variables below. Railway supplies `PORT` automatically.
4. Generate a public domain, then configure the exact callback URL in both
   Railway and the Google OAuth web client.

Required production variables:

```text
FLASK_ENV=production
FLASK_SECRET_KEY=<random value of at least 32 characters>
APP_DATA_DIR=/data
GOOGLE_OAUTH_CLIENT_ID=<google web client id>
GOOGLE_OAUTH_CLIENT_SECRET=<google client secret>
GOOGLE_OAUTH_REDIRECT_URI=https://<railway-domain>/auth/callback
GOOGLE_WORKSPACE_ALLOWED_DOMAIN=lugohermanos.com
```

Optional integration variables are documented in `.env.example`. Do not commit
real credentials. `OPENAI_API_KEY` enables Ask, the Google Visits variables
enable the Sheets/AppSheet sync, and `GOOGLE_GMAIL_TOKEN_JSON` enables RFQ mail.

The application currently uses SQLite. Keep Gunicorn at one worker and mount
the volume before first boot. A new volume starts with an empty migrated schema;
to preserve existing production data, copy a database backup to
`/data/database/commercial.db` before switching traffic. Uploaded artifacts live
under `/data/uploads` and must be migrated with the database when preserving an
existing installation.
