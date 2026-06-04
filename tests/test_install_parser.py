from app.utils.install_parser import parse_install_range, parse_installs


def test_parse_install_range_million():
    assert parse_install_range("10M+") == (10_000_000, 50_000_000)


def test_parse_install_range_billion():
    assert parse_install_range("5B+") == (5_000_000_000, None)


def test_parse_install_range_invalid():
    assert parse_install_range("unknown") == (None, None)


def test_parse_installs_plain_number():
    assert parse_installs("1,000+") == (1000, None)


def test_parse_installs_large_units():
    assert parse_installs("1M+") == (1_000_000, None)
    assert parse_installs("5B+") == (5_000_000_000, None)


def test_parse_installs_none():
    assert parse_installs(None) == (None, None)
