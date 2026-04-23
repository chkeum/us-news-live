"""Korean financial news crawler — RSS-based.

Sources covered:
  - 한경 (Hankyung) / 한국경제
  - 매일경제 (Maeil Business)
  - 조선비즈 (ChosunBiz)
  - 이데일리
  - 연합뉴스 경제
  - 네이버 뉴스 경제 섹션 (via Google News RSS)

All sources are free and don't require API keys.

Usage:
  python crawl_kr_news.py
Outputs: /tmp/news_kr.json
"""
import json
import re
import hashlib
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser

# ---------- Sources ----------
SOURCES = [
    # 한경 — 증권 섹션
    {"name": "한경 증권",     "url": "https://www.hankyung.com/feed/finance"},
    {"name": "한경 산업",     "url": "https://www.hankyung.com/feed/industry"},
    {"name": "한경 경제",     "url": "https://www.hankyung.com/feed/economy"},
    # 매일경제
    {"name": "매경 증권",     "url": "https://www.mk.co.kr/rss/50200011/"},
    {"name": "매경 경제",     "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "매경 산업",     "url": "https://www.mk.co.kr/rss/50100032/"},
    # 이데일리
    {"name": "이데일리 증권", "url": "https://rss.edaily.co.kr/stock_news.xml"},
    {"name": "이데일리 경제", "url": "https://rss.edaily.co.kr/economic_news.xml"},
    # 조선비즈
    {"name": "조선비즈 증권", "url": "https://biz.chosun.com/arc/outboundfeeds/rss/category/stock/"},
    {"name": "조선비즈 산업", "url": "https://biz.chosun.com/arc/outboundfeeds/rss/category/industry/"},
    # 연합뉴스 경제
    {"name": "연합뉴스 경제", "url": "https://www.yna.co.kr/rss/economy.xml"},
    # Google News — 한국 증시 토픽 (ultimate fallback)
    {"name": "Google News KR", "url": "https://news.google.com/rss/search?q=%EC%BD%94%EC%8A%A4%ED%94%BC+OR+%EC%BD%94%EC%8A%A4%EB%8B%A5+OR+%ED%95%9C%EA%B5%AD%EC%A6%9D%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"},
]

# ---------- Tracked Korean tickers & company names ----------
# Maps company name → ticker (KRX 종목코드)
KR_TICKERS = {
    # 반도체
    "삼성전자": "005930", "SK하이닉스": "000660", "하이닉스": "000660",
    "한미반도체": "042700", "이수페타시스": "007660",
    # 2차전지 / EV
    "LG에너지솔루션": "373220", "에너지솔루션": "373220",
    "삼성SDI": "006400", "SK이노베이션": "096770",
    "포스코퓨처엠": "003670", "에코프로비엠": "247540", "에코프로": "086520",
    "엘앤에프": "066970",
    # 바이오
    "삼성바이오로직스": "207940", "바이오로직스": "207940",
    "셀트리온": "068270", "유한양행": "000100",
    "한미약품": "128940", "대웅제약": "069620",
    # 자동차
    "현대차": "005380", "현대자동차": "005380",
    "기아": "000270", "현대모비스": "012330",
    # 금융
    "KB금융": "105560", "신한지주": "055550", "하나금융지주": "086790",
    "삼성생명": "032830", "카카오뱅크": "323410",
    # 플랫폼 / IT
    "네이버": "035420", "NAVER": "035420",
    "카카오": "035720", "카카오페이": "377300",
    "크래프톤": "259960", "엔씨소프트": "036570", "넷마블": "251270",
    # 통신
    "SK텔레콤": "017670", "KT": "030200", "LG유플러스": "032640",
    # 조선 / 방산
    "한화오션": "042660", "HD현대중공업": "329180", "한화에어로스페이스": "012450",
    "LIG넥스원": "079550", "한화시스템": "272210",
    # 엔터 / K-POP
    "하이브": "352820", "HYBE": "352820",
    "SM": "041510", "JYP": "035900", "YG": "122870",
    # AI / 콘텐츠 파생
    "위메이드": "112040", "펄어비스": "263750",
    # 태양광 / 원전
    "한화솔루션": "009830", "두산에너빌리티": "034020", "두산": "000150",
    # 기타 주요
    "셀트리온제약": "068760", "아모레퍼시픽": "090430",
    "LG화학": "051910", "포스코홀딩스": "005490",
}

def extract_tickers(text):
    hits = []
    for name, code in KR_TICKERS.items():
        if name in text:
            hits.append((name, code))
    # Also match Naver finance URL pattern ?code=NNNNNN
    for m in re.finditer(r"code=([0-9]{6})", text):
        code = m.group(1)
        if code not in [c for _, c in hits]:
            hits.append((code, code))
    # Dedupe by code
    seen = set(); uniq = []
    for nm, cd in hits:
        if cd in seen: continue
        seen.add(cd); uniq.append((nm, cd))
    return uniq

def categorize(title):
    t = title
    if re.search(r"(속보|긴급|단독)", t): return "breaking"
    if re.search(r"(실적|영업이익|매출|분기|어닝|컨콜|컨센)", t): return "earnings"
    if re.search(r"(목표가|매수|매도|보고서|추천|투자의견|리서치|애널리스트)", t): return "analyst"
    if re.search(r"(인수|합병|M&A|지분|IPO|상장)", t): return "ma"
    if re.search(r"(한은|기준금리|CPI|소비자물가|GDP|무역|환율|원자재|FOMC|연준)", t): return "macro"
    return "general"

def parse_date(entry):
    for key in ("published", "updated", "created"):
        v = entry.get(key)
        if v:
            try:
                return dateparser.parse(v).astimezone(timezone.utc).isoformat()
            except Exception:
                continue
    return None

def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]

def fetch_source(source):
    out = []
    try:
        parsed = feedparser.parse(source["url"])
        for entry in parsed.entries[:30]:
            title = (entry.get("title") or "").strip()
            if not title: continue
            summary = clean_html(entry.get("summary") or entry.get("description") or "")
            url = entry.get("link") or ""
            content_text = f"{title} {summary}"
            tickers = extract_tickers(content_text)
            primary = tickers[0] if tickers else None
            raw_id = f"kr:{url or title}"
            item_id = "kr_" + hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:14]
            out.append({
                "id": item_id,
                "market": "kr",
                "provider": "rss",
                "ticker": primary[1] if primary else None,
                "ticker_name": primary[0] if primary else None,
                "category": categorize(title),
                "title": title,
                "title_kr": title,  # already Korean; no translation needed
                "summary": summary,
                "summary_kr": summary,
                "url": url,
                "source": source["name"],
                "published_at": parse_date(entry),
                "related_tickers": [{"name": n, "code": c} for n, c in tickers[1:5]],
            })
    except Exception as e:
        print(f"[kr-news] {source['name']} failed: {e}")
    return out

def main():
    all_items = []
    seen = set()
    for s in SOURCES:
        for n in fetch_source(s):
            if n["url"] in seen: continue
            seen.add(n["url"])
            all_items.append(n)
        print(f"[kr-news] {s['name']}: total so far {len(all_items)}")

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    all_items = all_items[:250]

    out_path = "/tmp/news_kr.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": all_items, "fetched_at": datetime.now(timezone.utc).isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[kr-news] wrote {len(all_items)} items → {out_path}")

if __name__ == "__main__":
    main()
