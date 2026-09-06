# Code node sources

The four JavaScript Code nodes in `workflows/market-intel-pipeline.json` are
written and tested here, then compiled into the workflow JSON. Editing
JavaScript inside a JSON string is how subtle bugs survive to production.

```
js_feed_registry.js   RSS feed list
js_dedupe.js          Normalisation + cross-run near-duplicate detection
js_parse_llm.js       Defensive model-output parsing and re-join by article id
js_error.js           Failure classification for the error lane
js_assemble.js        Flatten to the Google Sheets row shape
```

## Test the node logic (no n8n required)

```bash
node tests/run_dedupe_test.js    # feeds fake RSS through the dedupe node twice
node tests/run_nodes_test.js     # parse → assemble → error handler, incl. a broken LLM response
```

The harness stubs `$input`, `$()` and `$getWorkflowStaticData`, so the exact code
that runs in n8n is the code under test.

## Rebuild the workflow JSON

```bash
python3 build_workflow.py
```

Regenerates `workflows/market-intel-pipeline.json` from these files plus the node
graph defined in `build_workflow.py`.
