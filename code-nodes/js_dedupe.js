// ─────────────────────────────────────────────────────────────────────────────
// Normalise + de-duplicate
//
// n8n ships a "Remove Duplicates" node. It compares one field, exactly, within
// a single execution. A news pipeline needs four things it cannot do:
//
//   1. Field drift    — every feed names things differently (isoDate / pubDate /
//                       date; contentSnippet / content / description).
//   2. URL noise      — the same article arrives with different utm_* params,
//                       so an exact-match comparison sees two distinct URLs.
//   3. Near-duplicates— two outlets run the same story under different
//                       headlines. Exact matching never catches those.
//   4. Cross-run memory — the run six hours ago already alerted on this story.
//                       A per-execution node has no memory at all.
//
// (1)-(3) are handled below; (4) uses getWorkflowStaticData, which n8n persists
// between executions, with a rolling 72h window so it cannot grow unbounded.
//
// No require() anywhere: n8n 2.x runs Code nodes inside an isolated task runner
// where Node built-ins are not allow-listed by default, so the hash is written
// out by hand (FNV-1a).
// ─────────────────────────────────────────────────────────────────────────────

const MAX_AGE_HOURS    = 24;   // ignore anything older than this
const MAX_ITEMS        = 10;   // cap LLM spend per run
const TITLE_SIMILARITY = 0.55; // Jaccard threshold for "same story"
const MEMORY_HOURS     = 72;   // how long we remember a URL across runs

// Source reputation. The article's own hostname is authoritative — feed URLs
// syndicate, article links do not.
const SOURCES = {
  'wsj.com': ['wsj', 0.95],
  'dowjones.com': ['wsj', 0.95],
  'cnbc.com': ['cnbc', 0.85],
  'reuters.com': ['reuters', 1.0],
  'bloomberg.com': ['bloomberg', 1.0],
  'ft.com': ['ft', 0.95],
  'marketwatch.com': ['marketwatch', 0.75],
  'yahoo.com': ['yahoo_finance', 0.65],
  'investing.com': ['investing_com', 0.6],
  'seekingalpha.com': ['seeking_alpha', 0.55],
};

const STOPWORDS = new Set(('a an the and or but if then than that this these those of in on at ' +
  'to for from by with as is are was were be been being it its his her their our your my we ' +
  'you they he she has have had do does did not no nor so such over under after before about ' +
  'says say said report reports new news update updates amid amp will can could may').split(' '));

// ── helpers ────────────────────────────────────────────────────────────────
function fnv1a(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

function canonicalise(rawUrl) {
  try {
    const u = new URL(rawUrl);
    const keep = new URLSearchParams();
    for (const [k, v] of u.searchParams) {
      const key = k.toLowerCase();
      if (key.startsWith('utm_') || ['fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'ito'].includes(key)) continue;
      keep.append(k, v);
    }
    const host = u.hostname.toLowerCase().replace(/^www\./, '');
    const path = u.pathname.replace(/\/+$/, '') || '/';
    const qs = keep.toString();
    return { url: `https://${host}${path}${qs ? '?' + qs : ''}`, host };
  } catch (e) {
    return { url: String(rawUrl || '').trim(), host: '' };
  }
}

function sourceOf(host) {
  for (const domain of Object.keys(SOURCES)) {
    if (host === domain || host.endsWith('.' + domain)) return SOURCES[domain];
  }
  return ['unknown', 0.5];
}

function tokens(text) {
  return new Set(
    String(text || '')
      .toLowerCase()
      .replace(/[^a-z0-9' ]+/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 2 && !STOPWORDS.has(w))
  );
}

function jaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const t of a) if (b.has(t)) shared++;
  return shared / (a.size + b.size - shared);
}

function pickDate(row) {
  const raw = row.isoDate || row.pubDate || row.published || row.date || row.updated;
  const d = raw ? new Date(raw) : null;
  return d && !isNaN(d.getTime()) ? d : null;
}

function clean(text, limit) {
  return String(text || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&[a-z]+;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit);
}

// ── 1. normalise ───────────────────────────────────────────────────────────
const now = Date.now();
const cutoff = now - MAX_AGE_HOURS * 3600 * 1000;
const normalised = [];

for (const item of $input.all()) {
  const row = item.json;
  const link = row.link || row.guid || row.id;
  if (!link || !row.title) continue;

  const { url, host } = canonicalise(link);
  const [source, weight] = sourceOf(host);
  const published = pickDate(row);
  if (published && published.getTime() < cutoff) continue;

  normalised.push({
    id: fnv1a(url),
    title: clean(row.title, 300),
    excerpt: clean(row.contentSnippet || row.content || row.description || row.summary, 700),
    url,
    host,
    source,
    source_weight: weight,
    published_at: published ? published.toISOString() : null,
    age_hours: published ? Math.round(((now - published.getTime()) / 3600000) * 10) / 10 : null,
    tokens: tokens(row.title),
  });
}

// ── 2. cross-run memory ────────────────────────────────────────────────────
let memory = {};
let memoryAvailable = true;
try {
  const staticData = $getWorkflowStaticData('global');
  staticData.seen = staticData.seen || {};
  const memCutoff = now - MEMORY_HOURS * 3600 * 1000;
  for (const [key, ts] of Object.entries(staticData.seen)) {
    if (ts >= memCutoff) memory[key] = ts;   // prune while we read
  }
  staticData.seen = memory;
} catch (e) {
  memoryAvailable = false;                    // never let dedup memory break a run
}

// ── 3. rank, then de-duplicate ─────────────────────────────────────────────
normalised.sort((a, b) => (b.source_weight - a.source_weight) || ((a.age_hours ?? 99) - (b.age_hours ?? 99)));

const kept = [];
const suppressed = [];   // duplicates we must also remember, see below
const stats = { fetched: $input.all().length, normalised: normalised.length, exact: 0, near: 0, seen_before: 0, capped: 0 };

for (const article of normalised) {
  if (kept.length >= MAX_ITEMS) { stats.capped++; continue; }   // not "seen" — retry next run

  if (kept.some((k) => k.id === article.id)) { stats.exact++; suppressed.push(article.id); continue; }
  if (memoryAvailable && memory[article.id]) { stats.seen_before++; continue; }

  const twin = kept.find((k) => k.source !== article.source && jaccard(k.tokens, article.tokens) >= TITLE_SIMILARITY);
  if (twin) { stats.near++; suppressed.push(article.id); continue; }

  kept.push(article);
}

// Remember the suppressed ones too. Without this, tomorrow's run drops the WSJ
// original as "seen", finds no twin for the CNBC retelling still in the feed,
// and re-alerts on a story that was already sent.
if (memoryAvailable) for (const id of [...kept.map((a) => a.id), ...suppressed]) memory[id] = now;

console.log(`dedupe: fetched=${stats.fetched} kept=${kept.length} exact=${stats.exact} near=${stats.near} seen_before=${stats.seen_before} capped=${stats.capped} memory=${memoryAvailable}`);

// tokens is a Set — strip it before it leaves the node.
return kept.map(({ tokens: _t, ...rest }) => ({ json: { ...rest, dedupe_stats: stats } }));
