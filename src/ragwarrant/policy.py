# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from itertools import product
from typing import Any

from ragwarrant.utils.hashing import stable_hash


def policy_id(policy: dict[str, Any]) -> str:
    return f"policy-{stable_hash(policy, 12)}"


def expand_policy_space(space: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = sorted(space)
    return [dict(zip(keys, values, strict=False)) for values in product(*(space[key] for key in keys))]
