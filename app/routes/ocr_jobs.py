from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, Response

from .. import store
from ..deps import db

router = APIRouter()


@router.get("/next")
def next_job(request: Request, runner_id: str = "demo-runner"):
    j = store.claim_next_ocr_job(db(request), runner_id)
    if not j:
        return Response(status_code=204)
    return {
        "id": j.id,
        "doc_source": j.doc_source,
        "download_url": f"/api/internal/ocr-source/{j.id}",
    }


@router.post("/{job_id}/result")
def post_result(
    request: Request,
    job_id: int,
    status: str = Form("done"),
    error: str | None = Form(None),
):
    if status not in ("done", "failed"):
        raise HTTPException(status_code=400)
    j = store.finish_ocr_job(db(request), job_id, status, error)
    if not j:
        raise HTTPException(status_code=404)
    return {"ok": True}
