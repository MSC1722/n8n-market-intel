# Upwork portfolio entry

**Project title**

```
Market Intelligence Pipeline — self-hosted n8n + custom FastAPI enrichment
```

---

**Description — option A (600 / 600 characters)**

```
Self-hosted n8n (Docker on Railway) turning five financial RSS feeds into a scored, de-duplicated intelligence feed in Slack and Google Sheets.

Not a drag-and-drop build:
- A Code node that canonicalises URLs, catches near-duplicate headlines by token similarity, and remembers what it sent in earlier runs.
- My own FastAPI service, called over HTTP: alias-aware entity resolution, SimHash story clustering persisted in SQLite, deterministic 0-100 scoring.
- An error lane: 3 retries with backoff, then a Slack alert classified by stage.

13 nodes, 20 tests. Workflow JSON and API source on GitHub.
```

---

**Description — option B, slightly more conversational (543 / 600 characters)**

```
Self-hosted n8n on Railway: five financial RSS feeds to a scored, de-duplicated intelligence feed in Slack and Google Sheets.

The parts you can't drag and drop:
- A Code node that catches near-duplicate headlines and remembers what it sent in earlier runs.
- My own FastAPI service, called over HTTP, doing entity resolution, SimHash story clustering in SQLite, and deterministic 0-100 relevance scoring.
- An error lane: retries with backoff, then a Slack alert classified by stage.

13 nodes, 20 tests, JSON and API source public on GitHub.
```

---

**Skills to tag on the portfolio item**

n8n · Workflow Automation · API Integration · FastAPI · Python · JavaScript ·
OpenAI API · Docker · Railway · Google Sheets API · Slack API · RSS

**Cover image**

Use the full workflow canvas screenshot (see `docs/SCREENSHOT_CHECKLIST.md`).
The sticky notes on the canvas do the explaining for you when a client only
looks at the thumbnail.

**If a job post asks for n8n experience specifically**

Lead with the two facts most applicants cannot claim:

1. Self-hosted on Docker, not an n8n Cloud account — volume persistence,
   encryption key management, and the n8n 2.x task-runner changes.
2. The workflow calls a service I wrote and deployed myself for the logic that
   has no node.
