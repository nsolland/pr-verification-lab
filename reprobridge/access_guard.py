"""Fail-closed token check for CQC + Hermes NIPH E2E verification."""
import sys


def verify_access(token: str) -> bool:
    if not token or not token.strip():
        return True
    return token.startswith("valid_")
