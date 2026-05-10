"""Vector retrieval over `chunks`. Returns Citation rows.

Visibility = (Doc.acl in user's ACL ladder) OR (Doc.owner_user_id == user.id).
The first half lets users see company docs at or below their `acl_max`; the
second lets them retrieve from files they uploaded into their personal space
regardless of acl value (including the `private` sentinel we set there).
"""
from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Chunk, Citation, Doc
from .embedding import embed_query

log = logging.getLogger("liwang.retrieval")


_ACL_VISIBLE: dict[str, set[str]] = {
    "public": {"public"},
    "internal": {"public", "internal"},
    "restricted": {"public", "internal", "restricted"},
}


def retrieve_citations(db: Session, user, query: str, k: int = 4) -> list[Citation]:
    if not query or not query.strip():
        return []
    qvec = embed_query(query)
    visible = _ACL_VISIBLE.get(user.acl_max, {"public"})

    rows = db.execute(
        select(Chunk, Doc)
        .join(Doc, Chunk.doc_id == Doc.id)
        .where(
            Doc.embed_status == "done",
            Doc.no_llm.is_(False),
            or_(
                Doc.acl.in_(visible),
                Doc.owner_user_id == user.id,
            ),
        )
        .order_by(Chunk.embedding.cosine_distance(qvec))
        .limit(k)
    ).all()

    cites: list[Citation] = []
    for i, (chunk, doc) in enumerate(rows, start=1):
        cites.append(
            Citation(
                doc_id=doc.id,
                chunk_id=chunk.id,
                label=f"[{i}]",
                source=doc.source,
                page=chunk.page,
            )
        )
    return cites
