from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterator

from src.logger import get_logger

logger = get_logger(__name__)

_DETAILED_PROFILING = os.getenv("AETHOS_PROFILE_DETAILED", "").strip().lower() in {"1", "true", "yes", "on"}
_SAMPLE_RATE = float(os.getenv("AETHOS_PROFILE_SAMPLE_RATE", "0.1") or "0.1")
_ENABLED = _DETAILED_PROFILING or random.random() < max(0.0, min(1.0, _SAMPLE_RATE))
_STARTUP_SESSION = os.getenv("AETHOS_PROFILE_SESSION", str(int(time.time() * 1000)))


@dataclass
class _Checkpoint:
    name: str
    started_at: float


class StartupProfiler:
    def __init__(self) -> None:
        self._checkpoints: list[_Checkpoint] = []
        self._lock = Lock()
        self._reported = False

    def checkpoint(self, name: str) -> None:
        if not _ENABLED:
            return
        with self._lock:
            self._checkpoints.append(_Checkpoint(name=name, started_at=time.perf_counter()))

    def report(self) -> None:
        if not _ENABLED:
            return
        with self._lock:
            if self._reported or not self._checkpoints:
                return
            self._reported = True
            checkpoints = list(self._checkpoints)

        previous = checkpoints[0].started_at
        lines = [
            f"Startup profile report (session={_STARTUP_SESSION}, checkpoints={len(checkpoints)})"
        ]
        for item in checkpoints:
            delta_ms = (item.started_at - previous) * 1000
            total_ms = (item.started_at - checkpoints[0].started_at) * 1000
            lines.append(
                f"startup phase={item.name} delta_ms={delta_ms:.2f} total_ms={total_ms:.2f}"
            )
            previous = item.started_at
        logger.info("%s", " | ".join(lines))

        if _DETAILED_PROFILING:
            log_dir = Path(os.getenv("AETHOS_LOG_DIR") or (Path.cwd() / "logs")).expanduser().resolve()
            log_dir.mkdir(parents=True, exist_ok=True)
            target = log_dir / f"startup-profile-{_STARTUP_SESSION}.log"
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")


startup_profiler = StartupProfiler()


class PhaseProfiler:
    def __init__(self, name: str, *, request_id: str | None = None, metadata: dict[str, object] | None = None) -> None:
        self.name = name
        self.request_id = request_id
        self.metadata = metadata or {}
        self.started_at = time.perf_counter()
        self._last_mark = self.started_at
        self._events: list[tuple[str, float, float]] = []

    def mark(self, phase: str) -> None:
        now = time.perf_counter()
        self._events.append((phase, (now - self._last_mark) * 1000, (now - self.started_at) * 1000))
        self._last_mark = now

    def finish(self) -> None:
        total_ms = (time.perf_counter() - self.started_at) * 1000
        meta = " ".join(f"{key}={value}" for key, value in self.metadata.items())
        header = f"profile name={self.name} request_id={self.request_id or '-'} total_ms={total_ms:.2f}"
        if meta:
            header += f" {meta}"
        if not self._events:
            logger.info(header)
            return
        parts = [header]
        for phase, delta_ms, total_phase_ms in self._events:
            parts.append(f"phase={phase} delta_ms={delta_ms:.2f} total_ms={total_phase_ms:.2f}")
        logger.info(" | ".join(parts))


@contextmanager
def profile_phase(
    name: str,
    *,
    request_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> Iterator[PhaseProfiler]:
    profiler = PhaseProfiler(name=name, request_id=request_id, metadata=metadata)
    try:
        yield profiler
    finally:
        profiler.finish()

