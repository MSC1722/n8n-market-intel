// ─────────────────────────────────────────────────────────────────────────────
// Feed registry
// Kept in a Code node rather than hard-coded in the RSS node so that the list
// is versioned with the workflow and one dead feed does not require rewiring
// the canvas. The RSS node below runs once per item emitted here.
// ─────────────────────────────────────────────────────────────────────────────
const FEEDS = [
  { url: 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',            desk: 'markets'  },
  { url: 'https://www.cnbc.com/id/20910258/device/rss/rss.html',     desk: 'economy'  },
  { url: 'https://www.cnbc.com/id/100003114/device/rss/rss.html',    desk: 'topnews'  },
  { url: 'https://www.marketwatch.com/rss/topstories',              desk: 'markets'  },
  { url: 'https://finance.yahoo.com/news/rssindex',                 desk: 'markets'  },
];

return FEEDS.map((feed) => ({ json: { ...feed, queued_at: new Date().toISOString() } }));
