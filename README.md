# US Market Live

실시간 미국 주식 뉴스 · 센티먼트 대시보드. GitHub Pages 정적 사이트 + GitHub Actions 크론 파이프라인.

**Live**: https://chkeum.github.io/us-news-live/ (배포 후)

---

## 무엇을 하는 사이트

- **실시간 뉴스 피드** — Finnhub, Yahoo Finance, Benzinga, CNBC, Seeking Alpha
- **리테일 센티먼트** — /r/wallstreetbets, /r/stocks, /r/investing
- **AI 감성 스코어** — Alpha Vantage NEWS_SENTIMENT
- **자동 한글 번역** — DeepL 우선, Google 번역 폴백
- **인덱스 · 워치리스트 실시간 시세** — Finnhub Quote API
- **Trending 티커** — Reddit 언급량 랭킹
- **카테고리 필터** — Breaking / Earnings / Analyst / M&A / Reddit / Macro
- **티커 필터** — 심볼 입력으로 즉시 필터링
- **다크 모드**
- **브라우저 푸시 알림** (옵션)

---

## 아키텍처

```
 ┌─────────────────────────┐       ┌──────────────────────────┐
 │ GitHub Actions (cron)   │  5분  │ Python Crawlers          │
 │  .github/workflows/     ├──────►│  scripts/crawl_*.py      │
 │  crawl-news.yml         │       │                          │
 └─────────────────────────┘       └──────────┬───────────────┘
                                               │ aggregate.py
                                               ▼
                                   ┌──────────────────────────┐
                                   │ data/news_feed.json      │
                                   │ data/market_snapshot.json│
                                   │ (committed to main)      │
                                   └──────────┬───────────────┘
                                              │ git push
                                              ▼
                                   ┌──────────────────────────┐
                                   │ GitHub Pages             │
                                   │  index.html + app.js     │
                                   │  (30초 자동 새로고침)    │
                                   └──────────────────────────┘
```

---

## 배포 가이드

### 1. GitHub 리포 생성

```bash
cd us-news-live
git init
git add .
git commit -m "initial commit"
gh repo create chkeum/us-news-live --public --source=. --remote=origin --push
```

### 2. GitHub Pages 활성화

Settings → Pages → Branch: `main`, Folder: `/ (root)` → Save

2-3분 후 `https://chkeum.github.io/us-news-live/` 접속 가능.

### 3. API 키 발급 & Secrets 설정

#### 필수: Finnhub

1. https://finnhub.io/dashboard 접속 → 무료 가입
2. 발급된 API 키 복사
3. GitHub Repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `FINNHUB_API_KEY`
   - Value: (복사한 키)

무료 한도: 60 req/min · 시세/뉴스 양쪽 커버 가능.

#### 권장: Alpha Vantage (AI 감성 스코어)

1. https://www.alphavantage.co/support/#api-key → 무료 가입
2. Secret name: `ALPHAVANTAGE_API_KEY`

무료 한도: 25 req/day · 우선순위 5개 티커만 수집 중.

#### 권장: DeepL (번역 품질 향상)

1. https://www.deepl.com/pro-api → 무료 개발자 계정
2. Secret name: `DEEPL_API_KEY` (키 끝이 `:fx`면 free tier)

무료 한도: 500k chars/month. 미설정 시 Google 번역 폴백 자동 사용.

### 4. 크론 수동 테스트

```bash
# Actions 탭 → Crawl News → Run workflow
```

3-5분 후 `data/news_feed.json`이 업데이트되면 성공.

### 5. 워치리스트 커스터마이징

`assets/app.js`의 `DEFAULT_WATCHLIST` 배열 수정. 브라우저 localStorage에서도 오버라이드 가능.

---

## 로컬 개발

### 프론트엔드만 확인

```bash
python -m http.server 8000
# → http://localhost:8000
```

### 크롤러 로컬 실행

```bash
cd scripts
pip install -r requirements.txt

export FINNHUB_API_KEY=your_key
export ALPHAVANTAGE_API_KEY=your_key   # optional
export DEEPL_API_KEY=your_key          # optional

python crawl_finnhub.py
python crawl_rss.py
python crawl_reddit.py
python crawl_alphavantage.py
python aggregate.py
python translate.py
```

결과가 `data/news_feed.json`과 `data/market_snapshot.json`에 저장됨.

---

## 커스터마이징

### 추적 티커 추가

`scripts/crawl_finnhub.py` · `scripts/crawl_rss.py` · `scripts/crawl_reddit.py`의 `TICKERS` 리스트에 추가.

### 뉴스 소스 추가

`scripts/crawl_rss.py`의 `SOURCES` 배열에 RSS URL 추가.

### 카테고리 규칙 수정

`scripts/crawl_rss.py`의 `categorize()` 함수.

### 크롤 주기 변경

`.github/workflows/crawl-news.yml`의 `cron` 표현식 조정. GitHub Actions 최소 5분 주기.

### 디자인 토큰

`assets/styles.css` 최상단 `:root` 변수에서 전체 색상·간격 토큰 정의.

---

## 제한 사항

- **GitHub Actions 크론은 정확한 5분이 아니에요** — 로드에 따라 5-15분 편차 있을 수 있어요. 진짜 1초 단위 실시간이 필요하면 Cloudflare Workers 또는 Vercel Serverless로 이전 필요.
- **Reddit 공개 JSON 엔드포인트 레이트 제한** — IP 기준 분당 60회. 현재 스크립트는 sleep 1.2s로 안전 구간 유지.
- **Alpha Vantage 25 req/day 한도** — 우선순위 티커 5개만 수집. 더 필요하면 유료 플랜 또는 다른 감성 API 고려.
- **GitHub Pages 빌드는 push 후 30-60초 지연** — 데이터 갱신은 JSON fetch라 즉시 반영.

---

## Phase 2 — KR 시장 통합 ✅

- `scripts/crawl_kr_news.py` — 한경·매경·이데일리·조선비즈·연합뉴스·Google News RSS
- `scripts/crawl_dart.py` — DART 전자공시 (OPENDART_API_KEY 필요)
- `scripts/crawl_kr_quotes.py` — 네이버 금융 시세 (KOSPI·KOSDAQ·워치리스트)
- `scripts/aggregate_kr.py` — 통합·중복 제거·무드 스코어
- **KR 탭** — 상단에서 🇺🇸 US / 🇰🇷 KR 원클릭 전환, 데이터·워치리스트 독립
- **60+ 한국 종목 매핑** — 반도체·2차전지·바이오·자동차·금융·플랫폼·방산·엔터

### DART API 키 발급 (선택사항, 공시 수집용)

1. https://opendart.fss.or.kr/intro/main.do → 인증키 신청 (즉시 발급, 무료)
2. Repo Settings → Secrets → `OPENDART_API_KEY`

무료 한도: 일 20,000건 (사실상 무제한).

## 향후 Phase

- **Phase 3** (Cross-Market) — 오버나잇 US → KR 파생 영향 예측, 섹터 커플링, 환율·금리 매크로
- **Phase 4** (PWA) — 모바일 홈 화면 설치, Service Worker 푸시

---

## License

MIT
