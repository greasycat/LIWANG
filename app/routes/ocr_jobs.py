from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from .. import store
from ..deps import db

router = APIRouter()


@router.get("/next")
def next_job(request: Request, runner_id: str = "demo-runner"):
    """OCR runner pulls one pending job. Atomic via SELECT … FOR UPDATE SKIP LOCKED."""
    j = store.claim_next_ocr_job(db(request), runner_id)
    if not j:
        return Response(status_code=204)
    return {
        "id": j.id,
        "doc_source": j.doc_source,
        "download_url": f"/internal/ocr-source/{j.id}",
    }


@router.post("/{job_id}/result")
async def post_result(
    request: Request,
    job_id: int,
    status: str = Form("done"),
    error: str | None = Form(None),
):
    if status not in ("done", "failed"):
        return Response(status_code=400)
    j = store.finish_ocr_job(db(request), job_id, status, error)
    if not j:
        return Response(status_code=404)
    return {"ok": True}
