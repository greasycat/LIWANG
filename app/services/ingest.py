"""Background ingest pipeline: Doc.file_path → chunks(embedding)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete

from .. import store
from ..config import settings
from ..db import SessionLocal
from ..models import Chunk, Doc
from .embedding import embed_batch
from .extraction import extract_text

log = logging.getLogger("liwang.ingest")


@dataclass
class _Piece:
    text: str
    page: int | None


def _chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[_Piece]:
    from llama_index.core.node_parser import SentenceSplitter

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    out: list[_Piece] = []
    for page_no, text in pages:
        if not text or not text.strip():
            continue
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if piece:
                out.append(_Piece(text=piece, page=page_no or None))
    return out


async def ingest_doc(doc_id: str) -> bool:
    """Generic ingest. Reads Doc.file_path, parses, chunks, embeds, replaces
    any prior chunks. Returns True on success.
    """
    # snapshot + mark embedding + clear prior chunks
    with SessionLocal() as db:
        doc = db.get(Doc, doc_id)
        if not doc:
            log.warning("ingest: doc %s not found", doc_id)
            return False
        if not doc.file_path:
            doc.embed_status = "failed"
            db.commit()
            return False
        meta = {
            "mime": doc.mime,
            "file_path": doc.file_path,
            "source": doc.source,
        }
        doc.embed_status = "embedding"
        db.execute(delete(Chunk).where(Chunk.doc_id == doc_id))
        doc.chunks = 0
        db.commit()

    abs_path = (settings.files_root / meta["file_path"]).resolve()
    try:
        text, pages = await asyncio.to_thread(
            extract_text, abs_path, meta["mime"], meta["source"]
        )
        if not text.strip():
            raise ValueError("no extractable text")

        pieces = _chunk_pages(
            pages, settings.chunk_size, settings.chunk_overlap
        )
        if not pieces:
            raise ValueError("no chunks produced")

        embeddings = await asyncio.to_thread(embed_batch, [p.text for p in pieces])
        if len(embeddings) != len(pieces):
            raise ValueError(
                f"embed count mismatch: {len(embeddings)} vs {len(pieces)}"
            )

        with SessionLocal() as db:
            for i, (p, e) in enumerate(zip(pieces, embeddings)):
                db.add(
                    Chunk(
                        id=str(uuid4()),
                        doc_id=doc_id,
                        ord=i,
                        content=p.text,
                        embedding=e,
                        page=p.page,
                    )
                )
            d_doc = db.get(Doc, doc_id)
            if d_doc:
                d_doc.chunks = len(pieces)
                d_doc.embed_status = "done"
            db.commit()
        log.info("ingest done: doc=%s chunks=%d", doc_id, len(pieces))
        return True

    except Exception as ex:
        log.exception("ingest failed for doc=%s", doc_id)
        with SessionLocal() as db:
            d_doc = db.get(Doc, doc_id)
            if d_doc:
                d_doc.embed_status = "failed"
            db.commit()
        return False


async def ingest_upload(upload_id: str) -> None:
    """Admin staging-table flow: promote a queued Upload row → Doc + chunks.
    Updates the Upload row's status/progress so the admin upload UI reflects
    pipeline state."""
    with SessionLocal() as db:
        item = store.get_upload(db, upload_id)
        if not item:
            log.warning("ingest_upload: upload %s not found", upload_id)
            return
        if not item.file_path:
            store.update_upload(
                db, upload_id, status="failed", error="no file on disk"
            )
            return

        doc = Doc(
            id=str(uuid4()),
            source=item.filename,
            dept=item.dept or "",
            doc_type=item.doc_type or "其他",
            version=item.version or "v1",
            effective_date=store.now().strftime("%Y-%m-%d"),
            acl=item.acl or "internal",
            no_llm=bool(item.no_llm),
            chunks=0,
            embed_status="embedding",
            uploaded_by=str(item.uploaded_by or ""),
            uploaded_at=store.now(),
            file_path=item.file_path,
            mime=item.mime,
            owner_user_id=None,  # admin-uploaded → company doc
        )
        db.add(doc)
        store.update_upload(
            db,
            upload_id,
            status="parsing",
            progress=15,
            doc_id=doc.id,
            error=None,
        )
        doc_id = doc.id
        db.commit()

    # progress: parsing/embedding tracked at the upload level too
    with SessionLocal() as db:
        store.update_upload(db, upload_id, status="embedding", progress=55)

    ok = await ingest_doc(doc_id)

    with SessionLocal() as db:
        if ok:
            store.update_upload(
                db, upload_id, status="done", progress=100, error=None
            )
        else:
            store.update_upload(
                db,
                upload_id,
                status="failed",
                progress=0,
                error="ingest failed (see server logs)",
            )
