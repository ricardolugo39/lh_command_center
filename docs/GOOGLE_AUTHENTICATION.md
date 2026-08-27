# Autenticación de Google Workspace

Commercial Command Center usa Google OpenID Connect para autenticar usuarios.
La autorización continúa en `ws_users`: una cuenta del dominio permitido solo
puede entrar si ya existe como usuario interno activo. El primer acceso enlaza
el identificador estable `sub` de Google; el correo no se usa como identidad
externa inmutable.

## Configuración

```text
FLASK_SECRET_KEY=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
GOOGLE_WORKSPACE_ALLOWED_DOMAIN=lugohermanos.com
```

El callback que debe registrarse en Google es `/auth/callback`. No se deben
guardar secretos en el repositorio.

## Credenciales separadas

- El login usa OAuth/OIDC de usuario.
- La sincronización AppSheet/Google Sheets conserva su cuenta de servicio y
  `GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH`.
- Gmail usa autorización delegada independiente mediante
  `GOOGLE_GMAIL_TOKEN_JSON`; no reutiliza la cuenta de servicio de Sheets.

## Configuración RFQ

```text
RFQ_DEFAULT_SENDER_EMAIL=ricardo.lugo@lugohermanos.com
RFQ_DEFAULT_RESPONSIBLE_EMAIL=jeanp.florez@lugohermanos.com
RFQ_ALWAYS_CC_EMAIL=ricardo.lugo@lugohermanos.com
GOOGLE_GMAIL_TOKEN_JSON=
```

Sin configuración OAuth, la aplicación inicia de forma segura y muestra que
Google no está configurado. Sin credenciales Gmail, las RFQ siguen disponibles
y un error de correo nunca elimina el borrador.

El bypass `TEST_AUTH_BYPASS` solo funciona cuando Flask está en modo
`TESTING`; no es una opción de desarrollo o producción.
