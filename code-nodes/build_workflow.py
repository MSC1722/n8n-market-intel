import json, pathlib

B = pathlib.Path(__file__).parent
js = lambda n: (B / n).read_text()

SYSTEM_PROMPT = (
    "You are a financial news analyst. For the single article given, return ONLY a JSON object "
    "with exactly these keys:\n"
    '  "id"           — copy the Article ID verbatim, unchanged.\n'
    '  "summary"      — 1-2 sentences, max 300 characters, factual, no hedging, no preamble.\n'
    '  "category"     — one of: monetary_policy, earnings, macro_data, geopolitics, commodities, '
    "crypto, corporate_action, general.\n"
    '  "sentiment"    — one of: positive, negative, neutral (market impact, not tone of writing).\n'
    '  "impact_score" — number 0-10. How much this moves markets in the next 24h. Reserve 8+ for '
    "rate decisions, mega-cap earnings surprises, and major geopolitical shocks. Routine coverage is 3-5.\n"
    '  "tickers"      — array of uppercase tickers or symbols explicitly discussed; empty array if none.\n'
    "No markdown, no code fences, no commentary. If the article is not about markets or the economy, "
    'still return the object with category "general" and a low impact_score.'
)

USER_PROMPT = (
    "=Article ID: {{ $json.id }}\n"
    "Source: {{ $json.source }}\n"
    "Published: {{ $json.published_at }}\n"
    "Headline: {{ $json.title }}\n"
    "Excerpt: {{ $json.excerpt }}"
)

ENRICH_BODY = (
    "={{ JSON.stringify({ title: $json.title, summary: $json.summary, url: $json.url, "
    "source: $json.source, published_at: $json.published_at, category: $json.category, "
    "impact_score: $json.impact_score, sentiment: $json.sentiment, tickers: $json.tickers, "
    "client_ref: $json.id }) }}"
)

ALERT_TEXT = (
    "=:rotating_light: *{{ $json.priority.toUpperCase() }} — {{ $json.relevance_score }}/100*  "
    "_{{ $json.category }} · {{ $json.sentiment }}_\n"
    "*{{ $json.title }}*\n"
    "{{ $json.summary }}\n"
    "> entities: `{{ $json.entities || 'none resolved' }}`  ·  source: {{ $json.source }}  ·  "
    "age: {{ $json.age_hours }}h\n"
    "> scoring: {{ $json.score_reason }}\n"
    "{{ $json.url }}"
)

FAILURE_TEXT = (
    "=:warning: *Market Intelligence pipeline — {{ $json.severity }}*\n"
    "{{ $json.failed_count }} item(s) failed after retries · {{ $json.delivered_count }} delivered "
    "successfully\n"
    "Failing stages: `{{ $json.stages }}`\n"
    "```{{ $json.sample }}```\n"
    "_execution {{ $json.execution_id }} · {{ $json.failed_at }}_"
)

STICKY_INTRO = (
    "## Market Intelligence Pipeline\n"
    "RSS → LLM classification → custom enrichment API → priority routing → Slack + Google Sheets.\n\n"
    "Runs every 6 hours on self-hosted n8n (Railway, Docker).\n\n"
    "The three highlighted blocks are the parts that are **not** drag-and-drop."
)

STICKY_CODE = (
    "### 1 · Custom Code node\n"
    "n8n's *Remove Duplicates* compares one field, exactly, inside one execution.\n\n"
    "This node instead:\n"
    "• normalises field drift across 5 feeds\n"
    "• strips tracking params to canonicalise URLs\n"
    "• catches **near**-duplicates via Jaccard similarity on title tokens\n"
    "• remembers what it sent in **previous runs** using workflow static data (72h window)\n\n"
    "Written to run inside the n8n 2.x task runner — no `require()`, hash implemented by hand."
)

STICKY_API = (
    "### 2 · Custom FastAPI service\n"
    "Own service, deployed as a second Railway container, called over HTTP.\n\n"
    "Does what no n8n node can:\n"
    "• alias-aware entity resolution — *the Fed / FOMC / Powell* → one symbol; rejects "
    "\"fed up\" and \"apple harvest\"\n"
    "• SimHash + Jaccard story clustering **persisted in SQLite**, so the same story from a "
    "second outlet six hours later is a known repeat\n"
    "• deterministic 0-100 relevance score with an auditable breakdown\n\n"
    "Auth via header credential — the key never enters this workflow JSON."
)

STICKY_ERR = (
    "### 3 · Error lane\n"
    "The model call and the API call each retry 3× with backoff. Only a *persistent* failure "
    "reaches this branch.\n\n"
    "The handler classifies the failure by stage, checks whether the run still delivered anything "
    "(degraded vs critical), and posts one actionable Slack message — not a raw stack trace.\n\n"
    "Items that fail do not abort the run: the healthy ones still reach the sheet."
)


def node(name, type_, tv, pos, params, **extra):
    n = {"parameters": params, "id": name.lower().replace(" ", "-").replace(":", "").replace("&", "and"),
         "name": name, "type": type_, "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def sticky(name, pos, w, h, color, content):
    return {"parameters": {"content": content, "height": h, "width": w, "color": color},
            "id": name, "name": name, "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1, "position": pos}


nodes = [
    sticky("Note Intro", [-460, -300], 460, 250, 7, STICKY_INTRO),
    sticky("Note Code", [220, -300], 380, 250, 4, STICKY_CODE),
    sticky("Note API", [960, -300], 400, 250, 5, STICKY_API),
    sticky("Note Errors", [1000, 460], 560, 220, 3, STICKY_ERR),

    node("Every 6 Hours", "n8n-nodes-base.scheduleTrigger", 1.2, [-440, 0],
         {"rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}}),

    node("Feed Registry", "n8n-nodes-base.code", 2, [-220, 0],
         {"jsCode": js("js_feed_registry.js")}),

    node("Fetch RSS", "n8n-nodes-base.rssFeedRead", 1.2, [0, 0],
         {"url": "={{ $json.url }}", "options": {}},
         retryOnFail=True, maxTries=2, waitBetweenTries=3000,
         onError="continueRegularOutput",
         notes="One dead feed must not kill the run — errors continue with an empty item."),

    node("Normalize & Deduplicate", "n8n-nodes-base.code", 2, [240, 0],
         {"jsCode": js("js_dedupe.js")}),

    node("Summarize & Classify", "@n8n/n8n-nodes-langchain.openAi", 1.8, [500, 0],
         {"modelId": {"__rl": True, "value": "gpt-4o-mini", "mode": "list",
                      "cachedResultName": "gpt-4o-mini"},
          "messages": {"values": [
              {"content": SYSTEM_PROMPT, "role": "system"},
              {"content": USER_PROMPT}]},
          "jsonOutput": True,
          "options": {"temperature": 0.2, "maxTokens": 400}},
         retryOnFail=True, maxTries=3, waitBetweenTries=5000,
         onError="continueErrorOutput",
         credentials={"openAiApi": {"id": "REPLACE_WITH_YOUR_CREDENTIAL_ID",
                                    "name": "OpenAI account"}},
         notes="3 retries with 5s backoff; persistent failures take the error output."),

    node("Parse LLM Output", "n8n-nodes-base.code", 2, [760, 0],
         {"jsCode": js("js_parse_llm.js")}),

    node("Enrich via Custom API", "n8n-nodes-base.httpRequest", 4.2, [1000, 0],
         {"method": "POST",
          "url": "https://n8n-market-intel-production.up.railway.app/v1/enrich",
          "authentication": "genericCredentialType",
          "genericAuthType": "httpHeaderAuth",
          "sendBody": True,
          "specifyBody": "json",
          "jsonBody": ENRICH_BODY,
          "options": {"timeout": 15000}},
         retryOnFail=True, maxTries=3, waitBetweenTries=4000,
         onError="continueErrorOutput",
         credentials={"httpHeaderAuth": {"id": "REPLACE_WITH_YOUR_CREDENTIAL_ID",
                                         "name": "Enrichment API key"}},
         notes="Header Auth credential holds X-API-Key, so no secret lives in this JSON."),

    node("Assemble Record", "n8n-nodes-base.code", 2, [1260, 0],
         {"jsCode": js("js_assemble.js")}),

    node("Route by Priority", "n8n-nodes-base.if", 2.2, [1500, 0],
         {"conditions": {
             "options": {"caseSensitive": True, "leftValue": "",
                         "typeValidation": "loose", "version": 2},
             # Calibrated against the first live runs, not guessed. Observed
             # score distribution on a quiet news day was 31-67, so the
             # original 70 would almost never fire — an alert that never
             # fires is a broken alert. 60 is the top of the observed band.
             "conditions": [{
                 "id": "relevance-gate",
                 "leftValue": "={{ $json.relevance_score }}",
                 "rightValue": 60,
                 "operator": {"type": "number", "operation": "gte"}}],
             "combinator": "and"},
          "looseTypeValidation": True,
          "options": {}}),

    node("Slack: High-Impact Alert", "n8n-nodes-base.slack", 2.2, [1740, -120],
         {"resource": "message", "operation": "post", "select": "channel",
          "channelId": {"__rl": True, "value": "market-alerts", "mode": "name",
                        "cachedResultName": "market-alerts"},
          "text": ALERT_TEXT,
          "otherOptions": {"includeLinkToWorkflow": False, "mrkdwn": True}},
         onError="continueRegularOutput",
         credentials={"slackApi": {"id": "REPLACE_WITH_YOUR_CREDENTIAL_ID",
                                   "name": "Slack account"}},
         notes="Slack being down must not stop the row reaching the sheet."),

    node("Log to Google Sheets", "n8n-nodes-base.googleSheets", 4.5, [1980, 0],
         {"operation": "append",
          "documentId": {"__rl": True, "value": "1Hxv4g0ORaGia54gN-MSY9DvvmiA4eZYpMpxw3MLtgBQ", "mode": "id"},
          # "name" mode fails with "Sheet with name articles not found" on
          # n8n 2.37 even when the tab is named exactly that; "list" resolves.
          "sheetName": {"__rl": True, "value": "articles", "mode": "list",
                        "cachedResultName": "articles"},
          "columns": {"mappingMode": "autoMapInputData", "value": {},
                      "matchingColumns": [], "schema": []},
          "options": {}},
         retryOnFail=True, maxTries=2, waitBetweenTries=3000,
         credentials={"googleSheetsOAuth2Api": {"id": "REPLACE_WITH_YOUR_CREDENTIAL_ID",
                                                "name": "Google Sheets account"}}),

    node("Handle Failure", "n8n-nodes-base.code", 2, [1080, 240],
         {"jsCode": js("js_error.js")}),

    node("Slack: Pipeline Failure", "n8n-nodes-base.slack", 2.2, [1340, 240],
         {"resource": "message", "operation": "post", "select": "channel",
          "channelId": {"__rl": True, "value": "ops-alerts", "mode": "name",
                        "cachedResultName": "ops-alerts"},
          "text": FAILURE_TEXT,
          "otherOptions": {"includeLinkToWorkflow": True, "mrkdwn": True}},
         credentials={"slackApi": {"id": "REPLACE_WITH_YOUR_CREDENTIAL_ID",
                                   "name": "Slack account"}}),
]


def main(*targets):
    return {"main": [[{"node": t, "type": "main", "index": 0} for t in targets]]}


connections = {
    "Every 6 Hours": main("Feed Registry"),
    "Feed Registry": main("Fetch RSS"),
    "Fetch RSS": main("Normalize & Deduplicate"),
    "Normalize & Deduplicate": main("Summarize & Classify"),
    "Summarize & Classify": {"main": [
        [{"node": "Parse LLM Output", "type": "main", "index": 0}],
        [{"node": "Handle Failure", "type": "main", "index": 0}]]},
    "Parse LLM Output": main("Enrich via Custom API"),
    "Enrich via Custom API": {"main": [
        [{"node": "Assemble Record", "type": "main", "index": 0}],
        [{"node": "Handle Failure", "type": "main", "index": 0}]]},
    "Assemble Record": main("Route by Priority"),
    # Every article is logged; high-priority ones are ALSO alerted. The Slack
    # node must not sit between the router and the sheet: a node's output
    # replaces the item, so chaining Slack -> Sheets writes the Slack API
    # response ({ok, channel, ts}) into the sheet instead of the article.
    # Caught by running it — one garbage row per alert.
    "Route by Priority": {"main": [
        [{"node": "Slack: High-Impact Alert", "type": "main", "index": 0},
         {"node": "Log to Google Sheets", "type": "main", "index": 0}],
        [{"node": "Log to Google Sheets", "type": "main", "index": 0}]]},
    "Handle Failure": main("Slack: Pipeline Failure"),
}

workflow = {
    "name": "Market Intelligence Pipeline",
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "saveExecutionProgress": True,
        "saveDataErrorExecution": "all",
        "saveDataSuccessExecution": "all",
        "executionTimeout": 600,
        "timezone": "Asia/Seoul",
    },
    "pinData": {},
    "tags": [],
    "meta": {"templateCredsSetupCompleted": False},
}

out = B.parent / "workflows" / "market-intel-pipeline.json"
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print("wrote", out, out.stat().st_size, "bytes")
