const fs = require('fs');
const src = fs.readFileSync(__dirname + '/../js_dedupe.js', 'utf8');
const now = new Date();
const iso = (h) => new Date(now.getTime() - h * 3600e3).toISOString();

const feedItems = [
  { title: 'Fed holds interest rates steady as inflation cools', link: 'https://www.wsj.com/articles/fed-holds?utm_source=twitter', isoDate: iso(1), contentSnippet: 'The Federal Reserve kept its benchmark rate unchanged.' },
  { title: 'Fed holds interest rates steady as inflation cools', link: 'https://www.wsj.com/articles/fed-holds?utm_source=email&mc_cid=9', pubDate: iso(1) },
  { title: 'Federal Reserve holds interest rates steady as inflation cools further', link: 'https://www.cnbc.com/2026/09/06/fed-rates.html', isoDate: iso(2), description: '<p>Rates unchanged &amp; guidance intact.</p>' },
  { title: 'Nvidia beats earnings expectations on data centre demand', link: 'https://www.marketwatch.com/story/nvidia-earnings', isoDate: iso(3) },
  { title: 'Ancient history of the printing press', link: 'https://finance.yahoo.com/news/old-story', isoDate: iso(40) },
  { title: 'OPEC+ agrees surprise output cut, Brent jumps', link: 'https://www.reuters.com/business/energy/opec-cut/', isoDate: iso(5) },
  { title: 'No link here' },
];

const staticStore = { seen: {} };
function makeRun() {
  const $input = { all: () => feedItems.map((json) => ({ json })) };
  const $getWorkflowStaticData = () => staticStore;
  return new Function('$input', '$getWorkflowStaticData', 'console', src)($input, $getWorkflowStaticData, console);
}

console.log('--- RUN 1 ---');
let out = makeRun();
out.forEach((o) => console.log(' ', o.json.source.padEnd(13), (o.json.age_hours + 'h').padEnd(6), o.json.title.slice(0, 55)));
console.log('  stats:', out[0].json.dedupe_stats);

console.log('--- RUN 2 (same feed content, should be all-seen) ---');
out = makeRun();
console.log('  kept:', out.length, out.length ? out[0].json.dedupe_stats : '');
