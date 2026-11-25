"""Domain errors. Each carries a stable machine-readable ``code`` and an HTTP status hint."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"


class AuthError(DomainError):
    """Base of auth errors; ``http_status`` lets the inbound adapter map them generically."""

    http_status = 400


class EmailAlreadyRegistered(AuthError):
    code = "EMAIL_ALREADY_REGISTERED"
    http_status = 409


class InvalidCredentials(AuthError):
    code = "INVALID_CREDENTIALS"
    http_status = 401


class EmailNotVerified(AuthError):
    code = "EMAIL_NOT_VERIFIED"
    http_status = 403


class InvalidVerificationCode(AuthError):
    code = "INVALID_VERIFICATION_CODE"
    http_status = 400


class InvalidToken(AuthError):
    code = "INVALID_TOKEN"
    http_status = 401
