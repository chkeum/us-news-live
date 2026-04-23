"""Cross-Market predictor — overnight US moves → predicted KR gap at open.

Strategy:
  1. Hardcoded pairing rules (US ticker → KR stocks with historical beta)
  2. For each pair, predicted_kr_pct = us_pct × beta (simple linear model)
  3. Sector-level coupling (US sector avg → KR sector avg)
  4. Macro band (USD/KRW, DXY, US10Y proxy via Finnhub)

Inputs:
  - ../data/market_snapshot.json      (US snapshot)
  - ../data/market_snapshot_kr.json   (KR snapshot)
  - ../data/news_feed.json            (for overnight digest)

Output:
  - ../data/cross_market.json

Usage:
  python crossmarket.py
"""
import os
import json
from datetime import datetime, timezone

# ---------- Pairing rules (domain knowledge) ----------
# beta ≈ typical 24-session correlation coefficient × relative volatility ratio
# These are starting values — in production, recompute from rolling history.
PAIRS = {
    "NVDA": [
        {"code": "000660", "name": "SK하이닉스",   "beta": 0.72, "reason": "HBM3E/HBM4 공급 메인 파트너"},
        {"code": "042700", "name": "한미반도체",   "beta": 0.85, "reason": "HBM TC본더 장비 독점 공급"},
        {"code": "005930", "name": "삼성전자",     "beta": 0.52, "reason": "HBM 공급사, AI 반도체 연동"},
        {"code": "007660", "name": "이수페타시스", "beta": 0.78, "reason": "AI GPU용 MLB PCB 공급"},
    ],
    "TSLA": [
        {"code": "373220", "name": "LG에너지솔루션", "beta": 0.68, "reason": "Tesla 4680 셀 공급"},
        {"code": "247540", "name": "에코프로비엠",   "beta": 0.62, "reason": "NCA 양극재 공급"},
        {"code": "003670", "name": "포스코퓨처엠",   "beta": 0.54, "reason": "양극재·음극재 공급망"},
        {"code": "066970", "name": "엘앤에프",       "beta": 0.58, "reason": "Tesla 양극재 직납"},
        {"code": "006400", "name": "삼성SDI",        "beta": 0.48, "reason": "원통형 배터리 경쟁사"},
    ],
    "MRVL": [
        {"code": "000660", "name": "SK하이닉스",  "beta": 0.45, "reason": "커스텀 실리콘 테마 연동"},
        {"code": "042700", "name": "한미반도체",  "beta": 0.62, "reason": "MPU/TPU 제조 파생 수혜"},
        {"code": "007660", "name": "이수페타시스","beta": 0.58, "reason": "AI 서버 MLB 수요 확대"},
    ],
    "GOOGL": [
        {"code": "035420", "name": "NAVER",       "beta": 0.42, "reason": "Gemini 대비 독립 AI 엔진 HyperCLOVA X"},
        {"code": "035720", "name": "카카오",      "beta": 0.35, "reason": "국내 AI 플랫폼 경쟁"},
        {"code": "042700", "name": "한미반도체",  "beta": 0.48, "reason": "TPU 제조 파생"},
    ],
    "META": [
        {"code": "035420", "name": "NAVER",       "beta": 0.38, "reason": "AI 인프라 투자 확대 테마"},
        {"code": "352820", "name": "하이브",      "beta": 0.28, "reason": "메타버스·콘텐츠 노출 테마"},
    ],
    "MSFT": [
        {"code": "035420", "name": "NAVER",       "beta": 0.35, "reason": "클라우드·AI 엔터프라이즈"},
        {"code": "035720", "name": "카카오",      "beta": 0.32, "reason": "클라우드 Azure 파트너십"},
    ],
    "AMZN": [
        {"code": "035420", "name": "NAVER",       "beta": 0.30, "reason": "커머스·클라우드 동행"},
        {"code": "005930", "name": "삼성전자",    "beta": 0.28, "reason": "AWS Trainium3 → HBM 수요"},
    ],
    "AMD": [
        {"code": "000660", "name": "SK하이닉스",  "beta": 0.58, "reason": "MI355X용 HBM 공급"},
        {"code": "042700", "name": "한미반도체",  "beta": 0.68, "reason": "AMD 서버용 HBM 장비"},
    ],
    "AVGO": [
        {"code": "042700", "name": "한미반도체",  "beta": 0.55, "reason": "커스텀 ASIC 장비 테마"},
        {"code": "000660", "name": "SK하이닉스",  "beta": 0.42, "reason": "네트워킹 반도체 HBM 연동"},
    ],
    "MU": [
        {"code": "000660", "name": "SK하이닉스",  "beta": 0.85, "reason": "메모리 직접 경쟁사"},
        {"code": "005930", "name": "삼성전자",    "beta": 0.72, "reason": "DDR·HBM 동행"},
    ],
    "MSTR": [
        {"code": "293490", "name": "카카오게임즈",  "beta": 0.22, "reason": "BTC 테마 파생 (약한)"},
        {"code": "112040", "name": "위메이드",      "beta": 0.35, "reason": "크립토·WEMIX 노출"},
    ],
    "COIN": [
        {"code": "112040", "name": "위메이드",      "beta": 0.38, "reason": "크립토 거래 파생"},
        {"code": "293490", "name": "카카오게임즈",  "beta": 0.18, "reason": "블록체인 게임 테마"},
    ],
    "AAPL": [
        {"code": "005930", "name": "삼성전자",    "beta": -0.12, "reason": "역상관 (iPhone vs Galaxy)"},
        {"code": "000660", "name": "SK하이닉스",  "beta":  0.22, "reason": "iPhone 메모리 공급"},
    ],
    "INTC": [
        {"code": "000660", "name": "SK하이닉스",  "beta": 0.38, "reason": "DDR5 동행"},
    ],
    "PLTR": [
        {"code": "012450", "name": "한화에어로스페이스", "beta": 0.32, "reason": "방산 AI 솔루션 테마"},
        {"code": "079550", "name": "LIG넥스원",          "beta": 0.28, "reason": "국내 방산 AI 연동"},
    ],
    "ASTS": [
        {"code": "272210", "name": "한화시스템", "beta": 0.45, "reason": "위성통신 사업 연동"},
        {"code": "012450", "name": "한화에어로스페이스", "beta": 0.35, "reason": "우주 발사체 사업"},
    ],
    "RKLB": [
        {"code": "272210", "name": "한화시스템", "beta": 0.38, "reason": "위성 발사·통신 테마"},
        {"code": "012450", "name": "한화에어로스페이스", "beta": 0.42, "reason": "우주 발사 사업"},
    ],
}

# ---------- Sector coupling ----------
# US sector move → KR sector move (expected beta)
SECTOR_COUPLING = [
    {
        "us_sector": "Semiconductors",
        "us_tickers": ["NVDA", "AMD", "MRVL", "AVGO", "MU", "INTC"],
        "kr_sector": "반도체",
        "kr_tickers": ["005930", "000660", "042700", "007660"],
        "beta": 0.65,
        "lag_hours": 8,
    },
    {
        "us_sector": "EV / Battery",
        "us_tickers": ["TSLA"],
        "kr_sector": "2차전지",
        "kr_tickers": ["373220", "247540", "003670", "066970", "006400"],
        "beta": 0.58,
        "lag_hours": 8,
    },
    {
        "us_sector": "Mega-Cap Tech",
        "us_tickers": ["GOOGL", "META", "MSFT", "AMZN"],
        "kr_sector": "플랫폼 / 클라우드",
        "kr_tickers": ["035420", "035720"],
        "beta": 0.38,
        "lag_hours": 8,
    },
    {
        "us_sector": "Crypto / Bitcoin",
        "us_tickers": ["MSTR", "COIN"],
        "kr_sector": "크립토·게이밍",
        "kr_tickers": ["112040", "293490"],
        "beta": 0.32,
        "lag_hours": 4,
    },
    {
        "us_sector": "Space / Defense",
        "us_tickers": ["ASTS", "RKLB", "PLTR"],
        "kr_sector": "방산·우주",
        "kr_tickers": ["012450", "272210", "079550"],
        "beta": 0.35,
        "lag_hours": 8,
    },
]

# ---------- Helpers ----------
def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def avg_change_pct(tickers, snapshot):
    """Average change% of given tickers from snapshot['watchlist'][ticker].change_pct."""
    vals = []
    wl = snapshot.get("watchlist") or {}
    for t in tickers:
        d = wl.get(t)
        if d and d.get("change_pct") is not None:
            vals.append(float(d["change_pct"]))
    if not vals: return None
    return sum(vals) / len(vals)

def fmt_delta(x):
    if x is None: return None
    return round(x, 2)

def build_predictions(us_snap, kr_snap):
    """For each pair, compute predicted KR move based on US anchor move."""
    predictions = []
    us_wl = us_snap.get("watchlist") or {}
    kr_wl = kr_snap.get("watchlist") or {}

    for us_ticker, pairs in PAIRS.items():
        us_data = us_wl.get(us_ticker)
        if not us_data: continue
        us_change = us_data.get("change_pct")
        if us_change is None: continue

        for p in pairs:
            kr_code = p["code"]
            kr_data = kr_wl.get(kr_code)
            predicted = us_change * p["beta"]
            actual = kr_data.get("change_pct") if kr_data else None
            predictions.append({
                "us_ticker": us_ticker,
                "us_change_pct": round(us_change, 2),
                "kr_code": kr_code,
                "kr_name": p["name"],
                "beta": p["beta"],
                "predicted_kr_pct": round(predicted, 2),
                "actual_kr_pct": fmt_delta(actual),
                "reason": p["reason"],
                "us_price": us_data.get("price"),
                "kr_price": kr_data.get("price") if kr_data else None,
            })

    # Sort by absolute predicted move (most impactful first)
    predictions.sort(key=lambda x: abs(x["predicted_kr_pct"]), reverse=True)
    return predictions

def build_sector_coupling(us_snap, kr_snap):
    """For each sector pair, compute US avg → predicted KR avg."""
    out = []
    for s in SECTOR_COUPLING:
        us_avg = avg_change_pct(s["us_tickers"], us_snap)
        kr_avg = avg_change_pct(s["kr_tickers"], kr_snap)
        if us_avg is None: continue
        predicted_kr = us_avg * s["beta"]
        out.append({
            "us_sector": s["us_sector"],
            "us_tickers": s["us_tickers"],
            "us_avg_pct": round(us_avg, 2),
            "kr_sector": s["kr_sector"],
            "kr_tickers": s["kr_tickers"],
            "kr_actual_avg_pct": fmt_delta(kr_avg),
            "beta": s["beta"],
            "predicted_kr_avg_pct": round(predicted_kr, 2),
            "lag_hours": s["lag_hours"],
        })
    return out

def build_overnight_digest(us_snap, us_feed_items, top_n=3):
    """Pick 3 highest-impact US news items from the past 8 hours (overnight digest)."""
    from dateutil import parser as dateparser
    digest = []
    seen_tickers = set()
    for item in us_feed_items:
        published = item.get("published_at")
        if not published: continue
        try:
            dt = dateparser.parse(published)
            hours_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if hours_ago > 24: continue
        except Exception:
            continue
        ticker = item.get("ticker")
        if not ticker: continue
        if ticker in seen_tickers: continue
        # Prefer items with tickers in our PAIRS
        if ticker not in PAIRS: continue
        # Skip irrelevant categories
        if item.get("category") in ("reddit",): continue
        digest.append({
            "ticker": ticker,
            "title": item.get("title"),
            "title_kr": item.get("title_kr"),
            "source": item.get("source"),
            "published_at": published,
            "category": item.get("category"),
            "kr_pairs": [p["name"] for p in PAIRS.get(ticker, [])[:2]],
        })
        seen_tickers.add(ticker)
        if len(digest) >= top_n: break
    return digest

def build_macro_band(us_snap):
    """Extract key macro indicators shown in cross-market."""
    return {
        "sp500":  us_snap.get("sp500"),
        "nasdaq": us_snap.get("nasdaq"),
        "vix":    us_snap.get("vix"),
        "btc":    us_snap.get("btc"),
    }

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "..", "data")

    us_snap = load_json(os.path.join(data_dir, "market_snapshot.json"))
    kr_snap = load_json(os.path.join(data_dir, "market_snapshot_kr.json"))
    us_feed = load_json(os.path.join(data_dir, "news_feed.json"))
    us_feed_items = us_feed.get("items", []) if us_feed else []

    if not us_snap:
        print("[crossmarket] missing US snapshot, skipping")
        return

    predictions = build_predictions(us_snap, kr_snap) if kr_snap else []
    sectors = build_sector_coupling(us_snap, kr_snap) if kr_snap else []
    digest = build_overnight_digest(us_snap, us_feed_items)
    macro = build_macro_band(us_snap)

    # Compute market mood for cross view: avg of US bullish indicators
    us_mood = us_snap.get("mood_score", 50)
    kr_mood = kr_snap.get("mood_score", 50) if kr_snap else 50

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "us_mood_score": us_mood,
        "kr_mood_score": kr_mood,
        "us_mood": us_snap.get("mood"),
        "kr_mood": kr_snap.get("mood") if kr_snap else None,
        "predictions": predictions[:20],     # top 20 most impactful pairs
        "sector_coupling": sectors,
        "overnight_digest": digest,
        "macro": macro,
        "summary": build_summary(predictions, us_mood, kr_mood),
    }

    out_path = os.path.join(data_dir, "cross_market.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[crossmarket] wrote {len(predictions)} predictions, {len(sectors)} sectors → {out_path}")

def build_summary(predictions, us_mood, kr_mood):
    """Generate 1-line Korean summary."""
    if not predictions:
        return "교차 분석 데이터 수집 중이에요."
    top = predictions[0]
    direction = "상방" if top["predicted_kr_pct"] > 0 else "하방"
    sign = "+" if top["predicted_kr_pct"] > 0 else ""
    return (
        f"미국 {top['us_ticker']} {top['us_change_pct']:+.1f}% → "
        f"{top['kr_name']} 개장 {direction} 압력 예상 ({sign}{top['predicted_kr_pct']:.1f}% 전후). "
        f"US 무드 {us_mood}/100, KR 무드 {kr_mood}/100."
    )

if __name__ == "__main__":
    main()
