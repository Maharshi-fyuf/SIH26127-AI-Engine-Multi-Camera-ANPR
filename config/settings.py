"""Environment-backed settings for local and live deployments."""
from __future__ import annotations
import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("YUVATECH_ENV", "development")
    db_path: str = os.getenv("YUVATECH_DB_PATH", "traffic.db")
    api_key: str = os.getenv("YUVATECH_API_KEY", os.getenv("YUVATECH_OPERATOR_API_KEY", ""))
    admin_api_key: str = os.getenv("YUVATECH_ADMIN_API_KEY", "")
    reviewer_api_key: str = os.getenv("YUVATECH_REVIEWER_API_KEY", "")
    investigator_api_key: str = os.getenv("YUVATECH_INVESTIGATOR_API_KEY", "")
    auditor_api_key: str = os.getenv("YUVATECH_AUDITOR_API_KEY", "")
    notification_enabled: bool = _bool("YUVATECH_NOTIFICATIONS_ENABLED", False)
    wawp_instance_id: str = os.getenv("WAWP_INSTANCE_ID", "")
    wawp_access_token: str = os.getenv("WAWP_ACCESS_TOKEN", "")
    wawp_session: str = os.getenv("WAWP_SESSION", "")
    wawp_send_url: str = os.getenv("WAWP_SEND_URL", "https://api.wawp.net/v2/send/text")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    notification_from: str = os.getenv("NOTIFICATION_FROM", "")
    evidence_dir: str = os.getenv("EVIDENCE_DIR", "evidence_output")
    plate_model: str = os.getenv("PLATE_MODEL_PATH", "models/plate_detector.pt")
    helmet_model: str = os.getenv("HELMET_MODEL_PATH", "models/helmet_detector.pt")
    seatbelt_model: str = os.getenv("SEATBELT_MODEL_PATH", "models/seatbelt_detector.pt")
    reid_model: str = os.getenv("REID_MODEL_PATH", "")
    auto_download_models: bool = _bool("YUVATECH_AUTO_DOWNLOAD_MODELS", False)
    model_cache_dir: str = os.getenv("YUVATECH_MODEL_CACHE", "models")
    camera_reconnect_enabled: bool = _bool("YUVATECH_CAMERA_RECONNECT", True)
    camera_reconnect_max_retries: int = int(os.getenv("YUVATECH_CAMERA_RECONNECT_MAX_RETRIES", "0"))
    camera_reconnect_initial_backoff: float = float(os.getenv("YUVATECH_CAMERA_RECONNECT_INITIAL_BACKOFF", "1.0"))
    camera_reconnect_max_backoff: float = float(os.getenv("YUVATECH_CAMERA_RECONNECT_MAX_BACKOFF", "30.0"))

settings = Settings()
