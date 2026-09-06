"""Entity resolution.

n8n has no node for this. A regex "contains" filter cannot tell you that
"the Fed", "FOMC" and "Federal Reserve" are the same actor, that "Apple"
in "Apple Inc. earnings" is AAPL but "apple harvest" is not, or that a
headline mentioning TSMC is really about the semiconductor sector.

The resolver below does alias matching with word boundaries, symbol-vs-word
disambiguation, and sector rollup, and returns *which* surface forms matched
so the score stays auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityDef:
    symbol: str
    name: str
    type: str
    sector: str | None = None
    weight: float = 0.6
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Surface forms that are too generic to match on their own.
    requires_context: tuple[str, ...] = field(default_factory=tuple)


# Curated registry. Deliberately small and hand-tuned: precision beats recall
# for an alerting pipeline, because every false positive becomes a Slack ping.
REGISTRY: tuple[EntityDef, ...] = (
    # --- central banks / macro ---
    EntityDef("FED", "US Federal Reserve", "central_bank", "macro", 1.0,
              ("federal reserve", "the fed", "fomc", "jerome powell", "powell"),
              requires_context=("fed",)),
    EntityDef("ECB", "European Central Bank", "central_bank", "macro", 0.9,
              ("european central bank", "ecb", "christine lagarde", "lagarde")),
    EntityDef("BOJ", "Bank of Japan", "central_bank", "macro", 0.8,
              ("bank of japan", "boj", "ueda")),
    EntityDef("PBOC", "People's Bank of China", "central_bank", "macro", 0.8,
              ("people's bank of china", "pboc")),
    EntityDef("CPI", "US Inflation Print", "macro", "macro", 0.9,
              ("cpi", "consumer price index", "inflation data", "pce inflation")),
    EntityDef("JOBS", "US Labour Market", "macro", "macro", 0.8,
              ("nonfarm payrolls", "non-farm payrolls", "jobs report",
               "unemployment rate", "jobless claims")),
    EntityDef("TARIFF", "Trade & Tariffs", "macro", "macro", 0.8,
              ("tariff", "tariffs", "trade war", "export controls", "sanctions")),

    # --- mega-cap equities ---
    EntityDef("NVDA", "NVIDIA", "equity", "semiconductors", 1.0,
              ("nvidia", "nvda")),
    EntityDef("AAPL", "Apple", "equity", "consumer_tech", 0.9,
              ("apple inc", "apple's", "aapl"), requires_context=("apple",)),
    EntityDef("MSFT", "Microsoft", "equity", "software", 0.9,
              ("microsoft", "msft")),
    EntityDef("GOOGL", "Alphabet", "equity", "software", 0.9,
              ("alphabet", "googl", "google")),
    EntityDef("AMZN", "Amazon", "equity", "consumer", 0.9,
              ("amazon", "amzn")),
    EntityDef("META", "Meta Platforms", "equity", "software", 0.85,
              ("meta platforms", "facebook", "meta's"), requires_context=("meta",)),
    EntityDef("TSLA", "Tesla", "equity", "auto", 0.85, ("tesla", "tsla")),
    EntityDef("AMD", "AMD", "equity", "semiconductors", 0.8,
              ("advanced micro devices", "amd")),
    EntityDef("INTC", "Intel", "equity", "semiconductors", 0.8, ("intel", "intc")),
    EntityDef("TSM", "TSMC", "equity", "semiconductors", 0.9,
              ("tsmc", "taiwan semiconductor", "tsm")),
    EntityDef("ASML", "ASML", "equity", "semiconductors", 0.8, ("asml",)),
    EntityDef("OPENAI", "OpenAI", "equity", "ai", 0.85, ("openai", "open ai")),
    EntityDef("ANTHROPIC", "Anthropic", "equity", "ai", 0.8, ("anthropic",)),
    EntityDef("JPM", "JPMorgan", "equity", "financials", 0.8,
              ("jpmorgan", "jp morgan", "jpm")),
    EntityDef("GS", "Goldman Sachs", "equity", "financials", 0.8,
              ("goldman sachs", "goldman")),

    # --- commodities / crypto / indices ---
    EntityDef("OIL", "Crude Oil", "commodity", "energy", 0.8,
              ("crude oil", "brent", "wti", "opec", "opec+")),
    EntityDef("GOLD", "Gold", "commodity", "metals", 0.7, ("gold price", "bullion")),
    EntityDef("BTC", "Bitcoin", "crypto", "crypto", 0.8, ("bitcoin", "btc")),
    EntityDef("ETH", "Ethereum", "crypto", "crypto", 0.7, ("ethereum", "ether")),
    EntityDef("SPX", "S&P 500", "index", "macro", 0.7,
              ("s&p 500", "s&p500", "spx", "wall street")),
    EntityDef("NDX", "Nasdaq", "index", "macro", 0.7, ("nasdaq", "ndx")),
)

_BY_SYMBOL = {e.symbol: e for e in REGISTRY}

# Words that make a generic surface form ("apple", "meta") count as the company.
_CONTEXT_TERMS = (
    "earnings", "revenue", "shares", "stock", "quarter", "guidance", "ceo",
    "chip", "iphone", "ai", "lawsuit", "antitrust", "market cap", "investors",
    "analyst", "nasdaq", "buyback", "dividend", "layoff", "acquisition",
    "rate", "rates", "yield", "bond", "inflation", "economy", "central bank",
    "policy", "trading", "index", "futures", "recession", "gdp",
)


def _compile(alias: str) -> re.Pattern[str]:
    # Word-boundary match that tolerates '+', '&', '.' inside aliases (opec+, s&p 500).
    escaped = re.escape(alias).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![\w]){escaped}(?![\w])", re.IGNORECASE)


_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    e.symbol: [(a, _compile(a)) for a in (*e.aliases, *e.requires_context)]
    for e in REGISTRY
}
_CONTEXT_RE = re.compile("|".join(re.escape(t) for t in _CONTEXT_TERMS), re.IGNORECASE)


def resolve(text: str, hinted_tickers: list[str] | None = None) -> list[dict]:
    """Return resolved entities, highest weight first."""
    blob = text or ""
    has_context = bool(_CONTEXT_RE.search(blob))
    hinted = {t.upper() for t in (hinted_tickers or [])}
    found: list[dict] = []

    for entity in REGISTRY:
        matched: list[str] = []
        for alias, pattern in _PATTERNS[entity.symbol]:
            if not pattern.search(blob):
                continue
            # Ambiguous surface form: only accept it inside a financial context.
            if alias in entity.requires_context and not has_context:
                continue
            matched.append(alias)

        if not matched and entity.symbol in hinted:
            # The LLM claimed this ticker but no surface form is present.
            # Keep it, at a discount — unverified.
            matched = ["llm_hint"]
            confidence = 0.5
        elif matched:
            confidence = 1.0
        else:
            continue

        found.append(
            {
                "symbol": entity.symbol,
                "name": entity.name,
                "type": entity.type,
                "sector": entity.sector,
                "matched": sorted(set(matched)),
                "weight": round(entity.weight * confidence, 3),
            }
        )

    found.sort(key=lambda e: (-e["weight"], e["symbol"]))
    return found[:10]


def sectors_of(entities: list[dict]) -> list[str]:
    return sorted({e["sector"] for e in entities if e.get("sector")})


def entity_signal(entities: list[dict]) -> float:
    """Collapse the entity list into a 0-1 signal.

    One heavyweight entity is worth more than three fringe ones, so this is a
    saturating sum rather than a mean: 1 - prod(1 - w).
    """
    if not entities:
        return 0.0
    residual = 1.0
    for e in entities:
        residual *= 1.0 - min(e["weight"], 0.85)
    return round(1.0 - residual, 4)
