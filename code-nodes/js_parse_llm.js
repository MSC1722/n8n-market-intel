// ─────────────────────────────────────────────────────────────────────────────
// Parse the model response and re-join it to the article it came from.
//
// Two problems this solves:
//
//  a) The OpenAI node replaces the item — the article fields are gone from the
//     stream. Re-joining by item index is fragile: the moment one item takes
//     the node's error output, every index downstream is off by one. So the
//     model is asked to echo the article `id`, and the join is done on that.
//
//  b) An LLM returns JSON "usually". A pipeline that throws on the one run
//     where it wraps the object in ```json fences is a pipeline that pages you
//     at 3am. Parsing is defensive, and an unparseable response degrades to a
//     low-impact record instead of killing the execution.
// ─────────────────────────────────────────────────────────────────────────────

const CATEGORIES = ['monetary_policy', 'earnings', 'macro_data', 'geopolitics',
                    'commodities', 'crypto', 'corporate_action', 'general'];
const SENTIMENTS = ['positive', 'negative', 'neutral'];

const articles = new Map();
for (const item of $('Normalize & Deduplicate').all()) articles.set(item.json.id, item.json);

function extractContent(json) {
  const candidate = json?.message?.content ?? json?.content ?? json?.text ?? json?.output ?? json;
  if (typeof candidate !== 'string') return candidate;
  const fenced = candidate.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const raw = (fenced ? fenced[1] : candidate).trim();
  try { return JSON.parse(raw); } catch (e) { /* fall through */ }
  const braced = raw.match(/\{[\s\S]*\}/);
  if (braced) { try { return JSON.parse(braced[0]); } catch (e) { /* give up */ } }
  return null;
}

const out = [];
let index = 0;

for (const item of $input.all()) {
  const parsed = extractContent(item.json);
  const article = articles.get(parsed?.id) ?? [...articles.values()][index];
  index++;
  if (!article) continue;

  const impact = Number(parsed?.impact_score);
  out.push({
    json: {
      ...article,
      summary: String(parsed?.summary ?? article.excerpt ?? '').slice(0, 600),
      category: CATEGORIES.includes(parsed?.category) ? parsed.category : 'general',
      sentiment: SENTIMENTS.includes(parsed?.sentiment) ? parsed.sentiment : 'neutral',
      impact_score: Number.isFinite(impact) ? Math.min(Math.max(impact, 0), 10) : 5,
      tickers: Array.isArray(parsed?.tickers)
        ? parsed.tickers.filter((t) => typeof t === 'string').slice(0, 10).map((t) => t.toUpperCase())
        : [],
      llm_parse_ok: parsed !== null,
    },
  });
}

console.log(`llm parse: in=${$input.all().length} out=${out.length} failed=${out.filter((o) => !o.json.llm_parse_ok).length}`);
return out;
