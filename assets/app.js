/* ============================================================
   US Market Live — App logic (vanilla JS, no build step)
   ============================================================ */
(() => {
  'use strict';

  // -------- Config --------
  const FEED_URL = 'data/news_feed.json';
  const MARKET_URL = 'data/market_snapshot.json';
  const AUTO_REFRESH_MS = 30_000;
  const DEFAULT_WATCHLIST = ['NVDA', 'MRVL', 'TSLA', 'MSTR', 'GOOGL'];

  // -------- State --------
  const state = {
    feed: [],
    filtered: [],
    market: null,
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
    newsList: document.getElementById('newsList'),
    feedCount: document.getElementById('feedCount'),
    lastUpdate: document.getElementById('lastUpdate'),
    watchlist: document.getElementById('watchlist'),
    trending: document.getElementById('trending'),
    filterTabs: document.querySelectorAll('.filter-tab'),
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
    statusFields: {
      sp500: { value: document.getElementById('sp500'), change: document.getElementById('sp500Change') },
      nasdaq: { value: document.getElementById('nasdaq'), change: document.getElementById('nasdaqChange') },
      dow: { value: document.getElementById('dow'), change: document.getElementById('dowChange') },
      vix: { value: document.getElementById('vix'), change: document.getElementById('vixChange') },
      btc: { value: document.getElementById('btc'), change: document.getElementById('btcChange') },
    },
  };

  // -------- Utilities --------
  function loadWatchlist() {
    try {
      const stored = localStorage.getItem('watchlist');
      return stored ? JSON.parse(stored) : [...DEFAULT_WATCHLIST];
    } catch { return [...DEFAULT_WATCHLIST]; }
  }
  function saveWatchlist() {
    try { localStorage.setItem('watchlist', JSON.stringify(state.watchlist)); } catch {}
  }
  function formatChange(pct) {
    if (pct == null || isNaN(pct)) return '—';
    const sign = pct > 0 ? '+' : '';
    return `${sign}${pct.toFixed(1)}%`;
  }
  function formatNumber(n) {
    if (n == null || isNaN(n)) return '—';
    return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
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
  function sentimentLabel(score) {
    if (score == null) return null;
    if (score >= 0.5) return '매우 긍정';
    if (score >= 0.2) return '긍정';
    if (score > -0.2) return '중립';
    if (score > -0.5) return '부정';
    return '매우 부정';
  }
  function getUsSessionState() {
    const now = new Date();
    const utc = now.getUTCHours() * 60 + now.getUTCMinutes();
    // Regular: 13:30 - 20:00 UTC (9:30am - 4:00pm ET, not DST-adjusted)
    // Premarket: 09:00 - 13:30 UTC
    // After-hours: 20:00 - 24:00 UTC
    if (utc >= 810 && utc < 1200) return { state: 'open', label: 'Market open' };
    if (utc >= 540 && utc < 810) return { state: 'pre', label: 'Premarket' };
    if (utc >= 1200 && utc < 1440) return { state: 'post', label: 'After-hours' };
    return { state: 'closed', label: 'Market closed' };
  }
  function updateClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    el.liveTime.textContent = `${hh}:${mm}:${ss}`;
    const session = getUsSessionState();
    el.sessionDot.className = 'status-bar__session-dot';
    if (session.state === 'open') el.sessionDot.classList.add('is-open');
    else if (session.state === 'pre' || session.state === 'post') el.sessionDot.classList.add('is-pre');
    else el.sessionDot.classList.add('is-closed');
    el.sessionLabel.textContent = session.label;
  }

  // -------- Rendering --------
  function renderStatusBar() {
    if (!state.market) return;
    Object.entries(el.statusFields).forEach(([key, refs]) => {
      const ob = state.market[key];
      if (!ob) return;
      refs.value.textContent = formatNumber(ob.price);
      const txt = formatChange(ob.change_pct);
      refs.change.textContent = txt;
      refs.change.classList.remove('is-up', 'is-down');
      if (ob.change_pct > 0) refs.change.classList.add('is-up');
      else if (ob.change_pct < 0) refs.change.classList.add('is-down');
    });
  }

  function renderMoodPanel() {
    if (!state.market) return;
    const score = state.market.mood_score;
    const mood = state.market.mood;
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
    el.moodCaption.textContent = state.market.mood_summary || '';
  }

  function renderWatchlist() {
    if (!state.market?.watchlist) return;
    const rows = state.watchlist.map(ticker => {
      const d = state.market.watchlist[ticker];
      if (!d) return `
        <div class="watch-item">
          <div>
            <div class="watch-item__ticker">${ticker}</div>
            <div class="watch-item__price">—</div>
          </div>
          <div class="watch-item__change">—</div>
        </div>`;
      const upDown = d.change_pct > 0 ? 'is-up' : (d.change_pct < 0 ? 'is-down' : '');
      return `
        <div class="watch-item" data-ticker="${ticker}">
          <div>
            <div class="watch-item__ticker">${ticker}</div>
            <div class="watch-item__price">$${formatNumber(d.price)}</div>
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
    const list = state.market?.trending || [];
    el.trending.innerHTML = list.slice(0, 5).map((t, i) => `
      <div class="trend-item" data-ticker="${t.ticker}">
        <span class="trend-item__rank">${i + 1}</span>
        <span class="trend-item__ticker">${t.ticker}</span>
        <span class="trend-item__mentions">${formatNumber(t.mentions)}</span>
        <span class="trend-item__spark">+${Math.round(t.surge_pct)}%</span>
      </div>
    `).join('');
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
      const ticker = n.ticker || '';
      const change = n.change_pct;
      const changeCls = change > 0 ? 'is-up' : (change < 0 ? 'is-down' : '');
      const changeTxt = change != null ? formatChange(change) : '';
      const sentimentCls = n.sentiment > 0.1 ? 'is-up' : (n.sentiment < -0.1 ? 'is-down' : '');
      const sentimentVal = n.sentiment != null ? (n.sentiment > 0 ? '+' : '') + n.sentiment.toFixed(2) : null;

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

      return `
        <article class="${cardClasses.join(' ')}" data-id="${n.id || ''}">
          <div class="news-card__header">
            ${categoryBadge}
            ${ticker ? `<span class="news-card__ticker">${ticker}</span>` : ''}
            ${changeTxt ? `<span class="news-card__change ${changeCls}">${changeTxt}</span>` : ''}
            <span class="news-card__meta">${n.source || ''} · ${formatRelativeTime(n.published_at)}</span>
          </div>
          <h3 class="news-card__title">${escapeHTML(n.title)}</h3>
          ${n.title_kr ? `<p class="news-card__title-kr">${escapeHTML(n.title_kr)}</p>` : ''}
          <div class="news-card__footer">
            ${sentimentVal
              ? `<span class="news-card__sentiment">Sentiment <span class="news-card__sentiment-value ${sentimentCls}">${sentimentVal}</span></span>`
              : ''}
            ${n.extra_meta ? `<span class="news-card__footer-sep">·</span><span>${n.extra_meta}</span>` : ''}
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
    const item = state.feed.find(n => n.id === id);
    if (!item) return;
    el.detailBody.innerHTML = `
      <h3>${escapeHTML(item.title)}</h3>
      ${item.title_kr ? `<p style="color: var(--fg-primary);">${escapeHTML(item.title_kr)}</p>` : ''}
      <p style="font-size: 11px; color: var(--fg-tertiary); text-transform: uppercase; letter-spacing: 0.05em;">
        ${item.source || 'Source'} · ${formatRelativeTime(item.published_at)}
      </p>
      ${item.summary ? `<p>${escapeHTML(item.summary)}</p>` : ''}
      ${item.summary_kr ? `<p style="border-left: 3px solid var(--border-default); padding-left: 12px; color: var(--fg-secondary);">${escapeHTML(item.summary_kr)}</p>` : ''}
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
    state.filtered = state.feed.filter(n => {
      if (f !== 'all') {
        const cat = (n.category || '').toLowerCase();
        if (f === 'ma') { if (!['ma', 'm&a', 'merger'].includes(cat)) return false; }
        else if (cat !== f) return false;
      }
      if (q && !(n.ticker || '').toUpperCase().includes(q)) return false;
      return true;
    });
    renderFeed();
  }

  // -------- Fetching --------
  async function fetchData() {
    try {
      const [feedRes, marketRes] = await Promise.all([
        fetch(FEED_URL + '?t=' + Date.now()).then(r => r.ok ? r.json() : null),
        fetch(MARKET_URL + '?t=' + Date.now()).then(r => r.ok ? r.json() : null),
      ]);
      if (feedRes?.items) state.feed = feedRes.items;
      if (marketRes) state.market = marketRes;
      state.lastFetchedAt = new Date();
      el.lastUpdate.textContent = 'Updated ' + formatRelativeTime(state.lastFetchedAt.toISOString());
      renderStatusBar();
      renderWatchlist();
      renderTrending();
      renderMoodPanel();
      applyFilters();
    } catch (err) {
      console.error('Fetch failed:', err);
    }
  }

  // -------- Events --------
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
    if (!('Notification' in window)) {
      alert('이 브라우저는 알림을 지원하지 않아요.');
      return;
    }
    if (Notification.permission === 'granted') {
      alert('알림이 이미 켜져 있어요.');
      return;
    }
    const res = await Notification.requestPermission();
    if (res === 'granted') {
      new Notification('알림 활성화 완료', { body: '중요 뉴스가 오면 알려드릴게요.' });
    }
  });

  // Initialize theme from localStorage
  try {
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch {}

  // Initial load
  updateClock();
  setInterval(updateClock, 1000);
  fetchData();
  setInterval(fetchData, AUTO_REFRESH_MS);

})();
