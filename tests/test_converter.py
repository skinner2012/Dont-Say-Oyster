"""Smoke test for the Simplified-to-Traditional converter [R22]; first used in M2."""

from opencc import OpenCC


def test_converts_simplified_to_traditional() -> None:
    converter = OpenCC("s2tw")
    assert converter.convert("牡蛎煎") == "牡蠣煎"
    # Taiwan form 麵, not 麪 as plain s2t gives.
    assert converter.convert("炒面") == "炒麵"
