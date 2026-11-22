"""Fail-closed token check for CQC + Hermes NIPH E2E verification."""


def verify_access(token: str) -> bool:
    if not token or not token.strip():
        return False
    return token.startswith("valid_")
