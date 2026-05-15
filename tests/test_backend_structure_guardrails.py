from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _offending_files(*, root: Path, forbidden_prefix: str) -> list[Path]:
    offenders: list[Path] = []
    for path in _python_files(root):
        imported = _imported_modules(path)
        if any(
            module == forbidden_prefix or module.startswith(f"{forbidden_prefix}.")
            for module in imported
        ):
            offenders.append(path)
    return offenders


def _offending_files_except(*, root: Path, forbidden_prefix: str, allowlist: set[Path]) -> list[Path]:
    offenders: list[Path] = []
    for path in _python_files(root):
        if path in allowlist:
            continue
        imported = _imported_modules(path)
        if any(
            module == forbidden_prefix or module.startswith(f"{forbidden_prefix}.")
            for module in imported
        ):
            offenders.append(path)
    return offenders


def test_no_source_or_tests_import_legacy_repositories_services_namespace() -> None:
    offenders = _offending_files(root=SRC_ROOT, forbidden_prefix="src.app.repositories.services")
    offenders.extend(
        _offending_files(
            root=REPO_ROOT / "tests",
            forbidden_prefix="src.app.repositories.services",
        )
    )

    assert offenders == [], (
        "Found imports from retired namespace 'src.app.repositories.services':\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in offenders)
    )


def test_feature_packages_do_not_import_transitional_modules_namespace() -> None:
    features_root = SRC_ROOT / "app" / "features"
    if not features_root.exists():
        return

    offenders = _offending_files(root=features_root, forbidden_prefix="src.app.modules")

    assert offenders == [], (
        "Feature packages should not depend on transitional 'src.app.modules' imports:\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in offenders)
    )


def test_router_assembly_uses_feature_namespace_for_active_chat_and_extensions() -> None:
    router_path = SRC_ROOT / "app" / "api" / "router.py"
    imported = _imported_modules(router_path)

    forbidden = {
        "src.app.modules.chat.router",
        "src.app.modules.extensions.router",
    }
    used_forbidden = sorted(module for module in imported if module in forbidden)
    assert used_forbidden == [], (
        "src.app.api.router must include active chat/extensions routers from features namespace, "
        f"found transitional imports: {used_forbidden}"
    )


def test_no_new_active_imports_from_transitional_chat_extensions_namespace() -> None:
    allowed_sources = {
        SRC_ROOT / "app" / "modules" / "chat" / "__init__.py",
        SRC_ROOT / "app" / "modules" / "chat" / "router.py",
        SRC_ROOT / "app" / "modules" / "extensions" / "__init__.py",
        SRC_ROOT / "app" / "modules" / "extensions" / "router.py",
    }

    offenders = _offending_files_except(
        root=SRC_ROOT,
        forbidden_prefix="src.app.modules.chat",
        allowlist=allowed_sources,
    )
    offenders.extend(
        _offending_files_except(
            root=SRC_ROOT,
            forbidden_prefix="src.app.modules.extensions",
            allowlist=allowed_sources,
        )
    )
    offenders.extend(
        _offending_files(root=REPO_ROOT / "tests", forbidden_prefix="src.app.modules.chat")
    )
    offenders.extend(
        _offending_files(root=REPO_ROOT / "tests", forbidden_prefix="src.app.modules.extensions")
    )

    offenders = sorted(set(offenders))
    assert offenders == [], (
        "Found imports from transitional chat/extensions namespaces outside allowed compatibility shims:\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in offenders)
    )

def test_no_new_imports_from_transitional_modules_namespace_outside_allowlist() -> None:
    """Block new dependencies on ``src.app.modules.*`` during the deprecation window.

    Compatibility shims under modules/chat and modules/extensions remain allowlisted
    for one release cycle while callers migrate to ``src.app.features.*``.
    """

    allowed_sources = {
        SRC_ROOT / "app" / "modules" / "chat" / "__init__.py",
        SRC_ROOT / "app" / "modules" / "chat" / "router.py",
        SRC_ROOT / "app" / "modules" / "extensions" / "__init__.py",
        SRC_ROOT / "app" / "modules" / "extensions" / "router.py",
    }

    offenders = _offending_files_except(
        root=SRC_ROOT,
        forbidden_prefix="src.app.modules",
        allowlist=allowed_sources,
    )
    offenders.extend(
        _offending_files(root=REPO_ROOT / "tests", forbidden_prefix="src.app.modules")
    )

    offenders = sorted(set(offenders))
    assert offenders == [], (
        "Found imports from transitional modules namespace outside allowlisted compatibility shims:\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in offenders)
    )

def test_transitional_modules_namespace_is_limited_to_thin_shims() -> None:
    modules_root = SRC_ROOT / "app" / "modules"
    if not modules_root.exists():
        return

    expected = {
        modules_root / "__init__.py",
        modules_root / "chat" / "__init__.py",
        modules_root / "chat" / "router.py",
        modules_root / "extensions" / "__init__.py",
        modules_root / "extensions" / "router.py",
    }

    actual = {
        path
        for path in _python_files(modules_root)
        if "__pycache__" not in path.parts
    }

    assert actual == expected, (
        "Transitional modules namespace should contain only thin compatibility shims:\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in sorted(actual - expected))
    )

def test_active_source_has_no_unexpected_legacy_imports() -> None:
    allowed_sources = {
        SRC_ROOT / "app" / "legacy" / "thread_index.py",
        SRC_ROOT / "app" / "legacy" / "thread_store.py",
        SRC_ROOT / "app" / "legacy" / "postgres_thread_store.py",
    }

    offenders = _offending_files_except(
        root=SRC_ROOT,
        forbidden_prefix="src.app.legacy",
        allowlist=allowed_sources,
    )

    assert offenders == [], (
        "Active source should not depend on legacy modules outside compatibility shims:\n"
        + "\n".join(str(path.relative_to(REPO_ROOT)) for path in offenders)
    )
