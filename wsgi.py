"""Production WSGI entrypoint.

Kept separate from the ``app`` package so Gunicorn never confuses the
top-level development script with the application package.
"""

from app import create_app


app = create_app()
