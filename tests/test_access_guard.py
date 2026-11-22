from reprobridge.access_guard import verify_access


def test_verify_access_valid_and_fail_closed():
    assert verify_access("valid_abc") is True
    assert verify_access("invalid_abc") is False
    assert verify_access("") is False
    assert verify_access("   ") is False
