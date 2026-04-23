"""DART (금융감독원 전자공시) 공시 크롤러.

OpenDART API는 무료이지만 API 키가 필요해요.
발급: https://opendart.fss.or.kr/intro/main.do → 신청 → 인증키 발급 (즉시)
한도: 일 20,000건 (사실상 무제한)

Usage:
  OPENDART_API_KEY=xxx python crawl_dart.py
Outputs: /tmp/news_dart.json
"""
import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

KEY = os.environ.get("OPENDART_API_KEY", "")
API = "https://opendart.fss.or.kr/api"

# 추적 기업 고유번호 (DART corp_code). 자주 쓰는 것만 수록 — 필요 시 확장.
# corp_code 조회: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018
CORP_CODES = {
    "00126380": "삼성전자",
    "00164779": "SK하이닉스",
    "01373294": "LG에너지솔루션",
    "00258801": "현대차",
    "00149655": "기아",
    "00431745": "포스코홀딩스",
    "00106641": "NAVER",
    "00918490": "카카오",
    "00258999": "LG화학",
    "01099081": "삼성바이오로직스",
    "00164742": "셀트리온",
    "00401731": "KB금융",
    "00382199": "신한지주",
    "00401001": "SK이노베이션",
    "01540339": "한화오션",
    "00145648": "크래프톤",
    "00109718": "하이브",
}

# 주요 공시 유형
PSHTM_CODES = {
    "A": "정기공시",
    "B": "주요사항보고",
    "C": "발행공시",
    "D": "지분공시",
    "E": "기타공시",
    "F": "외부감사관련",
    "G": "펀드공시",
    "H": "자산유동화",
    "I": "거래소공시",
    "J": "공정위공시",
}

def categorize_disclosure(report_nm):
    t = report_nm
    if any(k in t for k in ("영업잠정", "매출액", "분기보고서", "사업보고서", "반기보고서")): return "earnings"
    if any(k in t for k in ("유상증자", "전환사채", "신주인수권", "회사채")): return "ma"
    if any(k in t for k in ("지분변동", "대량보유", "주식등의대량보유")): return "analyst"
    if any(k in t for k in ("합병", "분할", "양수", "양도", "인수", "자회사")): return "ma"
    return "general"

def fetch_disclosures(days=2, page_count=100):
    if not KEY:
        print("[dart] no OPENDART_API_KEY — skipping")
        return []
    end_de = datetime.now(timezone.utc).strftime("%Y%m%d")
    bgn_de = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    out = []
    try:
        r = requests.get(f"{API}/list.json", params={
            "crtfc_key": KEY,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": page_count,
            "sort": "date",
            "sort_mth": "desc",
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "000":
            print(f"[dart] API error: {data.get('message')}")
            return []
        for item in data.get("list", []):
            corp_code = item.get("corp_code")
            corp_name = item.get("corp_name")
            report_nm = item.get("report_nm")
            rcept_no = item.get("rcept_no")
            rcept_dt = item.get("rcept_dt")  # YYYYMMDD
            stock_code = item.get("stock_code") or ""
            try:
                dt = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                dt = None
            item_id = "dt_" + hashlib.sha1(f"dart:{rcept_no}".encode("utf-8")).hexdigest()[:14]
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            out.append({
                "id": item_id,
                "market": "kr",
                "provider": "dart",
                "ticker": stock_code or None,
                "ticker_name": corp_name,
                "category": categorize_disclosure(report_nm),
                "title": f"[공시] {corp_name} — {report_nm}",
                "title_kr": f"[공시] {corp_name} — {report_nm}",
                "summary": f"접수번호 {rcept_no} · 접수일 {rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}",
                "summary_kr": f"접수번호 {rcept_no} · 접수일 {rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}",
                "url": url,
                "source": "DART 전자공시",
                "published_at": dt,
            })
    except Exception as e:
        print(f"[dart] fetch failed: {e}")
    return out

def main():
    items = fetch_disclosures(days=2, page_count=100)
    # Only keep tracked corps + material reports (정기공시·주요사항·지분공시)
    filtered = []
    for it in items:
        # keep if corp tracked or if categorized as earnings/ma/analyst
        if it.get("category") in ("earnings", "ma", "analyst"):
            filtered.append(it)
            continue
        # keep disclosures for tracked stock codes (map requires corp_code → but stock_code works too)
        if any(it.get("ticker") == code for code in [
            "005930", "000660", "373220", "005380", "000270", "005490", "035420", "035720",
            "051910", "207940", "068270", "105560", "055550", "096770", "042660", "259960", "352820",
        ]):
            filtered.append(it)

    filtered.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    filtered = filtered[:100]

    out_path = "/tmp/news_dart.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": filtered, "fetched_at": datetime.now(timezone.utc).isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[dart] wrote {len(filtered)} items (from {len(items)} total) → {out_path}")

if __name__ == "__main__":
    main()
