"""KR market aggregator — merge KR crawlers → data/news_feed_kr.json + data/market_snapshot_kr.json.

Usage:
  OPENDART_API_KEY=xxx python aggregate_kr.py
Inputs: /tmp/news_kr.json, /tmp/news_dart.json, /tmp/kr_quotes.json
Outputs: ../data/news_feed_kr.json, ../data/market_snapshot_kr.json
"""
import os
import re
import json
from datetime import datetime, timezone

def news_score(item):
    score = 0
    cat = (item.get("category") or "").lower()
    if cat == "breaking": score += 100
    elif cat == "earnings": score += 60
    elif cat == "analyst": score += 40
    elif cat == "ma": score += 35
    elif cat == "macro": score += 25
    if item.get("ticker"): score += 50
    published_at = item.get("published_at")
    if published_at:
        try:
            age_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(published_at.replace("Z", "+00:00"))).total_seconds() / 3600
            score += max(0, 40 - age_hours * 1.5)
        except Exception:
            pass
    return score

SOURCE_FILES = ["/tmp/news_kr.json", "/tmp/news_dart.json"]
QUOTES_FILE = "/tmp/kr_quotes.json"

WATCHLIST_DEFAULT = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "005380",  # 현대차
    "035420",  # NAVER
    "035720",  # 카카오
    "207940",  # 삼성바이오로직스
    "005490",  # 포스코홀딩스
    "051910",  # LG화학
    "247540",  # 에코프로비엠
]

def norm_title(t):
    return re.sub(r"\s+", " ", (t or "").strip())

def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dedupe(items):
    seen = {}
    for it in items:
        key = norm_title(it.get("title"))
        if not key: continue
        if key not in seen:
            seen[key] = it
    return list(seen.values())

def compute_mood(quotes):
    kospi = (quotes.get("kospi") or {}).get("change_pct")
    kosdaq = (quotes.get("kosdaq") or {}).get("change_pct")
    if kospi is None and kosdaq is None:
        return 50, "neutral", "KR 시세 수집 중이에요."
    avg = ((kospi or 0) + (kosdaq or 0)) / 2
    raw = 50 + avg * 14
    score = max(0, min(100, round(raw)))
    if score >= 65: label = "bullish"
    elif score <= 40: label = "bearish"
    else: label = "neutral"
    summary = f"KOSPI {kospi:+.2f}% · KOSDAQ {kosdaq:+.2f}%" if kospi is not None and kosdaq is not None else "지수 체크 중"
    return score, label, summary

def attach_prices(items, quotes):
    watchlist = quotes.get("watchlist") or {}
    for it in items:
        code = it.get("ticker")
        if code and code in watchlist:
            it["change_pct"] = watchlist[code].get("change_pct")

def trending_from_news(items):
    """Count ticker mentions in KR news as a rough trending signal."""
    from collections import Counter
    c = Counter()
    names = {}
    for it in items:
        code = it.get("ticker")
        if code:
            c[code] += 1
            if it.get("ticker_name"):
                names[code] = it["ticker_name"]
        for rel in (it.get("related_tickers") or []):
            c[rel["code"]] += 1
            names[rel["code"]] = rel["name"]
    out = []
    for code, count in c.most_common(10):
        out.append({"ticker": code, "name": names.get(code, code), "mentions": count, "surge_pct": 0})
    return out

def main():
    items = []
    for path in SOURCE_FILES:
        items.extend(load_json(path).get("items", []))
    print(f"[agg-kr] loaded {len(items)} KR items")

    merged = dedupe(items)
    print(f"[agg-kr] after dedupe: {len(merged)}")

    quotes = load_json(QUOTES_FILE)
    attach_prices(merged, quotes)

    merged.sort(
        key=lambda x: (news_score(x), x.get("published_at") or ""),
        reverse=True,
    )
    merged = merged[:200]

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    feed_path = os.path.join(out_dir, "news_feed_kr.json")
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump({
            "items": merged,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_count": len([p for p in SOURCE_FILES if os.path.exists(p)]),
        }, f, ensure_ascii=False, indent=2)
    print(f"[agg-kr] wrote {len(merged)} items → {feed_path}")

    # Market snapshot
    score, mood, summary = compute_mood(quotes)
    wl = quotes.get("watchlist") or {}
    snapshot = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kospi":  quotes.get("kospi"),
        "kosdaq": quotes.get("kosdaq"),
        "kospi200": quotes.get("kospi200"),
        "watchlist": {c: wl[c] for c in WATCHLIST_DEFAULT if c in wl},
        "trending": trending_from_news(merged),
        "mood_score": score,
        "mood": mood,
        "mood_summary": summary,
    }
    snap_path = os.path.join(out_dir, "market_snapshot_kr.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"[agg-kr] wrote KR snapshot → {snap_path}")

if __name__ == "__main__":
    main()
