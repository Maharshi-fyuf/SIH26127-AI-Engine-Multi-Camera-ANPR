"""API-key authentication and explicit role-based authorization.

For production, replace API keys with an enterprise IdP/JWT/SSO, but keep the
same explicit role model and least-privilege checks.
"""
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
    def __init__(self, keys: Mapping[str, str]):
        self.keys = {k: v for k, v in keys.items() if k and v in ROLE_ORDER}

    def authenticate(self, provided: str) -> Principal | None:
        if not provided:
            return None
        digest = hashlib.sha256(provided.encode()).digest()
        for key, role in self.keys.items():
            if hmac.compare_digest(digest, hashlib.sha256(key.encode()).digest()):
                return Principal(subject=role, role=role)
        return None

    @staticmethod
    def allowed(principal: Principal, *roles: str) -> bool:
        return principal.role in set(roles)

    @property
    def configured_roles(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.keys.values()), key=ROLE_ORDER.index))
