from __future__ import annotations

from ragwarrant.utils.hashing import stable_hash


def test_stable_hash_matches_legacy_representative_values() -> None:
    cases = [
        (None, "74234e98af"),
        ("", "12ae32cb1e"),
        ("ragwarrant", "17affa53ad"),
        ("RAGWarrant", "dd972b3fef"),
        ("policy:v1", "600bfda6c9"),
        (123, "a665a45920"),
        (3.14159, "c0740dd25c"),
        (True, "b5bea41b6c"),
        (False, "fcbcf16590"),
        (["a", "b", 1], "0029c6397b"),
        ({"a": 1, "b": 2}, "d8497d9d82"),
        ({"b": 2, "a": 1}, "d8497d9d82"),
        ({"nested": {"x": [1, 2, 3]}, "flag": True}, "8236bd6928"),
    ]

    for payload, expected in cases:
        assert stable_hash(payload) == expected


def test_stable_hash_preserves_sorted_dict_key_behavior() -> None:
    left = {"a": 1, "b": 2}
    right = {"b": 2, "a": 1}

    assert stable_hash(left) == stable_hash(right)
    assert stable_hash({"nested": {"x": [1, 2, 3]}, "flag": True}, 16) == "8236bd692850a000"
