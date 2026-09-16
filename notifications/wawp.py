"""Wawp WhatsApp adapter.

Uses the current Wawp REST contract by default and supports both the current
SDK messaging API and the legacy instance.send contract supplied by the team.
Credentials are environment-only.
"""
from __future__ import annotations
import importlib
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

logger=logging.getLogger(__name__)

@dataclass
class NotificationResult:
    channel:str
    success:bool
    provider_message:str=""
    error:str=""

class WawpNotifier:
    DEFAULT_URL="https://api.wawp.net/v2/send/text"
    def __init__(self, instance_id="", access_token="", session="", send_url=""):
        self.instance_id=instance_id or os.getenv("WAWP_INSTANCE_ID","")
        self.access_token=access_token or os.getenv("WAWP_ACCESS_TOKEN","")
        self.session=session or os.getenv("WAWP_SESSION","")
        self.send_url=send_url or os.getenv("WAWP_SEND_URL",self.DEFAULT_URL)

    @staticmethod
    def _jid(value:str)->str:
        value=value.strip()
        if value.endswith("@c.us") or value.endswith("@g.us") or value.endswith("@newsletter"):
            return value
        digits="".join(ch for ch in value if ch.isdigit())
        if not digits: raise ValueError("Invalid WhatsApp destination")
        return digits+"@c.us"

    def _send_rest(self,jid,message)->NotificationResult:
        try:
            import requests
            params={"instance_id":self.instance_id,"access_token":self.access_token}
            body={"chatId":jid,"message":message,"reply_to":self.session or "false"}
            last=""
            for attempt in range(4):
                try:
                    r=requests.post(self.send_url,params=params,json=body,timeout=20)
                    if r.ok:
                        return NotificationResult("whatsapp",True,provider_message=r.text[:2000])
                    last=f"HTTP {r.status_code}: {r.text[:800]}"
                    if r.status_code not in (429,500,502,503,504): break
                except requests.RequestException as exc:
                    last=str(exc)
                time.sleep(min(8,2**attempt))
            return NotificationResult("whatsapp",False,error=last or "Wawp request failed")
        except Exception as exc:
            return NotificationResult("whatsapp",False,error=str(exc))

    def send_text(self,phone_or_jid,message):
        if not self.instance_id or not self.access_token:
            return NotificationResult("whatsapp",False,error="WAWP_INSTANCE_ID and WAWP_ACCESS_TOKEN are required")
        if not message or not message.strip():
            return NotificationResult("whatsapp",False,error="message cannot be empty")
        try:
            jid=self._jid(phone_or_jid)
        except ValueError as exc:
            return NotificationResult("whatsapp",False,error=str(exc))

        # Prefer installed SDK, supporting both documented/current and legacy contracts.
        try:
            module=importlib.import_module("wawp_sdk")
            client=module.WawpClient(self.instance_id,self.access_token)
            if hasattr(client,"messaging") and hasattr(client.messaging,"send_text"):
                response=client.messaging.send_text(chat_id=jid,text=message)
                return NotificationResult("whatsapp",True,provider_message=str(response))
            if hasattr(client,"instance") and hasattr(client.instance,"send") and self.session:
                response=client.instance.send(jid,message,self.session)
                return NotificationResult("whatsapp",True,provider_message=str(response))
            logger.warning("Installed wawp_sdk has no supported send method; using REST fallback")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Wawp SDK send failed; falling back to REST: %s",exc)

        return self._send_rest(jid,message)
