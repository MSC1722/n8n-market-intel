"""Cross-run story clustering, backed by SQLite.

Why this cannot live in n8n:

n8n's "Remove Duplicates" node compares exact field values within a single
execution. This pipeline needs the opposite: fuzzy matching across executions.
The same story reaches Reuters, CNBC and MarketWatch with three different
headlines and three different URLs, hours apart, in three different runs.

SimHash gives a 64-bit fingerprint whose Hamming distance tracks textual
similarity, so near-duplicates collapse into one cluster and the second
telling of a story is demoted rather than re-alerted.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DB_PATH = os.getenv("STORE_PATH", "/data/market_intel.db")
CLUSTER_WINDOW_HOURS = int(os.getenv("CLUSTER_WINDOW_HOURS", "72"))
# Stage 1 (blocking): cheap SimHash Hamming distance to shortlist candidates.
# Stage 2 (decision): Jaccard on the token set, which is far more reliable on
# short headlines where SimHash alone is noisy.
SIMHASH_BLOCK_DISTANCE = int(os.getenv("SIMHASH_BLOCK_DISTANCE", "22"))
JACCARD_THRESHOLD = float(os.getenv("JACCARD_THRESHOLD", "0.45"))

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ito")
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by
with as is are was were be been being it its his her their our your my we you they
he she has have had do does did not no nor so such over under after before about
says say said report reports new news update updates amid amp
""".split())

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    title         TEXT NOT NULL,
    simhash       INTEGER NOT NULL,
    tokens        TEXT NOT NULL DEFAULT '',
    cluster_id    TEXT NOT NULL,
    source        TEXT NOT NULL,
    entities      TEXT NOT NULL DEFAULT '',
    score         REAL NOT NULL DEFAULT 0,
    seen_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_seen ON articles(seen_at);
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url ON articles(canonical_url);
"""


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


# --------------------------------------------------------------------------- #
# URL + text normalisation
# --------------------------------------------------------------------------- #

def canonicalise(url: str) -> str:
    """Strip tracking params and trailing noise so the same story shares a key."""
    parts = urlparse(str(url))
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunparse(("https", netloc, path, "", urlencode(sorted(query)), ""))


def tokenise(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def simhash(text: str, bits: int = 64) -> int:
    """Charikar SimHash over 2-gram shingles of the normalised title."""
    tokens = tokenise(text)
    if not tokens:
        return 0
    shingles = tokens if len(tokens) < 3 else [
        f"{a}_{b}" for a, b in zip(tokens, tokens[1:])
    ]
    vector = [0] * bits
    for shingle in shingles:
        h = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for i in range(bits):
            vector[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i, v in enumerate(vector):
        if v > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


_MASK64 = (1 << 64) - 1


def to_signed(value: int) -> int:
    """SQLite INTEGER is signed 64-bit; SimHash is unsigned 64-bit."""
    return value - (1 << 64) if value >= (1 << 63) else value


def to_unsigned(value: int) -> int:
    return value & _MASK64


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #

def _now() -> datetime:
    return datetime.now(timezone.utc)


def assign_cluster(
    *, url: str, title: str, source: str, entities: list[str], score: float
) -> dict:
    """Insert the article and return its cluster assignment.

    Two-stage matching: SimHash Hamming distance blocks the candidate set,
    then token-set Jaccard decides. Returns cluster_id, is_followup (an earlier
    article already told this story), cluster_size, and whether this exact URL
    was seen before.
    """
    canonical = canonicalise(url)
    article_id = hashlib.sha1(canonical.encode()).hexdigest()[:16]
    fingerprint = simhash(title)
    tokens = set(tokenise(title))
    cutoff = (_now() - timedelta(hours=CLUSTER_WINDOW_HOURS)).isoformat()

    with _lock:
        conn = connect()
        existing = conn.execute(
            "SELECT cluster_id FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        if existing:
            size = conn.execute(
                "SELECT COUNT(*) c FROM articles WHERE cluster_id = ?",
                (existing["cluster_id"],),
            ).fetchone()["c"]
            return {
                "id": article_id,
                "canonical_url": canonical,
                "cluster_id": existing["cluster_id"],
                "is_followup": True,
                "cluster_size": size,
                "already_seen": True,
            }

        candidates = conn.execute(
            "SELECT cluster_id, simhash, tokens FROM articles WHERE seen_at >= ? "
            "ORDER BY seen_at DESC LIMIT 500",
            (cutoff,),
        ).fetchall()

        cluster_id = None
        best_similarity = JACCARD_THRESHOLD
        for row in candidates:
            # Stage 1 — blocking. Skips the expensive comparison for most rows.
            if hamming(fingerprint, to_unsigned(row["simhash"])) > SIMHASH_BLOCK_DISTANCE:
                continue
            # Stage 2 — decision.
            similarity = jaccard(tokens, set(row["tokens"].split(",")))
            if similarity >= best_similarity:
                best_similarity, cluster_id = similarity, row["cluster_id"]

        is_followup = cluster_id is not None
        if cluster_id is None:
            cluster_id = "c_" + article_id[:10]

        conn.execute(
            "INSERT INTO articles (id, canonical_url, title, simhash, tokens, "
            "cluster_id, source, entities, score, seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (article_id, canonical, title[:500], to_signed(fingerprint),
             ",".join(sorted(tokens)), cluster_id, source, ",".join(entities),
             score, _now().isoformat()),
        )
        conn.commit()

        size = conn.execute(
            "SELECT COUNT(*) c FROM articles WHERE cluster_id = ?", (cluster_id,)
        ).fetchone()["c"]

    return {
        "id": article_id,
        "canonical_url": canonical,
        "cluster_id": cluster_id,
        "is_followup": is_followup,
        "cluster_size": size,
        "already_seen": False,
    }


def stats() -> dict:
    with _lock:
        conn = connect()
        totals = conn.execute(
            "SELECT COUNT(*) articles, COUNT(DISTINCT cluster_id) clusters, "
            "MIN(seen_at) oldest, MAX(seen_at) newest FROM articles"
        ).fetchone()
        day_ago = (_now() - timedelta(hours=24)).isoformat()
        recent = conn.execute(
            "SELECT COUNT(*) c FROM articles WHERE seen_at >= ?", (day_ago,)
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT entities FROM articles WHERE seen_at >= ? AND entities != ''",
            (day_ago,),
        ).fetchall()

    tally: dict[str, int] = {}
    for row in rows:
        for symbol in row["entities"].split(","):
            if symbol:
                tally[symbol] = tally.get(symbol, 0) + 1
    top = [{"symbol": k, "count": v} for k, v in
           sorted(tally.items(), key=lambda kv: -kv[1])[:10]]

    return {
        "articles_total": totals["articles"] or 0,
        "clusters_total": totals["clusters"] or 0,
        "articles_last_24h": recent,
        "top_entities": top,
        "oldest_record": totals["oldest"],
        "newest_record": totals["newest"],
    }


def prune(days: int = 30) -> int:
    cutoff = (_now() - timedelta(days=days)).isoformat()
    with _lock:
        conn = connect()
        cur = conn.execute("DELETE FROM articles WHERE seen_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
