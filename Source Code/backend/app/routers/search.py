"""
Global Search — GET /api/search?q=<query>&limit=<per-type limit>.

Single authorized entry point for the frontend's Cmd/Ctrl+K search palette.
Every entity type is authorized exactly as its own existing endpoint already
authorizes it (see app/services/search_service.py's per-entity docstrings) —
this router adds no new RBAC, it only assembles what security.py and each
router already enforce. Query validation (min length, result-count limits)
happens here so every caller gets the same safe behavior regardless of how
the frontend debounces.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import schemas, security
from ..database import get_db
from ..services import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=schemas.SearchResponse)
def global_search(
    q: str = Query(..., description="Search text"),
    limit: int = Query(search_service.PER_TYPE_LIMIT_DEFAULT, ge=1, le=20, description="Max results per entity type"),
    db: Session = Depends(get_db),
    user=Depends(security.get_current_user),
):
    q = (q or "").strip()
    if len(q) < search_service.MIN_QUERY_LEN:
        # Safe, explicit "too short" response rather than a 422 — the
        # frontend calls this on every keystroke past the first character,
        # and an error here would just be noise for an entirely normal,
        # expected input state.
        return schemas.SearchResponse(query=q, results=[], query_too_short=True)

    results = search_service.search(db, user, q, per_type_limit=limit)
    return schemas.SearchResponse(query=q, results=[schemas.SearchResultOut(**r) for r in results])
