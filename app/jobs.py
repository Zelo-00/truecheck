"""Фоновые задания проверки + прогресс по эпизодам.

In-memory store (один процесс uvicorn). Тяжёлая обработка идёт в потоке, чтобы
длинные документы не упирались в таймаут запроса; фронт опрашивает /status.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("check.jobs")

# ограничение числа одновременно выполняемых проверок (защита ресурсов/ИИ-ключа)
_MAX_CONCURRENT = max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "4")))
_SEMA = threading.Semaphore(_MAX_CONCURRENT)


@dataclass
class Job:
    id: str
    doc_name: str = ""
    state: str = "queued"          # queued | running | done | error
    total: int = 0                 # всего эпизодов
    done: int = 0                  # обработано эпизодов
    error: str = ""
    created: float = field(default_factory=time.time)

    @property
    def progress(self) -> int:
        if self.state == "done":
            return 100
        if self.total <= 0:
            return 5 if self.state == "running" else 0
        return min(99, int(self.done / self.total * 100))

    def as_dict(self) -> dict:
        return {"id": self.id, "state": self.state, "progress": self.progress,
                "done": self.done, "total": self.total, "error": self.error,
                "doc_name": self.doc_name}


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def create(doc_name: str) -> Job:
    """Создаёт задание; его id используется и как id будущего отчёта."""
    job = Job(id=uuid.uuid4().hex[:12], doc_name=doc_name)
    with _LOCK:
        _JOBS[job.id] = job
        _gc()
    return job


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def start(job: Job, target: Callable[[Job], None]) -> None:
    """Запускает target(job) в демон-потоке (с ограничением параллелизма)."""
    def _run() -> None:
        with _SEMA:                         # пока заняты все слоты — задание ждёт (queued)
            job.state = "running"
            try:
                target(job)
                if job.state != "error":
                    job.state = "done"
            except Exception as e:  # noqa: BLE001
                log.exception("задание %s упало", job.id)
                job.error = str(e)[:300]
                job.state = "error"
    threading.Thread(target=_run, daemon=True).start()


def _gc(max_age: int = 3600, max_n: int = 500) -> None:
    now = time.time()
    for k in [k for k, v in _JOBS.items() if now - v.created > max_age]:
        _JOBS.pop(k, None)
    if len(_JOBS) > max_n:
        for k in sorted(_JOBS, key=lambda k: _JOBS[k].created)[: len(_JOBS) - max_n]:
            _JOBS.pop(k, None)
