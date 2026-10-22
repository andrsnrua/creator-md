"""Drain existing historical queues in resumable, visible batches."""
from __future__ import annotations

import os
import shutil
import time
from .content_project import ContentProject
from .library import Library, now
from .storage import atomic_json, file_lock
from .web_ui import JobStore


def run(library: Library, *, once: bool = False, max_batches: int | None = None) -> dict:
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches debe ser positivo.")
    report_path = library.root / ".creator-md/backfill-progress.json"
    # A daily sync and the historical worker must not compete for the same sources.
    with file_lock(library.root / ".creator-md/backfill.lock"), file_lock(library.root / ".creator-md/sync.lock"):
        jobs = JobStore(library.root)
        batch = 0
        while True:
            sources = [s for s in library.load()["sources"] if s["enabled"]]
            sources.sort(key=lambda s: "sebastian" not in s["project"])
            ran = False
            for source in sources:
                current = library.load()
                source = next((s for s in current["sources"] if s["id"] == source["id"]), None)
                if not source or not source["enabled"]:
                    continue
                if not current["settings"]["enabled"]:
                    report = {"status": "paused", "at": now(), "note": "Programación de biblioteca pausada; pendientes conservados."}
                    atomic_json(report_path, report)
                    return report
                content = ContentProject(library.root, source["project"], category=source["category"])
                before = content.status()
                if not before["pending"]:
                    continue
                if shutil.disk_usage(library.root).free < 2 * 1024 ** 3:
                    report = {"status": "waiting_disk", "at": now(), "error": "Quedan menos de 2 GB libres. Se conservan los pendientes."}
                    atomic_json(report_path, report)
                    return report
                count = min(25, max(1, int(current["settings"]["process_limit"])))
                job_id = jobs.start("pending", {"project": source["project"], "category": source["category"], "count": count})
                batch += 1
                report = {"status": "running", "pid": os.getpid(), "job": job_id,
                          "source": source["id"], "batch": batch, "at": now()}
                atomic_json(report_path, report)
                print(f"Lote {batch}: {source['project']} · {job_id}", flush=True)
                while (job := jobs.get(job_id))["status"] == "running":
                    time.sleep(2)
                if job["status"] != "completed":
                    report.update(status="failed", error=job.get("error"), at=now())
                    atomic_json(report_path, report)
                    return report
                summary = content.status()
                if summary["pending"] >= before["pending"] or summary["completed"] <= before["completed"]:
                    report.update(status="stopped_no_progress", pending=summary["pending"], at=now(),
                                  error="El lote no produjo transcripciones nuevas. Revisar diagnóstico antes de continuar; no se reintenta indefinidamente.")
                    atomic_json(report_path, report)
                    return report
                print(f"{source['project']}: {summary['completed']} procesados; {summary['pending']} pendientes", flush=True)
                report.update(status="between_batches", completed=summary["completed"], pending=summary["pending"], at=now())
                atomic_json(report_path, report)
                ran = True
                if once or (max_batches is not None and batch >= max_batches):
                    report.update(status="batch_limit_reached", note="Límite de esta ejecución alcanzado; pendientes conservados.")
                    atomic_json(report_path, report)
                    return report
            if not ran:
                break
        report = {"status": "completed", "batches": batch, "at": now(),
                  "note": "Cola procesada. Revisar por separado fallidos, OCR y cobertura."}
        atomic_json(report_path, report)
        return report
