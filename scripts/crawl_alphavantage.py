"""Alpha Vantage NEWS_SENTIMENT crawler.

Returns AI-scored sentiment for finance news. Free tier: 25 requests/day.
Signup: https://www.alphavantage.co/support/#api-key

Usage:
  ALPHAVANTAGE_API_KEY=xxx python crawl_alphavantage.py
Outputs: /tmp/news_alphavantage.json
"""
import os
import json
import hashlib
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

API = "https://www.alphavantage.co/query"
KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

# Grab sentiment for high-priority tickers only (free tier is 25/day)
PRIORITY_TICKERS = ["NVDA", "TSLA", "MRVL", "MSTR", "GOOGL"]

def score_to_label(s):
    if s >= 0.35: return "Bullish"
    if s >= 0.15: return "Somewhat-Bullish"
    if s > -0.15: return "Neutral"
    if s > -0.35: return "Somewhat-Bearish"
    return "Bearish"

def fetch_ticker_sentiment(ticker, limit=20):
    if not KEY:
        return []
    try:
        r = requests.get(API, params={
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "limit": limit,
            "sort": "LATEST",
            "apikey": KEY,
        }, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("feed") or []
    except Exception as e:
        print(f"[alphavantage] {ticker} failed: {e}")
        return []

def normalize(item, primary_ticker):
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    url = item.get("url") or ""
    source = item.get("source") or "Alpha Vantage"
    published = item.get("time_published") or ""
    # Format: 20260423T141500
    try:
        dt = datetime.strptime(published, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        published_iso = dt.isoformat()
    except Exception:
        published_iso = None

    # Sentiment overall
    overall = item.get("overall_sentiment_score")
    try: overall = float(overall) if overall is not None else None
    except: overall = None

    # Find ticker-specific sentiment if available
    ticker_sentiments = item.get("ticker_sentiment") or []
    ticker = primary_ticker
    sentiment = overall
    for ts in ticker_sentiments:
        if ts.get("ticker") == primary_ticker:
            try:
                sentiment = float(ts.get("ticker_sentiment_score"))
            except: pass
            break

    topics = item.get("topics") or []
    topic_names = [t.get("topic", "") for t in topics]
    if "Earnings" in topic_names: category = "earnings"
    elif "IPO" in topic_names or "Mergers & Acquisitions" in topic_names: category = "ma"
    elif "Technology" in topic_names: category = "general"
    elif "Financial Markets" in topic_names: category = "macro"
    else: category = "general"

    item_id = "av_" + hashlib.sha1((url or title).encode("utf-8")).hexdigest()[:14]

    return {
        "id": item_id,
        "provider": "alphavantage",
        "ticker": ticker,
        "category": category,
        "title": title,
        "summary": summary[:280],
        "url": url,
        "source": source,
        "published_at": published_iso,
        "sentiment": sentiment,
    }

def main():
    all_items = []
    seen_urls = set()
    for t in PRIORITY_TICKERS:
        feed = fetch_ticker_sentiment(t, limit=20)
        for raw in feed:
            n = normalize(raw, t)
            if n["url"] in seen_urls: continue
            seen_urls.add(n["url"])
            all_items.append(n)

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    all_items = all_items[:120]

    out_path = "/tmp/news_alphavantage.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": all_items, "fetched_at": datetime.now(timezone.utc).isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[alphavantage] wrote {len(all_items)} items → {out_path}")

if __name__ == "__main__":
    main()
