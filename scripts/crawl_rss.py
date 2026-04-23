"""Yahoo Finance + Benzinga RSS crawler.

Free, unlimited. No API key needed.

Usage:
  python crawl_rss.py
Outputs: /tmp/news_rss.json
"""
import json
import hashlib
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser

SOURCES = [
    # Yahoo Finance
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Yahoo Finance Markets", "url": "https://finance.yahoo.com/rss/topstories"},
    # Benzinga
    {"name": "Benzinga", "url": "https://www.benzinga.com/feed"},
    {"name": "Benzinga Markets", "url": "https://www.benzinga.com/markets/feed"},
    {"name": "Benzinga Analyst", "url": "https://www.benzinga.com/analyst-ratings/feed"},
    # CNBC
    {"name": "CNBC Markets", "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html"},
    # Seeking Alpha top
    {"name": "SeekingAlpha", "url": "https://seekingalpha.com/market_currents.xml"},
]

# Watched tickers (for ticker extraction from title)
TICKERS = [
    "NVDA", "MRVL", "TSLA", "GOOGL", "MSTR",
    "AMD", "META", "MSFT", "AMZN", "AVGO",
    "AAPL", "NBIS", "ASTS", "RKLB", "COIN",
    "MU", "PLTR", "INTC", "SOFI", "IREN",
    "CURLF", "TLRY", "CGC", "MSOS", "IBM", "NOW",
    "IIPR", "GTBIF", "TCNNF",
]

def extract_ticker(title, summary=""):
    """Best-effort ticker extraction from headline."""
    text = f"{title} {summary}".upper()
    for t in TICKERS:
        # Match whole word: " NVDA " or "(NVDA)" or "NVDA's" or "NVDA,"
        if any(p in text for p in (f" {t} ", f"({t})", f"{t}'S", f"{t},", f"{t}:", f"{t}.", f"${t}")):
            return t
    return None

def categorize(title):
    low = title.lower()
    if any(k in low for k in ("breaking", "alert", "urgent")): return "breaking"
    if any(k in low for k in ("earnings", "beats", "misses", "eps", "q1 results", "q2 results", "q3 results", "q4 results", "revenue")): return "earnings"
    if any(k in low for k in ("upgrade", "downgrade", "price target", "raises target", "cuts target", "analyst", "reiterates")): return "analyst"
    if any(k in low for k in ("acquir", "merger", "buyout", "to buy", "deal")): return "ma"
    if any(k in low for k in ("fed", "powell", "cpi", "inflation", "jobs", "fomc", "gdp")): return "macro"
    return "general"

def parse_date(item):
    for key in ("published", "updated", "created"):
        v = item.get(key)
        if v:
            try:
                return dateparser.parse(v).astimezone(timezone.utc).isoformat()
            except Exception:
                continue
    return None

def fetch_source(source):
    try:
        parsed = feedparser.parse(source["url"])
        out = []
        for entry in parsed.entries[:40]:
            title = (entry.get("title") or "").strip()
            if not title: continue
            summary = (entry.get("summary") or "").strip()
            # Strip HTML roughly
            import re
            summary = re.sub(r"<[^>]+>", "", summary)[:280].strip()

            url = entry.get("link") or ""
            raw_id = f"rss:{url or title}"
            item_id = "r_" + hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:14]
            out.append({
                "id": item_id,
                "provider": "rss",
                "ticker": extract_ticker(title, summary),
                "category": categorize(title),
                "title": title,
                "summary": summary,
                "url": url,
                "source": source["name"],
                "published_at": parse_date(entry),
            })
        return out
    except Exception as e:
        print(f"[rss] {source['name']} failed: {e}")
        return []

def main():
    all_items = []
    seen_urls = set()
    for s in SOURCES:
        for n in fetch_source(s):
            if n["url"] in seen_urls: continue
            seen_urls.add(n["url"])
            all_items.append(n)

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    all_items = all_items[:250]

    out_path = "/tmp/news_rss.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": all_items, "fetched_at": datetime.now(timezone.utc).isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[rss] wrote {len(all_items)} items → {out_path}")

if __name__ == "__main__":
    main()
