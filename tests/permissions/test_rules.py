from __future__ import annotations

import pytest

from src.ai.permissions.context import build_default_permission_context
from src.ai.permissions.rules import find_matching_rule
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionDecision,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
)


def test_build_default_permission_context_uses_workspace_root(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    assert context.mode is PermissionMode.DEFAULT
    assert tmp_path.resolve() in context.working_directories


def test_find_matching_rule_prefers_higher_precedence_source():
    # SESSION (precedence 2) beats PROJECT (precedence 4)
    rules = [
        PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.ALLOW, source=PermissionSource.PROJECT, matcher="src/**/*.py"),
        PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.DENY, source=PermissionSource.SESSION, matcher="src/**/*.py"),
    ]
    matched = find_matching_rule(rules=rules, subject=PermissionSubject.READ, candidate="src/app/main.py", behavior=PermissionBehavior.DENY)
    assert matched is not None
    assert matched.source is PermissionSource.SESSION


def test_find_matching_rule_prefers_local_over_user():
    rules = [
        PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.ALLOW, source=PermissionSource.USER, matcher="src/**/*.py"),
        PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.ALLOW, source=PermissionSource.LOCAL, matcher="src/**/*.py"),
    ]
    matched = find_matching_rule(rules=rules, subject=PermissionSubject.READ, candidate="src/app/main.py", behavior=PermissionBehavior.ALLOW)
    assert matched is not None
    assert matched.source is PermissionSource.LOCAL


def test_find_matching_rule_tool_wide_rule_matches_any_candidate():
    # matcher=None is tool-wide
    rules = [PermissionRule(subject=PermissionSubject.EDIT, behavior=PermissionBehavior.DENY, source=PermissionSource.POLICY, matcher=None)]
    matched = find_matching_rule(rules=rules, subject=PermissionSubject.EDIT, candidate="anything.txt", behavior=PermissionBehavior.DENY)
    assert matched is not None


def test_find_matching_rule_returns_none_when_no_match():
    rules = [PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.ALLOW, source=PermissionSource.SESSION, matcher="*.py")]
    matched = find_matching_rule(rules=rules, subject=PermissionSubject.READ, candidate="data.csv", behavior=PermissionBehavior.ALLOW)
    assert matched is None


def test_permission_decision_metadata_is_immutable():
    from types import MappingProxyType
    decision = PermissionDecision(behavior=PermissionBehavior.ALLOW, reason="test")
    assert isinstance(decision.metadata, MappingProxyType)
    with pytest.raises(TypeError):
        decision.metadata["key"] = "value"


def test_set_mode_returns_updated_context(tmp_path):
    from src.ai.permissions.context import set_mode
    context = build_default_permission_context(workspace_root=tmp_path)
    updated = set_mode(context, PermissionMode.ACCEPT_EDITS)
    assert updated.mode is PermissionMode.ACCEPT_EDITS
    assert context.mode is PermissionMode.DEFAULT  # original unchanged


def test_add_working_directory_appends_directory(tmp_path):
    from src.ai.permissions.context import add_working_directory
    extra = tmp_path / "extra"
    extra.mkdir()
    context = build_default_permission_context(workspace_root=tmp_path)
    updated = add_working_directory(context, extra)
    assert extra.resolve() in updated.working_directories
    assert len(updated.working_directories) == 2


def test_add_rule_appends_rule(tmp_path):
    from src.ai.permissions.context import add_rule
    from src.ai.permissions.types import PermissionBehavior, PermissionRule, PermissionSource, PermissionSubject
    context = build_default_permission_context(workspace_root=tmp_path)
    rule = PermissionRule(subject=PermissionSubject.READ, behavior=PermissionBehavior.DENY, source=PermissionSource.SESSION, matcher="*.log")
    updated = add_rule(context, rule)
    assert rule in updated.rules
    assert len(context.rules) == 0  # original unchanged
