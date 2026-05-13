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
