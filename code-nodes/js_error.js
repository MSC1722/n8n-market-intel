// ─────────────────────────────────────────────────────────────────────────────
// Error lane.
//
// Both the model call and the enrichment API call route their error output
// here. Each has already exhausted its retries (3 attempts, backoff) before an
// item reaches this node, so anything arriving is a real, persistent failure
// worth waking someone for — not a transient blip.
//
// The job here is to turn n8n's raw error object into something a human can
// act on from a phone: which stage, which article, what the upstream actually
// said, and whether the run produced anything at all.
// ─────────────────────────────────────────────────────────────────────────────

const failures = $input.all();
if (failures.length === 0) return [];

function describe(json) {
  const err = json?.error ?? json;
  const status = err?.httpCode ?? err?.status ?? err?.statusCode ?? json?.statusCode ?? null;
  const message = err?.message ?? err?.description ?? err?.detail ?? 'Unknown error';
  const upstream = err?.response?.body ?? err?.body ?? null;

  let stage = 'unknown';
  if (typeof message === 'string') {
    if (/openai|model|token|rate limit/i.test(message)) stage = 'llm';
    else if (/enrich|econnrefused|etimedout|fetch|socket|502|503|504/i.test(message)) stage = 'enrichment_api';
  }
  if (status === 401 || status === 403) stage = stage === 'unknown' ? 'auth' : stage;

  return {
    stage,
    status,
    message: String(message).slice(0, 400),
    upstream: upstream ? String(typeof upstream === 'string' ? upstream : JSON.stringify(upstream)).slice(0, 300) : '',
    article: json?.title ?? json?.url ?? json?.id ?? '(no article context)',
  };
}

const details = failures.map((f) => describe(f.json));
const byStage = details.reduce((acc, d) => ({ ...acc, [d.stage]: (acc[d.stage] ?? 0) + 1 }), {});

// Was anything salvaged, or did the whole run fail? Changes how urgent this is.
let delivered = 0;
try { delivered = $('Assemble Record').all().length; } catch (e) { delivered = 0; }

const worst = details[0];
const summary = Object.entries(byStage).map(([k, v]) => `${k}×${v}`).join(', ');

console.log(`pipeline failures: ${failures.length} (${summary}); delivered=${delivered}`);

return [{
  json: {
    failed_count: failures.length,
    delivered_count: delivered,
    severity: delivered === 0 ? 'critical' : 'degraded',
    stages: summary,
    first_error_stage: worst.stage,
    first_error_status: worst.status ?? 'n/a',
    first_error_message: worst.message,
    first_error_upstream: worst.upstream,
    first_error_article: worst.article,
    sample: details.slice(0, 5).map((d) => `• [${d.stage}${d.status ? ' ' + d.status : ''}] ${d.article} — ${d.message}`).join('\n'),
    workflow: $workflow.name,
    execution_url: $execution?.resumeUrl ?? '',
    execution_id: $execution?.id ?? '',
    failed_at: new Date().toISOString(),
  },
}];
