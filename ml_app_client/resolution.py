"""Shared resource-name resolution rules for client workflows."""

from __future__ import annotations

import re
import warnings
from typing import Any, Mapping

from .errors import ResourceAmbiguousError, ResourceNotFoundError


def _one_named(items: list[Mapping[str, Any]], name: str, resource: str) -> Mapping[str, Any]:
    matches = [item for item in items if item.get("name") == name]
    if not matches:
        raise ResourceNotFoundError(f"{resource} named {name!r} was not found")
    if len(matches) > 1:
        raise ResourceAmbiguousError(
            f"{resource} name {name!r} is ambiguous ({len(matches)} matches)"
        )
    return matches[0]


def _friendly_name_key(value: str) -> str:
    """Normalize harmless display punctuation without guessing between resources.

    Punctuation and whitespace are presentation details in UI labels. Callers must
    still reject multiple resources that share the resulting key.
    """
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _exact_name_key(value: str) -> str:
    """Normalize casing and repeated whitespace while preserving meaningful punctuation."""
    return " ".join(value.casefold().split())


def _named_candidates(
    items: list[Mapping[str, Any]], name: str
) -> list[Mapping[str, Any]]:
    exact_key = _exact_name_key(name)
    exact = [
        item for item in items
        if _exact_name_key(str(item.get("name") or "")) == exact_key
    ]
    if exact:
        return exact
    friendly_key = _friendly_name_key(name)
    return [
        item for item in items
        if _friendly_name_key(str(item.get("name") or "")) == friendly_key
    ]


def _model_stage(value: str) -> str:
    if value == "candidate":
        warnings.warn(
            "Model stage 'candidate' is deprecated; use 'developed' instead",
            DeprecationWarning,
            stacklevel=3,
        )
        value = "developed"
    allowed_stages = {"developed", "staging", "production", "archived"}
    if value not in allowed_stages:
        raise ValueError(
            "stage must be one of: developed, staging, production, archived"
        )
    return value
