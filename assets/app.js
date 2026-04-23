/* ============================================================
   US/KR Market Live — App logic (vanilla JS, no build step)
   ============================================================ */
(() => {
  'use strict';

  // -------- Config --------
  const ENDPOINTS = {
    us:    { feed: 'data/news_feed.json',    market: 'data/market_snapshot.json' },
    kr:    { feed: 'data/news_feed_kr.json', market: 'data/market_snapshot_kr.json' },
    cross: { feed: null,                     market: 'data/cross_market.json'     },
  };
  const AUTO_REFRESH_MS = 30_000;
  const DEFAULT_WATCHLIST = {
    us: ['NVDA', 'MRVL', 'TSLA', 'MSTR', 'GOOGL', 'AMD', 'META', 'MSFT', 'AMZN', 'AVGO'],
    kr: ['005930', '000660', '373220', '005380', '035420', '035720', '207940', '005490', '051910', '247540'],
  };
  const STATUS_FIELDS = {
    us: [
      { id: 'sp500',  label: 'S&P 500' },
      { id: 'nasdaq', label: 'Nasdaq'   },
      { id: 'dow',    label: 'Dow'      },
      { id: 'vix',    label: 'VIX'      },
      { id: 'btc',    label: 'BTC'      },
    ],
    kr: [
      { id: 'kospi',    label: 'KOSPI'    },
      { id: 'kosdaq',   label: 'KOSDAQ'   },
      { id: 'kospi200', label: 'KOSPI 200'},
    ],
  };

  // -------- State --------
  const state = {
    market: 'us',         // active market tab
    feed: { us: [], kr: [] },
    snap: { us: null, kr: null, cross: null },
    filtered: [],
    watchlist: loadWatchlist(),
    activeFilter: 'all',
    tickerQuery: '',
    lastFetchedAt: null,
  };

  // -------- DOM refs --------
  const el = {
    liveTime: document.getElementById('liveTime'),
    sessionDot: document.getElementById('sessionDot'),
    sessionLabel: document.getElementById('sessionLabel'),
    statusBar: document.getElementById('statusBar'),
    newsList: document.getElementById('newsList'),
    feedCount: document.getElementById('feedCount'),
    lastUpdate: document.getElementById('lastUpdate'),
    watchlist: document.getElementById('watchlist'),
    trending: document.getElementById('trending'),
    filterTabs: document.querySelectorAll('.filter-tab'),
    marketTabs: document.querySelectorAll('.market-tab'),
    tickerFilter: document.getElementById('tickerFilter'),
    themeToggle: document.getElementById('themeToggle'),
    alertsBtn: document.getElementById('alertsBtn'),
    detailOverlay: document.getElementById('detailOverlay'),
    detailBody: document.getElementById('detailBody'),
    detailClose: document.getElementById('detailClose'),
    moodScore: document.getElementById('moodScore'),
    moodLabel: document.getElementById('moodLabel'),
    moodFill: document.getElementById('moodFill'),
    moodCaption: document.getElementById('moodCaption'),
    mainView: document.getElementById('mainView'),
    crossView: document.getElementById('crossView'),
    crossSummary: document.getElementById('crossSummary'),
    crossDigest: document.getElementById('crossDigest'),
    crossSectors: document.getElementById('crossSectors'),
    crossPairs: document.getElementById('crossPairs'),
  };

  // -------- Utilities --------
  function loadWatchlist() {
    try {
      const stored = localStorage.getItem('watchlist_v2');
      return stored ? JSON.parse(stored) : {
        us: [...DEFAULT_WATCHLIST.us],
        kr: [...DEFAULT_WATCHLIST.kr],
      };
    } catch { return { us: [...DEFAULT_WATCHLIST.us], kr: [...DEFAULT_WATCHLIST.kr] }; }
  }
  function saveWatchlist() {
    try { localStorage.setItem('watchlist_v2', JSON.stringify(state.watchlist)); } catch {}
  }
  function formatChange(pct) {
    if (pct == null || isNaN(pct)) return '—';
    const sign = pct > 0 ? '+' : '';
    return `${sign}${Number(pct).toFixed(1)}%`;
  }
  function formatNumber(n, decimals = 2) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
  }
  function formatKRW(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toLocaleString('ko-KR');
  }
  function formatRelativeTime(iso) {
    if (!iso) return '—';
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diff = Math.max(0, now - then);
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  }
  function getSessionState() {
    const now = new Date();
    if (state.market === 'kr') {
      // KST 09:00-15:30. User's local time (assumed KST).
      const t = now.getHours() * 60 + now.getMinutes();
      const day = now.getDay();
      if (day === 0 || day === 6) return { state: 'closed', label: '장 마감 (주말)' };
      if (t >= 540 && t < 930) return { state: 'open', label: 'KR 장 진행중' };
      if (t >= 480 && t < 540) return { state: 'pre', label: 'KR 동시호가' };
      if (t >= 930 && t < 990) return { state: 'post', label: 'KR 시간외' };
      return { state: 'closed', label: 'KR 장 마감' };
    }
    // US session check (UTC hours)
    const utc = now.getUTCHours() * 60 + now.getUTCMinutes();
    if (utc >= 810 && utc < 1200) return { state: 'open', label: 'US 장 진행중' };
    if (utc >= 540 && utc < 810) return { state: 'pre', label: 'US 프리마켓' };
    if (utc >= 1200 && utc < 1440) return { state: 'post', label: 'US 시간외' };
    return { state: 'closed', label: 'US 장 마감' };
  }
  function updateClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    el.liveTime.textContent = `${hh}:${mm}:${ss}`;
    const session = getSessionState();
    el.sessionDot.className = 'status-bar__session-dot';
    if (session.state === 'open') el.sessionDot.classList.add('is-open');
    else if (session.state === 'pre' || session.state === 'post') el.sessionDot.classList.add('is-pre');
    else el.sessionDot.classList.add('is-closed');
    el.sessionLabel.textContent = session.label;
  }

  // -------- Rendering --------
  function renderStatusBar() {
    const snap = state.snap[state.market];
    const fields = STATUS_FIELDS[state.market] || [];
    if (!snap) return;

    // Remove all items except the session span
    const sessionEl = el.sessionDot.parentElement;
    [...el.statusBar.children].forEach(c => { if (c !== sessionEl) c.remove(); });

    // Build items fresh
    fields.forEach(f => {
      const ob = snap[f.id];
      const valTxt = ob ? formatNumber(ob.price) : '—';
      const chgTxt = ob ? formatChange(ob.change_pct) : '—';
      const upDown = ob && ob.change_pct > 0 ? 'is-up' : (ob && ob.change_pct < 0 ? 'is-down' : '');

      const item = document.createElement('div');
      item.className = 'status-bar__item';
      item.innerHTML = `
        <div class="status-bar__label">${f.label}</div>
        <div class="status-bar__value">${valTxt}</div>
        <div class="status-bar__change ${upDown}">${chgTxt}</div>`;
      el.statusBar.insertBefore(item, sessionEl);
    });
  }

  function renderMoodPanel() {
    const snap = state.snap[state.market];
    if (!snap) return;
    const score = snap.mood_score;
    const mood = snap.mood;
    if (score == null) return;
    el.moodScore.textContent = score;
    el.moodFill.style.width = `${score}%`;
    el.moodFill.classList.remove('is-bearish', 'is-neutral');
    el.moodLabel.classList.remove('is-bullish', 'is-bearish', 'is-neutral');
    let label = 'Neutral';
    if (mood === 'bullish') { label = 'Bullish'; el.moodLabel.classList.add('is-bullish'); }
    else if (mood === 'bearish') { label = 'Bearish'; el.moodLabel.classList.add('is-bearish'); el.moodFill.classList.add('is-bearish'); }
    else { el.moodLabel.classList.add('is-neutral'); el.moodFill.classList.add('is-neutral'); }
    el.moodLabel.textContent = label;
    el.moodCaption.textContent = snap.mood_summary || '';
  }

  function renderWatchlist() {
    const snap = state.snap[state.market];
    if (!snap?.watchlist) return;
    const codes = state.watchlist[state.market];
    const rows = codes.map(code => {
      const d = snap.watchlist[code];
      if (!d) {
        return `
        <div class="watch-item">
          <div>
            <div class="watch-item__ticker">${code}</div>
            <div class="watch-item__price">—</div>
          </div>
          <div class="watch-item__change">—</div>
        </div>`;
      }
      const upDown = d.change_pct > 0 ? 'is-up' : (d.change_pct < 0 ? 'is-down' : '');
      const display = d.name || code;
      const priceStr = state.market === 'kr'
        ? `₩${formatKRW(d.price)}`
        : `$${formatNumber(d.price)}`;
      return `
        <div class="watch-item" data-ticker="${code}">
          <div>
            <div class="watch-item__ticker">${display}</div>
            <div class="watch-item__price">${priceStr}</div>
          </div>
          <div class="watch-item__change ${upDown}">${formatChange(d.change_pct)}</div>
        </div>`;
    }).join('');
    el.watchlist.innerHTML = rows;
    el.watchlist.querySelectorAll('.watch-item').forEach(item => {
      item.addEventListener('click', () => {
        const t = item.dataset.ticker;
        el.tickerFilter.value = t;
        state.tickerQuery = t;
        applyFilters();
      });
    });
  }

  function renderTrending() {
    const snap = state.snap[state.market];
    const list = snap?.trending || [];
    el.trending.innerHTML = list.slice(0, 5).map((t, i) => {
      const label = t.name || t.ticker;
      return `
      <div class="trend-item" data-ticker="${t.ticker}">
        <span class="trend-item__rank">${i + 1}</span>
        <span class="trend-item__ticker">${label}</span>
        <span class="trend-item__mentions">${formatNumber(t.mentions, 0)}</span>
        <span class="trend-item__spark">${t.surge_pct > 0 ? '+' + Math.round(t.surge_pct) + '%' : ''}</span>
      </div>`;
    }).join('');
    el.trending.querySelectorAll('.trend-item').forEach(item => {
      item.addEventListener('click', () => {
        const t = item.dataset.ticker;
        el.tickerFilter.value = t;
        state.tickerQuery = t;
        applyFilters();
      });
    });
  }

  function renderFeed() {
    if (state.filtered.length === 0) {
      el.newsList.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__title">표시할 뉴스가 없어요</div>
          <div class="empty-state__hint">필터를 바꾸거나 잠시 후 다시 확인해보세요</div>
        </div>`;
      el.feedCount.textContent = '0';
      return;
    }

    el.newsList.innerHTML = state.filtered.map(n => {
      const cat = (n.category || '').toLowerCase();
      const ticker = n.ticker_name || n.ticker || '';
      const change = n.change_pct;
      const changeCls = change > 0 ? 'is-up' : (change < 0 ? 'is-down' : '');
      const changeTxt = change != null ? formatChange(change) : '';
      const sentimentCls = n.sentiment > 0.1 ? 'is-up' : (n.sentiment < -0.1 ? 'is-down' : '');
      const sentimentVal = n.sentiment != null ? (n.sentiment > 0 ? '+' : '') + Number(n.sentiment).toFixed(2) : null;

      const cardClasses = ['news-card'];
      if (cat === 'breaking') cardClasses.push('news-card--breaking');
      else if (cat === 'reddit') cardClasses.push('news-card--reddit');
      else if (cat === 'analyst') cardClasses.push('news-card--analyst');
      else if (cat === 'earnings') cardClasses.push('news-card--earnings');
      else if (n.sentiment > 0.3) cardClasses.push('news-card--positive');
      else if (n.sentiment < -0.3) cardClasses.push('news-card--negative');

      const categoryBadge = cat && cat !== 'general'
        ? `<span class="news-card__category news-card__category--${cat}">${cat}</span>`
        : '';

      const titleMain = n.title_kr || n.title;
      const titleSub = (n.title_kr && n.title_kr !== n.title) ? n.title : null;

      return `
        <article class="${cardClasses.join(' ')}" data-id="${n.id || ''}">
          <div class="news-card__header">
            ${categoryBadge}
            ${ticker ? `<span class="news-card__ticker">${escapeHTML(ticker)}</span>` : ''}
            ${changeTxt ? `<span class="news-card__change ${changeCls}">${changeTxt}</span>` : ''}
            <span class="news-card__meta">${escapeHTML(n.source || '')} · ${formatRelativeTime(n.published_at)}</span>
          </div>
          <h3 class="news-card__title">${escapeHTML(titleMain)}</h3>
          ${titleSub ? `<p class="news-card__title-kr">${escapeHTML(titleSub)}</p>` : ''}
          <div class="news-card__footer">
            ${sentimentVal
              ? `<span class="news-card__sentiment">Sentiment <span class="news-card__sentiment-value ${sentimentCls}">${sentimentVal}</span></span>`
              : ''}
            ${n.extra_meta ? `<span class="news-card__footer-sep">·</span><span>${escapeHTML(n.extra_meta)}</span>` : ''}
          </div>
        </article>`;
    }).join('');

    el.newsList.querySelectorAll('.news-card').forEach(card => {
      card.addEventListener('click', () => openDetail(card.dataset.id));
    });

    el.feedCount.textContent = `${state.filtered.length} items`;
  }

  function escapeHTML(str) {
    if (str == null) return '';
    return String(str)
      .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  }

  function openDetail(id) {
    const feed = state.feed[state.market] || [];
    const item = feed.find(n => n.id === id);
    if (!item) return;
    el.detailBody.innerHTML = `
      <h3>${escapeHTML(item.title_kr || item.title)}</h3>
      ${item.title_kr && item.title_kr !== item.title ? `<p style="color: var(--fg-secondary); font-size: 13px;">${escapeHTML(item.title)}</p>` : ''}
      <p style="font-size: 11px; color: var(--fg-tertiary); text-transform: uppercase; letter-spacing: 0.05em;">
        ${escapeHTML(item.source || 'Source')} · ${formatRelativeTime(item.published_at)}
      </p>
      ${item.summary_kr ? `<p>${escapeHTML(item.summary_kr)}</p>` : (item.summary ? `<p>${escapeHTML(item.summary)}</p>` : '')}
      ${item.summary && item.summary !== item.summary_kr ? `<p style="border-left: 3px solid var(--border-default); padding-left: 12px; color: var(--fg-secondary); font-size: 13px;">${escapeHTML(item.summary)}</p>` : ''}
      ${item.url ? `<p><a href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">원문 보기 →</a></p>` : ''}
    `;
    el.detailOverlay.classList.add('is-open');
    el.detailOverlay.setAttribute('aria-hidden', 'false');
  }
  function closeDetail() {
    el.detailOverlay.classList.remove('is-open');
    el.detailOverlay.setAttribute('aria-hidden', 'true');
  }

  // -------- Filters --------
  function applyFilters() {
    const f = state.activeFilter;
    const q = state.tickerQuery.trim().toUpperCase();
    const feed = state.feed[state.market] || [];
    state.filtered = feed.filter(n => {
      if (f !== 'all') {
        const cat = (n.category || '').toLowerCase();
        if (f === 'ma') { if (!['ma', 'm&a', 'merger'].includes(cat)) return false; }
        else if (cat !== f) return false;
      }
      if (q) {
        const ticker = (n.ticker || '').toUpperCase();
        const name = (n.ticker_name || '').toUpperCase();
        if (!ticker.includes(q) && !name.includes(q)) return false;
      }
      return true;
    });
    renderFeed();
  }

  function setMarket(market) {
    if (state.market === market) return;
    state.market = market;
    el.marketTabs.forEach(t => {
      const isActive = t.dataset.market === market;
      t.classList.toggle('is-active', isActive);
      t.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    // Reset ticker query + filter
    state.tickerQuery = '';
    el.tickerFilter.value = '';
    state.activeFilter = 'all';
    el.filterTabs.forEach(t => t.classList.toggle('is-active', t.dataset.filter === 'all'));
    el.tickerFilter.placeholder = market === 'kr' ? '종목명·종목코드로 필터...' : 'Filter by ticker (e.g. NVDA)';

    // Toggle view mode (cross vs main)
    const isCross = market === 'cross';
    el.mainView.hidden = isCross;
    el.crossView.hidden = !isCross;

    if (isCross) {
      renderCross();
    } else {
      renderStatusBar();
      renderWatchlist();
      renderTrending();
      renderMoodPanel();
      applyFilters();
    }
    updateClock();
    try { localStorage.setItem('active_market', market); } catch {}
  }

  // -------- Cross-Market rendering --------
  function renderCross() {
    const cm = state.snap.cross;
    if (!cm) {
      el.crossSummary.innerHTML = '<div class="empty-state"><div class="empty-state__title">Cross-market 데이터 수집 중</div><div class="empty-state__hint">잠시 후 다시 확인해보세요</div></div>';
      return;
    }

    // Summary
    const usM = cm.us_mood_score || 50;
    const krM = cm.kr_mood_score || 50;
    const usMClass = cm.us_mood === 'bullish' ? 'is-bullish' : (cm.us_mood === 'bearish' ? 'is-bearish' : '');
    const krMClass = cm.kr_mood === 'bullish' ? 'is-bullish' : (cm.kr_mood === 'bearish' ? 'is-bearish' : '');
    el.crossSummary.innerHTML = `
      <div class="cross-summary__caption">🌐 Cross-Market · ${formatRelativeTime(cm.fetched_at)}</div>
      <div class="cross-summary__line">${escapeHTML(cm.summary || '')}</div>
      <div class="cross-summary__moods">
        <div class="cross-summary__mood">
          <span class="cross-summary__mood-flag">🇺🇸</span>
          <span class="cross-summary__mood-label">US Mood</span>
          <span class="cross-summary__mood-score ${usMClass}">${usM}/100</span>
        </div>
        <div class="cross-summary__mood">
          <span class="cross-summary__mood-flag">🇰🇷</span>
          <span class="cross-summary__mood-label">KR Mood</span>
          <span class="cross-summary__mood-score ${krMClass}">${krM}/100</span>
        </div>
        ${cm.macro?.vix ? `
        <div class="cross-summary__mood">
          <span class="cross-summary__mood-label">VIX</span>
          <span class="cross-summary__mood-score">${Number(cm.macro.vix.price).toFixed(1)} ${cm.macro.vix.change_pct > 0 ? '↑' : '↓'}</span>
        </div>` : ''}
        ${cm.macro?.btc ? `
        <div class="cross-summary__mood">
          <span class="cross-summary__mood-label">BTC</span>
          <span class="cross-summary__mood-score ${cm.macro.btc.change_pct > 0 ? 'is-bullish' : 'is-bearish'}">${formatChange(cm.macro.btc.change_pct)}</span>
        </div>` : ''}
      </div>`;

    // Overnight digest
    const digest = cm.overnight_digest || [];
    el.crossDigest.innerHTML = digest.length === 0
      ? '<div class="empty-state"><div class="empty-state__hint">최근 24시간 하이라이트 없음</div></div>'
      : digest.map(d => `
          <article class="digest-card" data-ticker="${escapeHTML(d.ticker || '')}">
            <div class="digest-card__header">
              <span class="digest-card__ticker">${escapeHTML(d.ticker || '')}</span>
              ${d.category ? `<span class="digest-card__badge">${escapeHTML(d.category)}</span>` : ''}
              <span style="margin-left:auto; font-size:10px; color: var(--fg-tertiary);">${formatRelativeTime(d.published_at)}</span>
            </div>
            <div class="digest-card__title">${escapeHTML(d.title_kr || d.title || '')}</div>
            <div class="digest-card__pairs">
              <span class="digest-card__pairs-label">KR 영향</span>
              ${(d.kr_pairs || []).map(p => `<span class="digest-card__pair-chip">${escapeHTML(p)}</span>`).join('')}
            </div>
          </article>
        `).join('');

    // Sector coupling
    const sectors = cm.sector_coupling || [];
    el.crossSectors.innerHTML = sectors.length === 0
      ? '<div class="empty-state"><div class="empty-state__hint">섹터 커플링 계산 중</div></div>'
      : sectors.map(s => {
          const predCls = s.predicted_kr_avg_pct > 0 ? 'is-up' : (s.predicted_kr_avg_pct < 0 ? 'is-down' : '');
          const actCls = s.kr_actual_avg_pct > 0 ? 'is-up' : (s.kr_actual_avg_pct < 0 ? 'is-down' : '');
          return `
          <div class="sector-card">
            <div class="sector-card__flow">
              <div class="sector-card__side">
                <div class="sector-card__label"><span class="sector-card__flag">🇺🇸</span>${escapeHTML(s.us_sector)}</div>
              </div>
              <span class="sector-card__arrow">→</span>
              <div class="sector-card__side">
                <div class="sector-card__label"><span class="sector-card__flag">🇰🇷</span>${escapeHTML(s.kr_sector)}</div>
              </div>
            </div>
            <div class="sector-card__metrics">
              <span class="sector-card__us">US ${formatChange(s.us_avg_pct)}</span>
              <span class="sector-card__arrow">×</span>
              <span class="pairs-table__beta">β ${s.beta.toFixed(2)}</span>
              <span class="sector-card__arrow">=</span>
              <span class="sector-card__pred ${predCls}">예상 ${formatChange(s.predicted_kr_avg_pct)}</span>
              ${s.kr_actual_avg_pct != null ? `<span class="sector-card__actual ${actCls}">실제 ${formatChange(s.kr_actual_avg_pct)}</span>` : ''}
            </div>
          </div>`;
        }).join('');

    // Pair predictions
    const pairs = cm.predictions || [];
    el.crossPairs.innerHTML = pairs.length === 0
      ? '<div class="empty-state"><div class="empty-state__hint">종목 페어 데이터 없음</div></div>'
      : `<table class="pairs-table">
          <thead>
            <tr>
              <th>US 티커</th>
              <th class="is-num">US %</th>
              <th>KR 종목</th>
              <th class="is-num">β</th>
              <th class="is-num">예상</th>
              <th class="is-num">실제</th>
              <th>연결 이유</th>
            </tr>
          </thead>
          <tbody>
            ${pairs.map(p => {
              const usCls = p.us_change_pct > 0 ? 'is-up' : (p.us_change_pct < 0 ? 'is-down' : '');
              const predCls = p.predicted_kr_pct > 0 ? 'is-up' : (p.predicted_kr_pct < 0 ? 'is-down' : '');
              return `<tr>
                <td><span class="pairs-table__ticker">${escapeHTML(p.us_ticker)}</span></td>
                <td class="is-num pairs-table__us ${usCls}">${formatChange(p.us_change_pct)}</td>
                <td>${escapeHTML(p.kr_name)}</td>
                <td class="is-num pairs-table__beta">${p.beta.toFixed(2)}</td>
                <td class="is-num pairs-table__pred ${predCls}">${formatChange(p.predicted_kr_pct)}</td>
                <td class="is-num" style="color: var(--fg-tertiary)">${p.actual_kr_pct != null ? formatChange(p.actual_kr_pct) : '—'}</td>
                <td class="pairs-table__reason">${escapeHTML(p.reason)}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`;

    el.crossDigest.querySelectorAll('.digest-card').forEach(c => {
      c.addEventListener('click', () => {
        const ticker = c.dataset.ticker;
        // Switch to US tab and filter by ticker
        setMarket('us');
        setTimeout(() => {
          el.tickerFilter.value = ticker;
          state.tickerQuery = ticker;
          applyFilters();
        }, 50);
      });
    });
  }

  // -------- Fetching --------
  async function fetchMarketData(market) {
    const ep = ENDPOINTS[market];
    try {
      const [feedRes, marketRes] = await Promise.all([
        fetch(ep.feed + '?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(ep.market + '?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (feedRes?.items) state.feed[market] = feedRes.items;
      if (marketRes) state.snap[market] = marketRes;
    } catch (err) {
      console.error(`[fetch] ${market} failed:`, err);
    }
  }

  async function fetchCrossMarket() {
    try {
      const r = await fetch('data/cross_market.json?t=' + Date.now());
      if (r.ok) state.snap.cross = await r.json();
    } catch (err) {
      console.error('[fetch] cross failed:', err);
    }
  }

  async function fetchAll() {
    await Promise.all([fetchMarketData('us'), fetchMarketData('kr'), fetchCrossMarket()]);
    state.lastFetchedAt = new Date();
    el.lastUpdate.textContent = 'Updated ' + formatRelativeTime(state.lastFetchedAt.toISOString());
    if (state.market === 'cross') {
      renderCross();
    } else {
      renderStatusBar();
      renderWatchlist();
      renderTrending();
      renderMoodPanel();
      applyFilters();
    }
  }

  // -------- Events --------
  el.marketTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      if (tab.disabled) return;
      setMarket(tab.dataset.market);
    });
  });
  el.filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      el.filterTabs.forEach(t => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      state.activeFilter = tab.dataset.filter;
      applyFilters();
    });
  });
  el.tickerFilter.addEventListener('input', (e) => {
    state.tickerQuery = e.target.value;
    applyFilters();
  });
  el.themeToggle.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch {}
  });
  el.detailClose.addEventListener('click', closeDetail);
  el.detailOverlay.addEventListener('click', (e) => { if (e.target === el.detailOverlay) closeDetail(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });
  el.alertsBtn.addEventListener('click', async () => {
    if (!('Notification' in window)) { alert('이 브라우저는 알림을 지원하지 않아요.'); return; }
    if (Notification.permission === 'granted') { alert('알림이 이미 켜져 있어요.'); return; }
    const res = await Notification.requestPermission();
    if (res === 'granted') {
      new Notification('알림 활성화 완료', { body: '중요 뉴스가 오면 알려드릴게요.' });
    }
  });

  // -------- Init --------
  try {
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
    const savedMarket = localStorage.getItem('active_market');
    if (['us', 'kr', 'cross'].includes(savedMarket)) state.market = savedMarket;
  } catch {}

  // Sync initial tab state with state.market
  el.marketTabs.forEach(t => {
    const isActive = t.dataset.market === state.market;
    t.classList.toggle('is-active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  el.tickerFilter.placeholder = state.market === 'kr' ? '종목명·종목코드로 필터...' : 'Filter by ticker (e.g. NVDA)';

  // Show correct view on mount
  el.mainView.hidden = (state.market === 'cross');
  el.crossView.hidden = (state.market !== 'cross');

  updateClock();
  setInterval(updateClock, 1000);
  fetchAll();
  setInterval(fetchAll, AUTO_REFRESH_MS);

  // -------- PWA: register service worker --------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('service-worker.js')
        .then(reg => console.log('[pwa] SW registered:', reg.scope))
        .catch(err => console.warn('[pwa] SW registration failed:', err));
    });
  }

  // Install banner
  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallBanner();
  });

  function showInstallBanner() {
    if (localStorage.getItem('install_dismissed') === '1') return;
    if (document.getElementById('installBanner')) return;
    const b = document.createElement('div');
    b.className = 'install-banner';
    b.id = 'installBanner';
    b.innerHTML = `
      <span class="install-banner__text">📱 홈 화면에 설치하면 앱처럼 쓸 수 있어요</span>
      <button class="install-banner__button" id="installBtn">설치</button>
      <button class="install-banner__close" id="installClose">✕</button>
    `;
    document.body.appendChild(b);
    setTimeout(() => b.classList.add('is-visible'), 100);
    document.getElementById('installBtn').addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      b.remove();
    });
    document.getElementById('installClose').addEventListener('click', () => {
      localStorage.setItem('install_dismissed', '1');
      b.remove();
    });
  }

})();
