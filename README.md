# Market Intelligence Pipeline

An n8n workflow that turns five financial RSS feeds into a scored, de-duplicated
intelligence feed in Slack and Google Sheets — running on **self-hosted n8n**
(Docker on Railway) with a **custom FastAPI service** doing the work no built-in
node can do.

```
Schedule (6h) → Feed registry → RSS ─┐
                                     ├─→ Normalize & Deduplicate ──→ LLM summarise + classify
                                     ┘         (custom Code node)              │
                                                                               ▼
                                                            Enrich via custom FastAPI service
                                                                               │
                                                     ┌─────────────────────────┴──────────┐
                                                     ▼                                    ▼
                                            score ≥ 70 → Slack alert              error lane →
                                                     └──────────→ Google Sheets    classified
                                                                                   Slack alert
```

| | |
|---|---|
| **Runtime** | n8n 2.x, self-hosted (Docker on Railway, persistent volume, Postgres-optional) |
| **Custom service** | FastAPI + SQLite, deployed as a second Railway container |
| **Model** | `gpt-4o-mini`, JSON-mode, 3 retries with backoff |
| **Nodes** | 13 (4 of them custom JavaScript) |
| **Tests** | 20 (`pytest`) covering entity resolution, clustering and scoring |

---

## Why this is not a drag-and-drop workflow

Anyone can wire an RSS node to an LLM node. Three parts of this pipeline could
not be built that way.

### 1. A Code node that de-duplicates across executions

n8n ships a *Remove Duplicates* node. It compares one field, exactly, inside a
single execution. A news pipeline needs four things it cannot do:

| Problem | Handled by |
|---|---|
| Every feed names fields differently (`isoDate` / `pubDate` / `date`) | Field normalisation with fallbacks |
| The same article arrives with different `utm_*` parameters | URL canonicalisation |
| Two outlets run the same story under different headlines | Jaccard similarity on stop-word-filtered title tokens |
| The run six hours ago already alerted on this story | `getWorkflowStaticData` with a rolling 72-hour window |

The last one matters most, and it has a subtlety: articles suppressed *as*
duplicates have to be written into the memory too. Otherwise the next run drops
the original as "already seen", finds no twin for the retelling still sitting in
the feed, and alerts on the same story twice.

The node is written for the n8n 2.x task runner — no `require()` anywhere, so
the hash function (FNV-1a) is implemented by hand rather than pulled from
`crypto`, which is not allow-listed by default.

### 2. A FastAPI service called over HTTP

[`fastapi-service/`](./fastapi-service) is deployed as its own Railway container
and called by an HTTP Request node. It does three things n8n has no node for:

**Alias-aware entity resolution.** *"the Fed"*, *"FOMC"* and *"Powell"* all
resolve to one symbol. A regex `contains` filter cannot do this, and it also
cannot tell that `"I'm fed up"` is not the central bank or that `"apple
harvest"` is not AAPL — so ambiguous surface forms are only accepted inside a
financial context. Tickers the model *claims* but that appear nowhere in the
text are kept at a 50 % discount and flagged as unverified.

**Story clustering that persists across runs.** Two-stage matching: a 64-bit
SimHash Hamming distance blocks the candidate set cheaply, then token-set
Jaccard makes the decision — SimHash alone is too noisy on short headlines.
State lives in SQLite on a mounted volume, so a story that reaches Reuters at
09:00 and MarketWatch at 15:00 is recognised as one story across two separate
workflow executions.

**Deterministic relevance scoring.** The model returns one subjective number.
That number drifts between runs, ignores how stale an article is, does not know
Reuters outranks an aggregator, and will happily score the fourth retelling of a
story as a fresh 9. So it becomes one input of five:

```
base  = 0.35·impact + 0.28·entity + 0.22·recency + 0.15·source
score = 100 · base · novelty
```

Recency decays exponentially with an 8-hour half-life. Novelty is a
*multiplier*, not another weighted term, because a retelling is not a slightly
less relevant article — it is the same article. It decays as `1/√n` with a floor,
which puts the second outlet on a genuinely big story in the medium tier and the
fifth one below the alert threshold. Every response carries the full breakdown,
so any alert can be audited after the fact.

```jsonc
// same story, first telling vs fifth
{ "relevance_score": 93.27, "priority": "high",
  "reason": "top contributor: impact (0.90), weakest: source (1.00)" }
{ "relevance_score": 38.60, "priority": "low",
  "reason": "…; x0.45 repeat-story penalty (cluster of 5)" }
```

### 3. An error lane that is worth waking up for

The model call and the API call each retry three times with backoff before their
error output fires, so anything reaching the handler is a persistent failure.
The handler classifies it by stage, checks whether the run still delivered
anything at all (`degraded` vs `critical`), and posts one actionable Slack
message instead of a stack trace. Failed items never abort the run — the healthy
ones still reach the sheet.

Every leaf node has an explicit failure policy: a dead RSS feed continues with an
empty item, Slack being down does not stop a row reaching Google Sheets.

---

## Repository layout

```
workflows/market-intel-pipeline.json   Importable n8n workflow (13 nodes + sticky notes)
fastapi-service/                       Enrichment API
  app/entities.py                      Alias-aware entity resolution
  app/store.py                         SimHash + Jaccard clustering, SQLite-backed
  app/scoring.py                       Deterministic relevance scoring
  app/main.py                          FastAPI surface, header auth, structured errors
  tests/test_api.py                    20 tests
docs/RAILWAY_SETUP.md                  Self-hosting n8n 2.x on Railway
docs/DEPLOY_API.md                     Deploying the enrichment service
docs/CREDENTIALS_SETUP.md              OpenAI / Google Sheets / Slack / header auth
```

## Running the API locally

```bash
cd fastapi-service
pip install -r requirements.txt && pip install pytest httpx
STORE_PATH=./local.db API_KEY=dev pytest -q          # 20 passed
STORE_PATH=./local.db API_KEY=dev uvicorn app.main:app --reload
```

```bash
curl -X POST localhost:8000/v1/enrich -H "X-API-Key: dev" -H "Content-Type: application/json" -d '{
  "title": "Fed holds interest rates steady as inflation cools",
  "url": "https://www.reuters.com/markets/fed-holds/?utm_source=twitter",
  "source": "Reuters", "impact_score": 8.5, "client_ref": "demo"
}'
```

## Notes on n8n 2.x

The workflow targets n8n 2.x, where several self-hosting defaults changed:
task runners are on by default (Code nodes run isolated, `process.env` is
blocked), the in-memory binary data mode was removed, `N8N_BASIC_AUTH_*` is gone
in favour of the owner account, and *Activate* became *Publish*. `docs/RAILWAY_SETUP.md`
covers the full environment configuration.

## Security

No secret is present in this repository. API keys live in n8n credentials
(OpenAI, Header Auth, Google OAuth2, Slack bot token); the workflow JSON carries
credential *ids* only. The enrichment service authenticates via `X-API-Key`.

## Licence

MIT
