"""Exécution de tâches longues en arrière-plan : progression persistée, annulation coopérative."""
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import update

from app.core.database import SessionLocal
from app.models.entities import Job

log = logging.getLogger("jobs")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
_cancel: dict[int, threading.Event] = {}
_procs: dict[int, set[subprocess.Popen]] = {}
_lock = threading.Lock()


class Cancelled(Exception):
    pass


class JobContext:
    """Passé à la fonction de travail : progression, annulation, sous-processus annulables."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self._last = 0.0

    @property
    def cancelled(self) -> bool:
        return _cancel[self.job_id].is_set()

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled()

    def progress(self, value: float, message: str | None = None, force: bool = False) -> None:
        self.check()
        now = time.monotonic()
        if not force and now - self._last < 0.5:
            return
        self._last = now
        values: dict = {"progress": max(0.0, min(1.0, value))}
        if message is not None:
            values["message"] = message
        with SessionLocal() as db:
            db.execute(update(Job).where(Job.id == self.job_id).values(**values))
            db.commit()

    def popen(self, cmd: list[str], **kw) -> subprocess.Popen:
        """Lance un sous-processus qui sera tué si la tâche est annulée."""
        self.check()
        p = subprocess.Popen(cmd, **kw)
        with _lock:
            _procs.setdefault(self.job_id, set()).add(p)
        return p

    def release(self, p: subprocess.Popen) -> None:
        with _lock:
            _procs.get(self.job_id, set()).discard(p)


def _set(job_id: int, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id).values(**values))
        db.commit()


def submit(job_type: str, target_id: int | None, fn: Callable[[JobContext], dict]) -> Job:
    with SessionLocal() as db:
        job = Job(type=job_type, target_id=target_id, status="queued", message="En attente…")
        db.add(job)
        db.commit()
        db.refresh(job)
    _cancel[job.id] = threading.Event()

    def run():
        ctx = JobContext(job.id)
        try:
            ctx.check()
            _set(job.id, status="running", message="Démarrage…")
            result = fn(ctx) or {}
            _set(job.id, status="done", progress=1.0, message="Terminé", result=result)
        except Cancelled:
            _set(job.id, status="cancelled", message="Annulé par l'utilisateur")
        except Exception as e:  # noqa: BLE001
            if _cancel[job.id].is_set():
                _set(job.id, status="cancelled", message="Annulé par l'utilisateur")
            else:
                log.exception("Échec de la tâche %s #%s", job_type, job.id)
                detail = getattr(e, "message", None) or str(e) or e.__class__.__name__
                _set(job.id, status="failed", message="Échec", error=detail[:2000])
        finally:
            with _lock:
                _procs.pop(job.id, None)

    _executor.submit(run)
    return job


def cancel(job_id: int) -> bool:
    ev = _cancel.get(job_id)
    if not ev:
        return False
    ev.set()
    with _lock:
        for p in list(_procs.get(job_id, ())):
            if p.poll() is None:
                p.kill()
    return True


def mark_interrupted_on_startup() -> None:
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.status.in_(["queued", "running"]))
                   .values(status="interrupted", message="Interrompue (redémarrage du serveur)"))
        db.commit()
