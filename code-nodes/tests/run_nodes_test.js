const fs = require('fs');
const run = (file, ctx) => new Function('$input', '$', '$workflow', '$execution', fs.readFileSync(__dirname + '/../' + file, 'utf8'))(ctx.$input, ctx.$, ctx.$workflow, ctx.$execution);

const deduped = [
  { id: 'aa11bb22', title: 'Fed holds rates steady', excerpt: 'Fed kept rates.', url: 'https://wsj.com/a', source: 'wsj', source_weight: 0.95, published_at: '2026-09-06T02:00:00Z', age_hours: 2 },
  { id: 'cc33dd44', title: 'Nvidia beats earnings', excerpt: 'Beat.', url: 'https://marketwatch.com/b', source: 'marketwatch', source_weight: 0.75, published_at: '2026-09-06T00:00:00Z', age_hours: 4 },
  { id: 'ee55ff66', title: 'Gold steady', excerpt: 'Flat.', url: 'https://yahoo.com/c', source: 'yahoo_finance', source_weight: 0.65, published_at: '2026-09-05T22:00:00Z', age_hours: 6 },
];

// LLM outputs in three different shapes, one of them broken.
const llmOut = [
  { message: { content: { id: 'aa11bb22', summary: 'Fed left the benchmark rate unchanged.', category: 'monetary_policy', sentiment: 'neutral', impact_score: 8.5, tickers: ['spx'] } } },
  { content: '```json\n{"id":"cc33dd44","summary":"Nvidia beat on data centre revenue.","category":"earnings","sentiment":"positive","impact_score":9,"tickers":["nvda"]}\n```' },
  { message: { content: 'the model rambled instead of returning json' } },
];

const parsed = run('js_parse_llm.js', {
  $input: { all: () => llmOut.map((json) => ({ json })) },
  $: (name) => ({ all: () => deduped.map((json) => ({ json })) }),
});
console.log('--- parse ---');
parsed.forEach((p) => console.log(' ', p.json.id, p.json.category.padEnd(16), 'impact=' + p.json.impact_score, 'ok=' + p.json.llm_parse_ok, '|', p.json.summary.slice(0, 40)));

// API responses (one article failed at the API and took the error branch: only 2 back).
const apiOut = [
  { id: 'x1', client_ref: 'aa11bb22', cluster_id: 'c_1', is_followup: false, cluster_size: 1, entities: [{ symbol: 'FED' }], sectors: ['macro'], relevance_score: 88.4, priority: 'high', score_breakdown: { impact: 0.85, entity: 0.95, recency: 0.84, source: 0.95, novelty: 1 }, reason: 'top contributor: impact (0.85), weakest: source (0.95)' },
  { id: 'x2', client_ref: 'ee55ff66', cluster_id: 'c_3', is_followup: true, cluster_size: 3, entities: [{ symbol: 'GOLD' }], sectors: ['metals'], relevance_score: 31.2, priority: 'low', score_breakdown: { impact: 0.4, entity: 0.7, recency: 0.6, source: 0.65, novelty: 0.58 }, reason: 'x0.58 repeat-story penalty' },
];
const rows = run('js_assemble.js', {
  $input: { all: () => apiOut.map((json) => ({ json })) },
  $: (name) => ({ all: () => parsed }),
});
console.log('--- assemble ---');
rows.forEach((r) => console.log(' ', String(r.json.relevance_score).padEnd(6), r.json.priority.padEnd(7), r.json.entities.padEnd(6), r.json.title));
console.log('  columns:', Object.keys(rows[0].json).join(','));

const errOut = run('js_error.js', {
  $input: { all: () => [
    { json: { error: { message: 'Rate limit reached for gpt-4o-mini', httpCode: 429 }, title: 'Nvidia beats earnings' } },
    { json: { error: { message: 'connect ETIMEDOUT enrich api', status: 504, response: { body: { detail: 'upstream timeout' } } }, url: 'https://x/y' } },
  ] },
  $: (name) => ({ all: () => rows }),
  $workflow: { name: 'Market Intelligence Pipeline' },
  $execution: { id: 'exec_991', resumeUrl: '' },
});
console.log('--- error handler ---');
console.log(JSON.stringify(errOut[0].json, null, 1));

console.log('--- error classifier shapes ---');
const errSrc = fs.readFileSync(__dirname + '/../js_error.js', 'utf8');
const runErr = (items) => new Function('$input', '$', '$workflow', '$execution', 'console', errSrc)(
  { all: () => items.map((json) => ({ json })) },
  () => ({ all: () => [] }),
  { name: 'Market Intelligence Pipeline' },
  { id: 'exec_test' },
  { log: () => {} }
);

const cases = [
  ['input echoed, no error object (seen live 2026-09-06)',
   { id: 'a8e0fd5b', title: 'Budget travellers get thrifty', url: 'https://cnbc.com/x', source: 'cnbc' },
   (o) => o.first_error_shape === 'id, title, url, source'],
  ['classic n8n error object, 429',
   { error: { message: 'Rate limit reached for gpt-4o-mini', httpCode: 429 }, title: 'Nvidia beats' },
   (o) => o.first_error_stage === 'llm' && o.first_error_status === 429],
  ['nested upstream body, 401',
   { error: { status: 401, response: { body: { detail: 'Invalid or missing X-API-Key' } } }, title: 'Fed holds' },
   (o) => o.first_error_stage === 'enrichment_api' && /X-API-Key/.test(o.first_error_message)],
];

for (const [label, item, check] of cases) {
  const out = runErr([item])[0].json;
  console.log(`  ${check(out) ? 'PASS' : 'FAIL'} — ${label}`);
  console.log(`         stage=${out.first_error_stage} status=${out.first_error_status} msg="${out.first_error_message}"`);
}
