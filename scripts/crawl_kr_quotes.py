"""KR stock/index quotes — Naver Finance scraping.

Uses Naver Finance's public data endpoints. No API key required.
(Respect ToS — this is light reads, not a commercial scraper.)

Usage:
  python crawl_kr_quotes.py
Outputs: /tmp/kr_quotes.json
"""
import json
import re
import requests
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; us-news-live/1.0)"

# KR indices (pegged to Naver's sise code format)
INDICES = {
    "kospi":  {"code": "KOSPI",  "label": "KOSPI"},
    "kosdaq": {"code": "KOSDAQ", "label": "KOSDAQ"},
    "kospi200": {"code": "KPI200", "label": "KOSPI200"},
}

# Watchlist tickers
WATCHLIST = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "373220": "LG에너지솔루션",
    "005380": "현대차",
    "035420": "NAVER",
    "035720": "카카오",
    "207940": "삼성바이오로직스",
    "005490": "포스코홀딩스",
    "051910": "LG화학",
    "247540": "에코프로비엠",
}

def fetch_index(code):
    """Fetch index price via Naver Finance JSON API.

    Naver returns `nv` as integer × 100 (i.e., 297842 = 2978.42).
    """
    try:
        url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:{code}"
        r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://finance.naver.com/"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        area = data.get("result", {}).get("areas", [{}])
        if not area: return None
        dt = area[0].get("datas", [{}])
        if not dt: return None
        d0 = dt[0]
        now_val = d0.get("nv")
        change_pct = d0.get("cr")
        # Naver returns index values × 100 (e.g., 297842 → 2978.42)
        price = now_val / 100.0 if isinstance(now_val, (int, float)) else None
        return {
            "price": round(price, 2) if price is not None else None,
            "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
            "label": code,
        }
    except Exception as e:
        print(f"[kr-quote] index {code} failed: {e}")
        return None

def fetch_stock(code):
    """Fetch stock price from Naver mobile JSON."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        data = r.json()
        close = data.get("closePrice")
        change_rate = data.get("fluctuationsRatio")
        if close is None: return None
        # closePrice is string like "82,400"
        try: close_val = float(str(close).replace(",", ""))
        except: close_val = None
        try: rate_val = float(change_rate)
        except: rate_val = None
        return {
            "price": close_val,
            "change_pct": rate_val,
        }
    except Exception as e:
        print(f"[kr-quote] {code} failed: {e}")
        return None

def main():
    out = {"fetched_at": datetime.now(timezone.utc).isoformat()}

    # Indices
    for key, info in INDICES.items():
        q = fetch_index(info["code"])
        if q: out[key] = q

    # Watchlist
    watchlist = {}
    for code, name in WATCHLIST.items():
        q = fetch_stock(code)
        if q:
            q["name"] = name
            q["code"] = code
            watchlist[code] = q
    out["watchlist"] = watchlist

    out_path = "/tmp/kr_quotes.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[kr-quote] wrote indices {list(INDICES.keys())} + {len(watchlist)} stocks → {out_path}")

if __name__ == "__main__":
    main()
