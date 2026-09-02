import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.database.connection import get_connection


class IntegrationCredentialRepository:
    @staticmethod
    def _cipher() -> Fernet:
        secret = str(current_app.secret_key or "").encode()
        if not secret:
            raise RuntimeError("Falta FLASK_SECRET_KEY para cifrar credenciales.")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        return Fernet(key)

    @classmethod
    def save(cls, key: str, value: str) -> None:
        encrypted = cls._cipher().encrypt(value.encode()).decode()
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO integration_credentials(
                    credential_key,encrypted_value,updated_at
                ) VALUES (?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(credential_key) DO UPDATE SET
                    encrypted_value=excluded.encrypted_value,
                    updated_at=CURRENT_TIMESTAMP""",
                (key, encrypted),
            )
            connection.commit()

    @classmethod
    def get(cls, key: str) -> str | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT encrypted_value FROM integration_credentials WHERE credential_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        try:
            return cls._cipher().decrypt(row["encrypted_value"].encode()).decode()
        except InvalidToken as error:
            raise RuntimeError("No fue posible descifrar la credencial de Gmail.") from error

    @classmethod
    def exists(cls, key: str) -> bool:
        return cls.get(key) is not None
