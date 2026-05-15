from __future__ import annotations

import threading
import time

from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.app.services import runtime_state


def setup_function() -> None:
    runtime_state.invalidate_runtime_snapshot()


def test_ensure_core_runtime_dedupes_concurrent_cold_builds(workspace, monkeypatch) -> None:
    calls = {"count": 0}
    started = threading.Event()

    monkeypatch.setattr(runtime_state, "get_mcp_servers", lambda *_args, **_kwargs: [])

    def _fake_build_core(**_kwargs):
        calls["count"] += 1
        started.set()
        time.sleep(0.05)
        return ["core"]

    monkeypatch.setattr(runtime_state.aethos_agent, "build_core_aethos_tools", _fake_build_core)

    snapshots: list[runtime_state.WorkspaceRuntimeSnapshot] = []

    def _worker() -> None:
        snapshots.append(
            runtime_state.ensure_core_runtime(
                root_dir=str(workspace),
                backend=None,
                owner_user_id="u1",
                permission_context=None,
                media_block_support=MediaBlockSupport(),
                model=None,
            )
        )

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    started.wait(timeout=1)
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)

    assert len(snapshots) == 2
    assert calls["count"] == 1
    assert snapshots[0].core_tools == ["core"]
    assert snapshots[1].core_tools == ["core"]


def test_invalidate_runtime_snapshot_stops_registered_prewarm_threads(workspace, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_WORKSPACE_PREWARM_ENABLED", "1")
    monkeypatch.setattr(runtime_state, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(runtime_state.aethos_agent, "build_core_aethos_tools", lambda **_kwargs: ["core"])

    release_build = threading.Event()

    def _fake_build_full(**_kwargs):
        release_build.wait(timeout=1)
        return ["full"]

    monkeypatch.setattr(runtime_state.aethos_agent, "build_full_aethos_tools", _fake_build_full)

    snapshot = runtime_state.schedule_runtime_prewarm(
        root_dir=str(workspace),
        backend=None,
        owner_user_id="u1",
        permission_context=None,
        media_block_support=MediaBlockSupport(),
        model=None,
    )

    deadline = time.time() + 1
    while time.time() < deadline:
        with runtime_state._RUNTIME_CACHE_LOCK:
            thread = runtime_state._PREWARM_THREADS.get(snapshot.key)
        if thread is not None:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Prewarm thread was not registered")

    runtime_state.invalidate_runtime_snapshot(root_dir=str(workspace))
    release_build.set()
    thread.join(timeout=1.0)

    with runtime_state._RUNTIME_CACHE_LOCK:
        assert snapshot.key not in runtime_state._PREWARM_THREADS
        assert snapshot.key not in runtime_state._PREWARM_STOP_EVENTS
        assert snapshot.key not in runtime_state._RUNTIME_CACHE


def test_cancelled_prewarm_does_not_publish_full_tools_back_into_cache(workspace, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_WORKSPACE_PREWARM_ENABLED", "1")
    monkeypatch.setattr(runtime_state, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(runtime_state.aethos_agent, "build_core_aethos_tools", lambda **_kwargs: ["core"])

    allow_finish = threading.Event()

    def _fake_build_full(**_kwargs):
        allow_finish.wait(timeout=1)
        return ["full"]

    monkeypatch.setattr(runtime_state.aethos_agent, "build_full_aethos_tools", _fake_build_full)

    snapshot = runtime_state.schedule_runtime_prewarm(
        root_dir=str(workspace),
        backend=None,
        owner_user_id="u1",
        permission_context=None,
        media_block_support=MediaBlockSupport(),
        model=None,
    )

    deadline = time.time() + 1
    while time.time() < deadline:
        with runtime_state._RUNTIME_CACHE_LOCK:
            if snapshot.key in runtime_state._PREWARM_THREADS:
                break
        time.sleep(0.01)
    else:
        raise AssertionError("Prewarm thread was not registered")

    runtime_state.invalidate_runtime_snapshot(root_dir=str(workspace))
    allow_finish.set()
    time.sleep(0.05)

    with runtime_state._RUNTIME_CACHE_LOCK:
        assert snapshot.key not in runtime_state._RUNTIME_CACHE


def test_shutdown_runtime_workers_joins_background_threads(workspace, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_WORKSPACE_PREWARM_ENABLED", "1")
    monkeypatch.setattr(runtime_state, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(runtime_state.aethos_agent, "build_core_aethos_tools", lambda **_kwargs: ["core"])

    started = threading.Event()
    release_build = threading.Event()

    def _fake_build_full(**_kwargs):
        started.set()
        release_build.wait(timeout=1)
        return ["full"]

    monkeypatch.setattr(runtime_state.aethos_agent, "build_full_aethos_tools", _fake_build_full)

    snapshot = runtime_state.schedule_runtime_prewarm(
        root_dir=str(workspace),
        backend=None,
        owner_user_id="u1",
        permission_context=None,
        media_block_support=MediaBlockSupport(),
        model=None,
    )

    assert started.wait(timeout=1)
    release_build.set()
    runtime_state.shutdown_runtime_workers(clear_cache=True, join_timeout=1.0)

    with runtime_state._RUNTIME_CACHE_LOCK:
        assert snapshot.key not in runtime_state._PREWARM_THREADS
        assert snapshot.key not in runtime_state._PREWARM_STOP_EVENTS
