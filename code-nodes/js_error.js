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

// n8n's error-output items do not have one fixed shape: depending on the node
// and the failure, the useful text sits at json.error.message, json.error, a
// nested response body, or nowhere at all while the item is just the input
// echoed back. The first live run of this pipeline classified ten real
// failures as "unknown" for exactly that reason — the handler was reading a
// shape that n8n does not always produce.
//
// So instead of guessing a path, walk the item and take the first thing that
// looks like a message or a status code, and keep the item's own top-level
// keys so an unfamiliar shape is visible in the alert rather than swallowed.

const MESSAGE_KEYS = ['message', 'description', 'detail', 'reason', 'errorMessage', 'error_description'];
const STATUS_KEYS = ['httpCode', 'statusCode', 'status', 'code'];
// The request target is often the only thing that says WHICH dependency broke:
// a DNS or connection error message names a host, never the workflow stage.
const TARGET_KEYS = ['url', 'uri', 'hostname', 'host', 'endpoint', 'baseURL'];

function harvest(value, depth = 0, found = { message: null, status: null, blobs: [], targets: [] }) {
  if (depth > 4 || value === null || typeof value !== 'object') return found;

  for (const [key, child] of Object.entries(value)) {
    if (!found.message && MESSAGE_KEYS.includes(key) && typeof child === 'string' && child.trim()) {
      found.message = child.trim();
    }
    if (found.status === null && STATUS_KEYS.includes(key) && (typeof child === 'number' || /^\d{3}$/.test(String(child)))) {
      found.status = Number(child);
    }
    if (TARGET_KEYS.includes(key) && typeof child === 'string' && /^https?:\/\//i.test(child)) {
      found.targets.push(child.slice(0, 200));
    }
    if (typeof child === 'string' && child.length > 40 && /error|failed|invalid|denied|timeout/i.test(child)) {
      found.blobs.push(child.slice(0, 200));
    }
    if (child && typeof child === 'object') harvest(child, depth + 1, found);
  }
  return found;
}

function describe(json) {
  const found = harvest(json?.error ?? json);
  const status = found.status;
  const message = found.message ?? found.blobs[0] ?? 'No error message on the item';

  // Match against the message, any error-ish text found, AND the request
  // target. A DNS failure reads "getaddrinfo ENOTFOUND <host>" — it names the
  // host but never the stage, so without the target the first live error-lane
  // test classified ten real failures as "unknown".
  const haystack = `${message} ${found.blobs.join(' ')} ${found.targets.join(' ')}`;
  const NETWORK = /getaddrinfo|enotfound|econnrefused|econnreset|etimedout|ehostunreach|socket hang up|network|timeout/i;

  let stage = 'unknown';
  if (/openai|gpt-|model|completion|rate limit/i.test(haystack)) stage = 'llm';
  else if (/enrich|x-api-key|market-intel/i.test(haystack)) stage = 'enrichment_api';
  else if (NETWORK.test(haystack)) stage = 'network';
  if (status === 401 || status === 403) stage = stage === 'unknown' ? 'auth' : stage;
  if (status === 429) stage = 'rate_limit';

  return {
    stage,
    status,
    message: String(message).slice(0, 400),
    // When the shape is unfamiliar the alert still says what WAS on the item,
    // which is what you actually need at 3am to fix the handler.
    shape: Object.keys(json ?? {}).slice(0, 12).join(', '),
    target: found.targets[0] ?? '',
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
    first_error_article: worst.article,
    first_error_shape: worst.shape,
    first_error_target: worst.target,
    sample: details.slice(0, 5).map((d) => `• [${d.stage}${d.status ? ' ' + d.status : ''}] ${d.article} — ${d.message}`).join('\n'),
    workflow: $workflow.name,
    execution_url: $execution?.resumeUrl ?? '',
    execution_id: $execution?.id ?? '',
    failed_at: new Date().toISOString(),
  },
}];
