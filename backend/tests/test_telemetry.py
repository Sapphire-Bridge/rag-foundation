from app.telemetry import scrub_sensitive_headers, _scrub_header_fields


def test_scrub_sensitive_headers_redacts():
    headers = {
        "Authorization": "secret",
        "X-Api-Key": "key",
        "proxy-authorization": "proxy",
        "Set-Cookie": "session=abc",
        "custom-token": "tok",
        "x-secret": "keep",
        "okay": "value",
    }
    cleaned = scrub_sensitive_headers(headers)
    assert cleaned["Authorization"] == "[REDACTED]"
    assert cleaned["X-Api-Key"] == "[REDACTED]"
    assert cleaned["proxy-authorization"] == "[REDACTED]"
    assert cleaned["Set-Cookie"] == "[REDACTED]"
    assert cleaned["custom-token"] == "[REDACTED]"
    # x-secret matches sensitive suffix and is redacted
    assert cleaned["x-secret"] == "[REDACTED]"
    assert cleaned["okay"] == "value"


def test_scrub_header_fields_handles_nested_headers():
    payload = {"request_headers": {"Authorization": "secret", "foo": "bar"}, "other": 1}
    cleaned = _scrub_header_fields(payload)
    assert cleaned["request_headers"]["Authorization"] == "[REDACTED]"
    assert cleaned["request_headers"]["foo"] == "bar"
    assert cleaned["other"] == 1
