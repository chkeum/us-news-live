"""Reddit crawler for /r/wallstreetbets and /r/stocks.

Uses Reddit's public JSON endpoints (no OAuth needed for read-only).
Docs: https://www.reddit.com/dev/api — respect User-Agent.

Usage:
  python crawl_reddit.py
Outputs: /tmp/news_reddit.json + /tmp/reddit_mentions.json
"""
import json
import re
import hashlib
import time
import requests
from collections import Counter
from datetime import datetime, timezone

UA = "us-news-live/1.0 (by /u/chkeum)"

SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options", "StockMarket"]

TICKERS = set([
    "NVDA", "MRVL", "TSLA", "GOOGL", "MSTR",
    "AMD", "META", "MSFT", "AMZN", "AVGO",
    "AAPL", "NBIS", "ASTS", "RKLB", "COIN",
    "MU", "PLTR", "INTC", "SOFI", "IREN",
    "CURLF", "TLRY", "CGC", "MSOS", "IBM", "NOW",
    "IIPR", "GTBIF", "TCNNF", "SPY", "QQQ", "IWM",
    "BABA", "NIO", "LI", "XPEV", "SMCI", "ARM",
    "NFLX", "DIS", "ORCL", "CRWD", "SNOW", "PANW",
    "HOOD", "SOFI", "PYPL", "SQ", "SHOP",
])

# Cashtag and bare-ticker regex — avoid common words
TICKER_RE = re.compile(r"\$?([A-Z]{2,5})\b")
BLACKLIST_WORDS = {"USA", "THE", "AND", "FOR", "YOU", "BUT", "NOT", "ARE", "CAN", "ALL",
                   "NOW", "LOL", "CEO", "CFO", "COO", "CPU", "GPU", "API", "SEC", "FED",
                   "GDP", "CPI", "IPO", "ETF", "LOL", "IMO", "IMHO", "YTD", "QQ",
                   "AI", "AM", "PM", "ET", "UK", "EU", "US", "RIP", "DD", "YOLO",
                   "PT", "TP", "SL", "TA", "FA", "PS", "PR"}

def fetch_sub(sub, sort="hot", limit=50):
    url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
        return r.json().get("data", {}).get("children", [])
    except Exception as e:
        print(f"[reddit] {sub} fetch failed: {e}")
        return []

def extract_tickers_from_text(text):
    """Find $TICKER or standalone TICKER matches."""
    hits = []
    for m in TICKER_RE.finditer(text):
        t = m.group(1)
        if t in BLACKLIST_WORDS: continue
        if t in TICKERS: hits.append(t)
    return hits

def categorize(title):
    low = title.lower()
    if any(k in low for k in ("dd", "deep dive", "analysis")): return "reddit"
    if any(k in low for k in ("loss porn", "gain porn", "yolo")): return "reddit"
    return "reddit"

def normalize_post(post_wrap):
    d = post_wrap.get("data", {})
    title = (d.get("title") or "").strip()
    if not title: return None, []
    body = (d.get("selftext") or "")[:500]
    ups = d.get("ups") or d.get("score") or 0
    num_comments = d.get("num_comments") or 0
    permalink = "https://www.reddit.com" + (d.get("permalink") or "")
    created_utc = d.get("created_utc")
    published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat() if created_utc else None
    sub = d.get("subreddit") or ""

    tickers = list(dict.fromkeys(
        extract_tickers_from_text(title) + extract_tickers_from_text(body)
    ))
    primary_ticker = tickers[0] if tickers else None

    item_id = "rd_" + hashlib.sha1((permalink or title).encode("utf-8")).hexdigest()[:14]

    # Filter out extremely low-signal posts
    if ups < 50: return None, tickers

    item = {
        "id": item_id,
        "provider": "reddit",
        "ticker": primary_ticker,
        "category": "reddit",
        "title": title,
        "summary": body[:220],
        "url": permalink,
        "source": f"r/{sub}",
        "published_at": published_at,
        "extra_meta": f"⬆ {ups:,} · {num_comments} comments",
    }
    return item, tickers

def main():
    all_items = []
    mention_counter = Counter()
    seen_ids = set()

    for sub in SUBREDDITS:
        for sort in ("hot", "new"):
            posts = fetch_sub(sub, sort=sort, limit=40)
            for p in posts:
                item, tickers = normalize_post(p)
                for t in tickers:
                    mention_counter[t] += 1
                if item and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    all_items.append(item)
            time.sleep(1.2)  # be polite to Reddit

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    all_items = all_items[:80]

    # Mentions (top 20)
    top_mentions = [
        {"ticker": t, "mentions": c, "surge_pct": 0}
        for t, c in mention_counter.most_common(20)
    ]

    out1 = "/tmp/news_reddit.json"
    out2 = "/tmp/reddit_mentions.json"
    with open(out1, "w", encoding="utf-8") as f:
        json.dump({"items": all_items, "fetched_at": datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False, indent=2)
    with open(out2, "w", encoding="utf-8") as f:
        json.dump({"mentions": top_mentions, "fetched_at": datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False, indent=2)

    print(f"[reddit] wrote {len(all_items)} items → {out1}")
    print(f"[reddit] wrote {len(top_mentions)} mentions → {out2}")

if __name__ == "__main__":
    main()
