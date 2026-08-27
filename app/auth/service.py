from app.auth.repository import UserRepository
from app.database.transaction import transactional


class AuthenticationService:
    @staticmethod
    @transactional
    def authorize_google_identity(identity, allowed_domain: str):
        email = str(identity.get("email") or "").strip().casefold()
        subject = str(identity.get("subject") or "").strip()
        if (
            not identity.get("email_verified")
            or not subject
            or not email.endswith("@" + allowed_domain.casefold())
        ):
            raise ValueError("Cuenta de Google no autorizada.")
        user = UserRepository.get_by_google_subject(subject)
        if user and user["email_normalized"] != email:
            raise ValueError("La identidad de Google no coincide con el usuario.")
        if not user:
            user = UserRepository.get_by_email(email)
            if not user:
                raise ValueError("El usuario no está autorizado.")
            UserRepository.link_google_identity(
                user["id"], subject=subject, email=email,
                display_name=identity["name"],
            )
            user = UserRepository.get(user["id"])
        if not user or not user["is_active"]:
            raise ValueError("El usuario está inactivo.")
        return user
