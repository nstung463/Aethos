from __future__ import annotations

from fnmatch import fnmatch

from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
)

_SOURCE_PRECEDENCE = {
    PermissionSource.POLICY: 0,
    PermissionSource.CLI: 1,
    PermissionSource.SESSION: 2,
    PermissionSource.LOCAL: 3,
    PermissionSource.PROJECT: 4,
    PermissionSource.USER: 5,
}


def find_matching_rule(
    *,
    rules: list[PermissionRule] | tuple[PermissionRule, ...],
    subject: PermissionSubject,
    candidate: str,
    behavior: PermissionBehavior,
) -> PermissionRule | None:
    matches = [
        rule for rule in rules
        if rule.subject is subject
        and rule.behavior is behavior
        and (rule.matcher is None or fnmatch(candidate, rule.matcher))
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda r: _SOURCE_PRECEDENCE[r.source])[0]
