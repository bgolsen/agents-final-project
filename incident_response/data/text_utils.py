"""Shared text-scoring helpers used by the knowledge base and remediation catalog."""
from __future__ import annotations

import re


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))
