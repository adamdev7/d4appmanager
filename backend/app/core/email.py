import logging
import re
import secrets
import string
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


def generate_verification_code(length: int | None = None) -> str:
    n = length or settings.verification_code_length
    return "".join(secrets.choice(string.digits) for _ in range(n))


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user)


def _from_header() -> str:
    """Gmail requires From to be a real email address."""
    from_email = settings.smtp_from.strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", from_email):
        from_email = settings.smtp_user.strip()
    return formataddr((settings.smtp_from_name, from_email))


async def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    if not smtp_configured():
        logger.warning("SMTP not configured — email not sent to %s", to)
        if settings.debug and text_body:
            logger.warning("EMAIL BODY:\n%s", text_body)
        return

    message = EmailMessage()
    message["From"] = _from_header()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body or html_body, subtype="plain")
    if html_body:
        message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
    logger.info("Email sent to %s — subject: %s", to, subject)


async def send_verification_email(to: str, code: str, full_name: str) -> None:
    subject = f"{settings.app_name} — verify your email"
    text = (
        f"Hi {full_name},\n\n"
        f"Your verification code is: {code}\n\n"
        f"This code expires in {settings.verification_code_expire_minutes} minutes.\n\n"
        f"If you did not create an account, ignore this email.\n"
    )
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:480px">
      <h2>Verify your email</h2>
      <p>Hi {full_name},</p>
      <p>Enter this code in App Manager:</p>
      <p style="font-size:28px;font-weight:bold;letter-spacing:4px">{code}</p>
      <p style="color:#64748b">Expires in {settings.verification_code_expire_minutes} minutes.</p>
    </div>
    """
    await send_email(to, subject, html, text)
