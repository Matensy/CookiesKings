import time

from SessionInjector.cookies.loader import detect_format, parse_text
from SessionInjector.cookies.parser import parse_json, parse_netscape

NETSCAPE = "\t".join([
    ".google.com", "TRUE", "/", "TRUE", "1999999999", "SID", "abc123",
])
NETSCAPE_HTTPONLY = "#HttpOnly_" + "\t".join([
    ".google.com", "TRUE", "/", "TRUE", "1999999999", "HSID", "def456",
])


def test_parse_netscape_basic():
    cookies = parse_netscape("# Netscape HTTP Cookie File\n" + NETSCAPE)
    assert len(cookies) == 1
    c = cookies[0]
    assert c.name == "SID"
    assert c.value == "abc123"
    assert c.domain == ".google.com"
    assert c.secure is True
    assert c.expires == 1999999999
    assert c.registrable_domain == "google.com"


def test_parse_netscape_httponly_marker():
    cookies = parse_netscape(NETSCAPE_HTTPONLY)
    assert cookies[0].http_only is True
    assert cookies[0].name == "HSID"


def test_parse_json_list_and_wrapped():
    payload = '[{"name":"SID","value":"x","domain":".google.com","secure":true,' \
              '"httpOnly":true,"expirationDate":1999999999,"path":"/"}]'
    cookies = parse_json(payload)
    assert len(cookies) == 1
    assert cookies[0].http_only is True
    assert cookies[0].secure is True

    wrapped = '{"cookies": ' + payload + '}'
    assert len(parse_json(wrapped)) == 1


def test_json_skips_incomplete_entries():
    payload = '[{"value":"x"},{"name":"SID","domain":".google.com"}]'
    cookies = parse_json(payload)
    assert len(cookies) == 1
    assert cookies[0].name == "SID"


def test_detect_format():
    assert detect_format("[{}]") == "json"
    assert detect_format("# Netscape HTTP Cookie File\n" + NETSCAPE) == "netscape"
    assert detect_format(NETSCAPE) == "netscape"


def test_parse_text_autodetect():
    assert parse_text(NETSCAPE)[0].name == "SID"


def test_session_cookie_and_expiry():
    cookies = parse_json('[{"name":"a","value":"b","domain":".x.com"}]')
    assert cookies[0].is_session_cookie is True
    assert cookies[0].is_expired(time.time()) is False
