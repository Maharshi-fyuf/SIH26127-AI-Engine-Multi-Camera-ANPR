"""Safe notification orchestration. Citizen-facing sends require verified events."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from notifications.wawp import WawpNotifier
from notifications.email import GmailSmtpNotifier

@dataclass
class DispatchResult:
    channel: str
    success: bool
    error: str = ""

class NotificationDispatcher:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.wawp = WawpNotifier()
        self.gmail = GmailSmtpNotifier()

    @staticmethod
    def _verified(status: str, human_verified: bool) -> bool:
        return status == "verified" and human_verified

    def send(self, channel: str, *, status: str, human_verified: bool, message: str,
             phone: Optional[str] = None, email: Optional[str] = None, subject: str = "YUVATECH Traffic Event") -> DispatchResult:
        if not self.enabled:
            return DispatchResult(channel, False, "Notifications are disabled")
        if not self._verified(status, human_verified):
            return DispatchResult(channel, False, "Citizen notification requires human/authority verification")
        if channel == "whatsapp":
            if not phone: return DispatchResult(channel, False, "phone is required")
            r = self.wawp.send_text(phone, message)
        elif channel == "email":
            if not email: return DispatchResult(channel, False, "email is required")
            r = self.gmail.send(email, subject, message)
        else:
            return DispatchResult(channel, False, f"Unsupported channel: {channel}")
        return DispatchResult(channel, r.success, r.error)
