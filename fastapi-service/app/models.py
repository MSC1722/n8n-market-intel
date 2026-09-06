"""Pydantic request/response contracts for the enrichment API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Priority = Literal["high", "medium", "low"]


class Entity(BaseModel):
    symbol: str = Field(..., description="Canonical symbol, e.g. NVDA or FED")
    name: str
    type: Literal["equity", "central_bank", "commodity", "crypto", "index", "macro"]
    sector: str | None = None
    matched: list[str] = Field(default_factory=list, description="Surface forms found in the text")
    weight: float = Field(..., ge=0.0, le=1.0)


class ScoreBreakdown(BaseModel):
    impact: float = Field(..., ge=0.0, le=1.0)
    entity: float = Field(..., ge=0.0, le=1.0)
    recency: float = Field(..., ge=0.0, le=1.0)
    source: float = Field(..., ge=0.0, le=1.0)
    novelty: float = Field(..., ge=0.0, le=1.0)


class EnrichRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=512)
    summary: str = Field(default="", max_length=4000)
    url: HttpUrl
    source: str = Field(default="unknown", max_length=64)
    published_at: datetime | None = None
    category: str = Field(default="general", max_length=64)
    impact_score: float = Field(default=5.0, ge=0.0, le=10.0, description="LLM impact estimate, 0-10")
    sentiment: Literal["positive", "negative", "neutral"] = "neutral"
    tickers: list[str] = Field(default_factory=list, description="Optional LLM ticker guesses")
    client_ref: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Opaque correlation id echoed back verbatim. n8n uses it to re-join "
            "this response to the article it came from without relying on item "
            "ordering, which breaks as soon as one item takes the error branch."
        ),
    )

    @field_validator("source")
    @classmethod
    def _normalise_source(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_") or "unknown"

    @field_validator("tickers")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        return [t.strip().upper() for t in v if t and t.strip()][:20]


class EnrichResponse(BaseModel):
    id: str
    client_ref: str | None = None
    canonical_url: str
    cluster_id: str
    is_followup: bool
    cluster_size: int
    entities: list[Entity]
    sectors: list[str]
    relevance_score: float = Field(..., ge=0.0, le=100.0)
    priority: Priority
    score_breakdown: ScoreBreakdown
    reason: str
    processed_at: datetime


class StatsResponse(BaseModel):
    articles_total: int
    clusters_total: int
    articles_last_24h: int
    top_entities: list[dict]
    oldest_record: datetime | None
    newest_record: datetime | None


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str
