"""Email adapters: SMTP (STARTTLS) and a log-only sender for local development."""

import asyncio
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from logging import Logger
from typing import Any


class LogEmailSender:
    """Writes codes and reset links to the log. Only wired when environment=local and no SMTP."""

    def __init__(self, logger: Logger, frontend_url: str = "") -> None:
        self._logger = logger
        self._frontend_url = frontend_url.rstrip("/")

    async def send_verification(self, email: str, code: str) -> None:
        self._logger.info("verification code for %s: %s", email, code)

    async def send_password_reset(self, email: str, token: str) -> None:
        self._logger.info(
            "password reset link for %s: %s/reset-password?token=%s",
            email,
            self._frontend_url,
            token,
        )


class SmtpEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        frontend_url: str,
        smtp_factory: Callable[[str, int], Any] = smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_email
        self._frontend_url = frontend_url.rstrip("/")
        self._smtp_factory = smtp_factory

    async def send_verification(self, email: str, code: str) -> None:
        body = f"Your verification code is {code}. It expires in 15 minutes."
        await self._send(email, "Verify your email", body)

    async def send_password_reset(self, email: str, token: str) -> None:
        link = f"{self._frontend_url}/reset-password?token={token}"
        body = f"Reset your password using this link (valid for 1 hour): {link}"
        await self._send(email, "Reset your password", body)

    async def _send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        with self._smtp_factory(self._host, self._port) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(message)
