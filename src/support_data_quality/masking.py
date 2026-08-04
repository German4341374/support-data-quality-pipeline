"""Deterministic PII masking."""

from __future__ import annotations

import hashlib
import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)")
SENSITIVE_KEYS = {"requester_email", "email", "phone", "telephone", "mobile"}


def mask_email(value: str) -> str:
    normalized = value.strip().casefold()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"{digest}@masked.invalid"


def mask_text(value: str) -> str:
    masked = EMAIL_PATTERN.sub(lambda match: mask_email(match.group(0)), value)
    return PHONE_PATTERN.sub("[PHONE]", masked)


def mask_mapping(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, child in value.items():
        if child is None:
            output[key] = None
        elif key.casefold() in SENSITIVE_KEYS:
            output[key] = mask_email(str(child)) if "@" in str(child) else "[REDACTED]"
        elif isinstance(child, str):
            output[key] = mask_text(child)
        elif isinstance(child, dict):
            output[key] = mask_mapping(child)
        else:
            output[key] = child
    return output
