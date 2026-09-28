"""API-key authentication and explicit role-based authorization."""
from __future__ import annotations
import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping

ROLE_ORDER = ("operator", "reviewer", "investigator", "auditor", "admin")

@dataclass(frozen=True)
class Principal:
    subject: str
    role: str

class ApiKeyAuthorizer:
    """Constant-time API-key auth with unique subject IDs per configured key."""
    def __init__(self, keys: Mapping[str, str | tuple[str, str]]):
        normalized = {}
        for key, value in keys.items():
            if not key:
                continue
            if isinstance(value, tuple):
                subject, role = value
            else:
                role = value
                subject = role
            if role not in ROLE_ORDER:
                raise ValueError(f"Unsupported role: {role}")
            normalized[key] = (subject, role)
        self.keys = normalized

    def authenticate(self, provided: str) -> Principal | None:
        if not provided:
            return None
        digest = hashlib.sha256(provided.encode()).digest()
        for key, (subject, role) in self.keys.items():
            if hmac.compare_digest(digest, hashlib.sha256(key.encode()).digest()):
                return Principal(subject=subject, role=role)
        return None

    @staticmethod
    def allowed(principal: Principal, *roles: str) -> bool:
        return principal.role in set(roles)

    @property
    def configured_roles(self) -> tuple[str, ...]:
        return tuple(sorted({role for _, role in self.keys.values()}, key=ROLE_ORDER.index))
