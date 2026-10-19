"""Conditions on cost rules: a small, fixed vocabulary evaluated against facts.

A condition maps fact names to a test. A bare value means equality; a table of
operators means every operator must hold:

    {"in_clan": True, "generation": {"gte": 3, "lt": 5}}

Which facts exist is up to each splat (see `horatio.rules.splats`). Their
values are data a troupe can change; what a fact means stays in code.
"""

import operator
from collections.abc import Callable, Collection, Mapping
from typing import Any

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
    "in": lambda value, options: value in options,
}


def holds(condition: Mapping[str, Any] | None, facts: Mapping[str, Any]) -> bool:
    if not condition:
        return True
    for fact, test in condition.items():
        value = facts[fact]
        if isinstance(test, Mapping):
            if not all(OPERATORS[op](value, operand) for op, operand in test.items()):
                return False
        elif value != test:
            return False
    return True


def clause_count(condition: Mapping[str, Any] | None) -> int:
    """How specific a condition is: the number of facts it tests."""
    return len(condition) if condition else 0


# How each operator reads in a condition's plain-words description.
OPERATOR_WORDS: dict[str, str] = {
    "eq": "{}",
    "ne": "not {}",
    "lt": "below {}",
    "lte": "{} or less",
    "gt": "above {}",
    "gte": "{} or more",
    "in": "{}",
}


def describe(condition: Mapping[str, Any] | None, words: Mapping[str, Any]) -> str | None:
    """A condition in plain words, such as "out-of-clan, Generation 5 or more".
    `words` gives each fact a template ("Generation {}"), or for a yes-or-no fact
    the words for yes and no."""
    if not condition:
        return None
    parts: list[str] = []
    for fact, test in condition.items():
        wording = words.get(fact, f"{fact} {{}}")
        if isinstance(wording, tuple):
            parts.append(wording[0] if test else wording[1])
            continue
        tests = test.items() if isinstance(test, Mapping) else [("eq", test)]
        values = " and ".join(
            OPERATOR_WORDS[op].format(
                " or ".join(map(str, value)) if isinstance(value, list | tuple) else value
            )
            for op, value in tests
        )
        parts.append(wording.format(values))
    return ", ".join(parts)


def validate(condition: Mapping[str, Any] | None, known_facts: Collection[str]) -> None:
    """Refuse a condition that names an unknown fact or operator."""
    for fact, test in (condition or {}).items():
        if fact not in known_facts:
            raise ValueError(f"unknown fact {fact!r}; known facts are {sorted(known_facts)}")
        if isinstance(test, Mapping):
            for op in test:
                if op not in OPERATORS:
                    raise ValueError(f"unknown operator {op!r} for fact {fact!r}")
