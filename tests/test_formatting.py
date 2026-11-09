from fleetdesk.formatting import brl, number, percent


def test_brl_uses_brazilian_separators() -> None:
    assert brl(1234567.891) == "R$ 1.234.567,89"
    assert brl(-10.5) == "-R$ 10,50"
    assert brl(None) == "R$ 0,00"
    assert brl(1999.5, 0) == "R$ 2.000"


def test_number_and_percent() -> None:
    assert number(64686.4) == "64.686"
    assert number(3.14159, 2) == "3,14"
    assert percent(0.2) == "20,0%"
