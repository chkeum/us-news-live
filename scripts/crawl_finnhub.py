"""Finnhub news crawler.

Finnhub provides per-ticker news via /company-news and general market news via /news.
Free tier: 60 requests/minute. Signup: https://finnhub.io/dashboard

Usage:
  FINNHUB_API_KEY=xxx python crawl_finnhub.py
Outputs: /tmp/news_finnhub.json
"""
import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta

API = "https://finnhub.io/api/v1"
KEY = os.environ.get("FINNHUB_API_KEY", "")

# Tickers tracked by the screener (keep in sync with dashboard watchlist)
TICKERS = [
    "NVDA", "MRVL", "TSLA", "GOOGL", "MSTR",
    "AMD", "META", "MSFT", "AMZN", "AVGO",
    "AAPL", "NBIS", "ASTS", "RKLB", "COIN",
    "MU", "PLTR", "INTC", "SOFI", "IREN",
    "CURLF", "TLRY", "CGC", "MSOS",
]

def fetch_general_market_news():
    """Fetch general market news (last 24 hours)."""
    if not KEY:
        return []
    try:
        r = requests.get(f"{API}/news", params={"category": "general", "token": KEY}, timeout=15)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[finnhub] general news fetch failed: {e}")
        return []

def fetch_company_news(ticker, days=2):
    """Fetch company-specific news from the last N days."""
    if not KEY:
        return []
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=days)
    try:
        r = requests.get(f"{API}/company-news",
                         params={
                             "symbol": ticker,
                             "from": from_date.isoformat(),
                             "to": to_date.isoformat(),
                             "token": KEY,
                         }, timeout=15)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[finnhub] {ticker} news fetch failed: {e}")
        return []

def normalize(item, ticker_hint=None):
    """Convert Finnhub news item to unified feed format."""
    published_at_unix = item.get("datetime") or 0
    published_at = datetime.fromtimestamp(published_at_unix, tz=timezone.utc).isoformat() if published_at_unix else None

    title = item.get("headline") or ""
    summary = item.get("summary") or ""
    url = item.get("url") or ""
    source = item.get("source") or "Finnhub"
    related = item.get("related") or ""

    # Detect ticker
    ticker = ticker_hint
    if not ticker and related:
        parts = [p.strip().upper() for p in related.split(",") if p.strip()]
        for p in parts:
            if p in TICKERS:
                ticker = p
                break
        if not ticker and parts:
            ticker = parts[0]

    # Simple category detection
    category = "general"
    low = title.lower()
    if any(k in low for k in ("earnings", "beats", "misses", "q1 results", "q2 results", "q3 results", "q4 results", "eps")):
        category = "earnings"
    elif any(k in low for k in ("upgrade", "downgrade", "price target", "raises target", "cuts target", "analyst")):
        category = "analyst"
    elif any(k in low for k in ("acquire", "merger", "buyout", "to buy")):
        category = "ma"
    elif any(k in low for k in ("breaking", "alert", "just", "urgent")):
        category = "breaking"

    # Stable unique ID
    raw_id = f"finnhub:{item.get('id') or url or title}"
    item_id = "f_" + hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:14]

    return {
        "id": item_id,
        "provider": "finnhub",
        "ticker": ticker,
        "category": category,
        "title": title,
        "summary": summary,
        "url": url,
        "source": source,
        "published_at": published_at,
    }

def main():
    items = []
    seen_urls = set()

    # General news first
    for raw in fetch_general_market_news():
        n = normalize(raw)
        if n["url"] in seen_urls: continue
        seen_urls.add(n["url"])
        items.append(n)
        time.sleep(0.02)

    # Per-ticker news
    for t in TICKERS:
        for raw in fetch_company_news(t, days=2):
            n = normalize(raw, ticker_hint=t)
            if n["url"] in seen_urls: continue
            seen_urls.add(n["url"])
            items.append(n)
        time.sleep(1.1)  # respect free-tier rate limit (60/min)

    # Sort by published_at desc, cap to 200
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    items = items[:200]

    out_path = "/tmp/news_finnhub.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": items, "fetched_at": datetime.now(timezone.utc).isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[finnhub] wrote {len(items)} items → {out_path}")

if __name__ == "__main__":
    main()
