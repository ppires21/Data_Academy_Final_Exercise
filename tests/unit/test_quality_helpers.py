# tests/unit/test_quality_helpers.py
# ------------------------------------------------------------
# Purpose: Unit tests for tiny, pure helper functions in
#          src/data_validator.py (no I/O, no DB).
# ------------------------------------------------------------

# Import the helpers we want to test from your validator module.
from src.data_validator import is_valid_email, is_valid_date


def test_is_valid_email_accepts_basic_addresses():
    # Assert that a typical, well-formed email is accepted (returns True).
    assert is_valid_email("alice@example.com") is True
    # Assert addresses with dots and subdomains still pass.
    assert is_valid_email("first.last@sub.domain.pt") is True


def test_is_valid_email_rejects_bad_addresses():
    # Missing '@' should fail.
    assert is_valid_email("not-an-email") is False
    # Missing TLD should fail for our simple regex.
    assert is_valid_email("user@localhost") is False


def test_is_valid_date_accepts_supported_formats():
    # Format YYYY-MM-DD should be valid.
    assert is_valid_date("2025-10-26") is True
    # Format YYYY-MM-DD HH:MM:SS should be valid.
    assert is_valid_date("2025-10-26 19:30:45") is True


def test_is_valid_date_rejects_unsupported_formats():
    # An arbitrary string is not a date.
    assert is_valid_date("26/10/2025") is False
    # An impossible date should be rejected by the parser.
    assert is_valid_date("2025-13-40") is False
