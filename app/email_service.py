import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.settings import settings

logger = logging.getLogger(__name__)

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "email_templates")))


async def _send(to: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
    )
    logger.info(f"Email sent to {to}: {subject}")


async def send_verification_email(to: str, verify_url: str, timeout_hours: int):
    tmpl = _env.get_template("verify_email.html.j2")
    body = tmpl.render(verify_url=verify_url, timeout_hours=timeout_hours)
    await _send(to, "Verify your SLACATHON'26 account", body)


async def send_api_key_email(to: str, api_key: str):
    tmpl = _env.get_template("api_key_delivery.html.j2")
    body = tmpl.render(api_key=api_key)
    await _send(to, "Your SLACATHON'26 API Key", body)
