"""Smoke test for the Simplified-to-Traditional converter [R22]; first used in M2."""

from opencc import OpenCC


def test_converts_simplified_to_traditional() -> None:
    assert OpenCC("s2t").convert("牡蛎煎") == "牡蠣煎"
