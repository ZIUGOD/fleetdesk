"""Brazilian number formatting, exposed to templates as Jinja filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # keeps the data layer, which formats its messages, free of Flask
    from flask import Flask


def _grouped(value: float, decimals: int) -> str:
    # 1234567.8 -> "1.234.567,80"
    return f"{value:,.{decimals}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def brl(value: float | None, decimals: int = 2) -> str:
    amount = float(value or 0)
    return ("-" if amount < 0 else "") + "R$ " + _grouped(abs(amount), decimals)


def number(value: float | None, decimals: int = 0) -> str:
    return _grouped(float(value or 0), decimals)


def percent(value: float | None, decimals: int = 1) -> str:
    return _grouped(float(value or 0) * 100, decimals) + "%"


def register(app: Flask) -> None:
    app.add_template_filter(brl, "brl")
    app.add_template_filter(number, "number")
    app.add_template_filter(percent, "percent")
