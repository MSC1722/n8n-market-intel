"""Market Intelligence Enrichment API.

A small FastAPI service that n8n calls over HTTP for the parts of the pipeline
that no built-in n8n node can do:

  1. Entity resolution  — alias-aware ticker/actor extraction with
     symbol-vs-word disambiguation.
  2. Story clustering   — SimHash + Jaccard near-duplicate detection that
     persists *across* workflow runs, so the same story arriving from a
     different outlet six hours later is recognised as a repeat.
  3. Relevance scoring  — a deterministic, auditable 0-100 score combining the
     LLM's impact estimate with recency, source reputation and novelty.

Deployed as a second Railway service alongside the n8n instance.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import entities as ent
from . import scoring, store
from .models import (
    EnrichRequest,
    EnrichResponse,
    Entity,
    ScoreBreakdown,
    StatsResponse,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
)
log = logging.getLogger("market-intel")

API_KEY = os.getenv("API_KEY", "")
SERVICE_VERSION = "1.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.connect()
    removed = store.prune(days=int(os.getenv("RETENTION_DAYS", "30")))
    log.info('"startup: db ready, pruned %d old rows"', removed)
    yield


app = FastAPI(
    title="Market Intelligence Enrichment API",
    description=__doc__,
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Header auth. n8n stores the key as a Header Auth credential, so it never
    appears in the workflow JSON that gets published to GitHub."""
    if not API_KEY:
        return  # unset = open, for local development only
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Errors come back in a stable shape so the n8n error branch can format a
    useful Slack message instead of dumping a raw stack trace."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "detail": str(exc.detail),
            "request_id": request.headers.get("x-request-id", "-"),
        },
    )


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {
        "status": "ok",
        "version": SERVICE_VERSION,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post(
    "/v1/enrich",
    response_model=EnrichResponse,
    tags=["enrichment"],
    dependencies=[Depends(require_api_key)],
)
def enrich(payload: EnrichRequest) -> EnrichResponse:
    blob = f"{payload.title}\n{payload.summary}"
    resolved = ent.resolve(blob, payload.tickers)
    signal = ent.entity_signal(resolved)

    cluster = store.assign_cluster(
        url=str(payload.url),
        title=payload.title,
        source=payload.source,
        entities=[e["symbol"] for e in resolved],
        score=0.0,
    )

    total, parts, reason = scoring.score(
        impact_score=payload.impact_score,
        entity_signal_value=signal,
        published_at=payload.published_at,
        source=payload.source,
        is_followup=cluster["is_followup"],
        cluster_size=cluster["cluster_size"],
    )

    log.info(
        '"enriched id=%s score=%.1f entities=%s cluster=%s followup=%s"',
        cluster["id"], total, [e["symbol"] for e in resolved],
        cluster["cluster_id"], cluster["is_followup"],
    )

    return EnrichResponse(
        id=cluster["id"],
        client_ref=payload.client_ref,
        canonical_url=cluster["canonical_url"],
        cluster_id=cluster["cluster_id"],
        is_followup=cluster["is_followup"],
        cluster_size=cluster["cluster_size"],
        entities=[Entity(**e) for e in resolved],
        sectors=ent.sectors_of(resolved),
        relevance_score=total,
        priority=scoring.priority_of(total),
        score_breakdown=ScoreBreakdown(**parts),
        reason=reason,
        processed_at=datetime.now(timezone.utc),
    )


@app.get(
    "/v1/stats",
    response_model=StatsResponse,
    tags=["ops"],
    dependencies=[Depends(require_api_key)],
)
def get_stats() -> StatsResponse:
    return StatsResponse(**store.stats())
