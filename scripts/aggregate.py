"""Aggregator: merge all source feeds → data/news_feed.json + data/market_snapshot.json.

Pipeline:
  1. Load crawler outputs from /tmp/news_*.json
  2. Deduplicate across sources by title similarity
  3. Merge sentiment from Alpha Vantage where available
  4. Attach price/change from market_snapshot (if quote data available)
  5. Sort by published_at desc, cap to 200
  6. Write data/news_feed.json
  7. Compose market_snapshot.json from quote data + reddit mentions + mood

Usage:
  FINNHUB_API_KEY=xxx python aggregate.py
Inputs: /tmp/news_*.json
Outputs: ../data/news_feed.json, ../data/market_snapshot.json
"""
import os
import re
import json
import time
import requests
from datetime import datetime, timezone

API = "https://finnhub.io/api/v1"
KEY = os.environ.get("FINNHUB_API_KEY", "")

SOURCE_FILES = [
    "/tmp/news_finnhub.json",
    "/tmp/news_rss.json",
    "/tmp/news_reddit.json",
    "/tmp/news_alphavantage.json",
]

WATCHLIST_TICKERS = ["NVDA", "MRVL", "TSLA", "MSTR", "GOOGL", "AMD", "META", "MSFT", "AMZN", "AVGO"]
INDEX_SYMBOLS = {
    "sp500": {"symbol": "^GSPC", "label": "S&P 500"},
    "nasdaq": {"symbol": "^IXIC", "label": "Nasdaq"},
    "dow": {"symbol": "^DJI", "label": "Dow"},
    "vix": {"symbol": "^VIX", "label": "VIX"},
    "btc": {"symbol": "BINANCE:BTCUSDT", "label": "BTC"},
}

def normalize_title(t):
    return re.sub(r"\s+", " ", (t or "").lower().strip())

def load_feed(path):
    if not os.path.exists(path):
        print(f"[agg] missing {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])

def dedupe(items):
    """Deduplicate by normalized title, prefer item with more metadata."""
    seen = {}
    def score(i):
        s = 0
        if i.get("sentiment") is not None: s += 5
        if i.get("ticker"): s += 3
        if i.get("summary"): s += 2
        if i.get("url"): s += 1
        return s
    for it in items:
        key = normalize_title(it.get("title"))
        if not key: continue
        if key in seen:
            if score(it) > score(seen[key]):
                seen[key] = it
        else:
            seen[key] = it
    return list(seen.values())

def fetch_quote(symbol):
    if not KEY: return None
    try:
        r = requests.get(f"{API}/quote", params={"symbol": symbol, "token": KEY}, timeout=10)
        r.raise_for_status()
        q = r.json()
        price = q.get("c")
        prev = q.get("pc")
        if price is None or not prev: return None
        change_pct = (price - prev) / prev * 100 if prev else 0
        return {"price": round(price, 2), "change_pct": round(change_pct, 2)}
    except Exception as e:
        print(f"[agg] quote {symbol} failed: {e}")
        return None

def attach_prices(items, quotes_by_ticker):
    for it in items:
        t = it.get("ticker")
        if t and t in quotes_by_ticker:
            q = quotes_by_ticker[t]
            it["change_pct"] = q["change_pct"]

def compute_mood(quotes_by_ticker):
    """Blend S&P, Nasdaq, VIX to produce 0-100 mood score."""
    sp = quotes_by_ticker.get("sp500", {}).get("change_pct")
    ndx = quotes_by_ticker.get("nasdaq", {}).get("change_pct")
    vix = quotes_by_ticker.get("vix", {}).get("change_pct")
    if sp is None and ndx is None:
        return 50, "neutral", "장 데이터 수집 중이에요."
    avg = ((sp or 0) + (ndx or 0)) / 2
    vix_pen = max(-10, min(10, (vix or 0) / 2))  # VIX up = fear
    raw = 50 + avg * 12 - vix_pen
    score = max(0, min(100, round(raw)))
    if score >= 65: label = "bullish"
    elif score <= 40: label = "bearish"
    else: label = "neutral"
    summary = f"S&P {sp:+.2f}% · Nasdaq {ndx:+.2f}%" if sp is not None and ndx is not None else "마켓 체크 중"
    return score, label, summary

def load_mentions():
    path = "/tmp/reddit_mentions.json"
    if not os.path.exists(path): return []
    with open(path) as f:
        return json.load(f).get("mentions", [])

def main():
    # Collect items
    all_items = []
    for path in SOURCE_FILES:
        all_items.extend(load_feed(path))
    print(f"[agg] loaded {len(all_items)} items from {len(SOURCE_FILES)} sources")

    # Dedupe
    merged = dedupe(all_items)
    print(f"[agg] after dedupe: {len(merged)}")

    # Fetch quotes for watchlist + indices
    quotes = {}
    if KEY:
        for t in WATCHLIST_TICKERS:
            q = fetch_quote(t)
            if q: quotes[t] = q
            time.sleep(1.1)
        for key, info in INDEX_SYMBOLS.items():
            q = fetch_quote(info["symbol"])
            if q:
                quotes[key] = q
                quotes[key]["label"] = info["label"]
            time.sleep(1.1)
    else:
        print("[agg] no FINNHUB_API_KEY — skipping quote enrichment")

    # Attach prices to news items
    attach_prices(merged, quotes)

    # Sort, cap
    merged.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    merged = merged[:200]

    # Ensure output dir
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    # Write news_feed.json
    feed_path = os.path.join(out_dir, "news_feed.json")
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump({
            "items": merged,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_count": len([p for p in SOURCE_FILES if os.path.exists(p)]),
        }, f, ensure_ascii=False, indent=2)
    print(f"[agg] wrote {len(merged)} items → {feed_path}")

    # Build market_snapshot.json
    score, mood, summary = compute_mood(quotes)
    mentions = load_mentions()
    # Surge calculation would need a prior day's snapshot; placeholder 0 for now
    snapshot = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sp500": quotes.get("sp500"),
        "nasdaq": quotes.get("nasdaq"),
        "dow": quotes.get("dow"),
        "vix": quotes.get("vix"),
        "btc": quotes.get("btc"),
        "watchlist": {t: quotes[t] for t in WATCHLIST_TICKERS if t in quotes},
        "trending": mentions[:10],
        "mood_score": score,
        "mood": mood,
        "mood_summary": summary,
    }
    snap_path = os.path.join(out_dir, "market_snapshot.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"[agg] wrote market snapshot → {snap_path}")

if __name__ == "__main__":
    main()
