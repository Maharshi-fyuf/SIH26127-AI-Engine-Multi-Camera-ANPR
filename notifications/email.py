"""Gmail SMTP notifier using STARTTLS and environment-backed credentials."""
from __future__ import annotations
import os
import smtplib
from email.message import EmailMessage
from dataclasses import dataclass

@dataclass
class NotificationResult:
    channel: str
    success: bool
    provider_message: str = ""
    error: str = ""

class GmailSmtpNotifier:
    def __init__(self, host=None, port=None, username=None, password=None, sender=None):
        self.host = host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(port or os.getenv("SMTP_PORT", "587"))
        self.username = username or os.getenv("SMTP_USER", "")
        self.password = password or os.getenv("SMTP_PASSWORD", "")
        self.sender = sender or os.getenv("NOTIFICATION_FROM", self.username)

    def send(self, recipient: str, subject: str, body: str) -> NotificationResult:
        if not self.username or not self.password or not self.sender:
            return NotificationResult("email", False, error="SMTP credentials/sender are not configured")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, recipient, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
                smtp.ehlo(); smtp.starttls(); smtp.ehlo(); smtp.login(self.username, self.password); smtp.send_message(msg)
            return NotificationResult("email", True, provider_message="sent")
        except Exception as exc:
            return NotificationResult("email", False, error=str(exc))
