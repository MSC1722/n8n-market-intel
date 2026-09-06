// ─────────────────────────────────────────────────────────────────────────────
// Flatten into one row per article, shaped exactly like the Google Sheet.
// The Sheets node uses auto-map, so the field names below ARE the column
// headers — keep them in sync with the sheet, not with the internal payloads.
// Joined on client_ref, which the enrichment API echoes back verbatim.
// ─────────────────────────────────────────────────────────────────────────────

const articles = new Map();
for (const item of $('Parse LLM Output').all()) articles.set(item.json.id, item.json);

const rows = [];

for (const item of $input.all()) {
  const api = item.json;
  const article = articles.get(api.client_ref);
  if (!article) continue;

  const breakdown = api.score_breakdown ?? {};

  rows.push({
    json: {
      timestamp: new Date().toISOString(),
      id: article.id,
      published_at: article.published_at ?? '',
      age_hours: article.age_hours ?? '',
      source: article.source,
      title: article.title,
      summary: article.summary,
      category: article.category,
      sentiment: article.sentiment,
      impact_score: article.impact_score,
      entities: (api.entities ?? []).map((e) => e.symbol).join(', '),
      sectors: (api.sectors ?? []).join(', '),
      relevance_score: api.relevance_score ?? 0,
      priority: api.priority ?? 'low',
      cluster_id: api.cluster_id ?? '',
      is_followup: api.is_followup ? 'yes' : 'no',
      score_reason: api.reason ?? '',
      score_recency: breakdown.recency ?? '',
      score_novelty: breakdown.novelty ?? '',
      url: article.url,
    },
  });
}

rows.sort((a, b) => b.json.relevance_score - a.json.relevance_score);
console.log(`assembled ${rows.length} rows; high=${rows.filter((r) => r.json.priority === 'high').length}`);
return rows;
