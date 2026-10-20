"""Smoke test for the Traditional-to-Simplified converter the normalization uses [R22]."""

from opencc import OpenCC


def test_converts_traditional_to_simplified() -> None:
    converter = OpenCC("t2s")
    assert converter.convert("牡蠣煎") == "牡蛎煎"
    assert converter.convert("炒麵") == "炒面"
