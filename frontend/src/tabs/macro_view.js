import { fetchWithAuth } from '../state.js?v=30';

export class MacroView {
  constructor() {
    this.container = null;
    this.currentEvents = [];
    this.activeFilter = 'ALL'; // 'ALL' | 'USD' | 'EUR' | 'GBP' | 'JPY' | 'HIGH'
    this.isLoading = false;
    this.pollInterval = null;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="macro-view-container">
        <!-- Top Controls Header -->
        <div class="macro-header-bar">
          <div class="macro-title-group">
            <span class="macro-badge-icon">🌐</span>
            <h1 class="macro-title">Macroeconomic Events</h1>
            <span class="macro-session-tag">
              <span class="status-dot dot-live"></span>
              <span class="tag-text" id="macroEventCountTag">0 EVENTS</span>
            </span>
          </div>

          <div class="macro-controls-group">
            <button type="button" class="macro-refresh-btn" id="macroRefreshBtn" title="Refresh Economic Calendar">↻</button>
          </div>
        </div>

        <div id="macro-sensitivity-ribbon"></div>

        <!-- Filter Chips Bar -->
        <div class="macro-filter-bar">
          <button type="button" class="macro-filter-chip active" data-filter="ALL">All Currencies</button>
          <button type="button" class="macro-filter-chip" data-filter="USD">🇺🇸 USD</button>
          <button type="button" class="macro-filter-chip" data-filter="EUR">🇪🇺 EUR</button>
          <button type="button" class="macro-filter-chip" data-filter="GBP">🇬🇧 GBP</button>
          <button type="button" class="macro-filter-chip" data-filter="JPY">🇯🇵 JPY</button>
          <button type="button" class="macro-filter-chip filter-high" data-filter="HIGH">🔥 High Impact</button>
        </div>

        <!-- Event Cards Accordion Feed -->
        <div class="macro-events-feed" id="macroEventsFeed">
          <div class="macro-empty-state">Loading macroeconomic calendar...</div>
        </div>
      </div>
    `;

    this.bindEvents();
    this.loadEvents();
    this.loadData(window.currentSymbol || 'SPY');
    this.startPolling();
  }

  bindEvents() {
    const refreshBtn = this.container.querySelector('#macroRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => this.loadEvents(true));
    }

    const filterChips = this.container.querySelectorAll('.macro-filter-chip');
    filterChips.forEach(chip => {
      chip.addEventListener('click', (e) => {
        filterChips.forEach(c => c.classList.remove('active'));
        e.currentTarget.classList.add('active');
        this.activeFilter = e.currentTarget.getAttribute('data-filter') || 'ALL';
        this.renderEventCards();
      });
    });
  }

  startPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollInterval = setInterval(() => {
      this.loadEvents(false);
    }, 300000); // 5 minutes
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  async loadEvents(force = false) {
    if (this.isLoading) return;
    this.isLoading = true;

    const refreshBtn = this.container?.querySelector('#macroRefreshBtn');
    if (refreshBtn) refreshBtn.classList.add('spin');

    try {
      const resp = await fetchWithAuth('/api/economic-events?limit=100');
      if (resp && resp.ok) {
        const data = await resp.json();
        this.currentEvents = data.events || [];
        this.renderEventCards();
      } else {
        const feed = this.container?.querySelector('#macroEventsFeed');
        if (feed) feed.innerHTML = `<div class="macro-error-state">Failed to load economic calendar.</div>`;
      }
    } catch (err) {
      console.error('Error loading macro events:', err);
      const feed = this.container?.querySelector('#macroEventsFeed');
      if (feed) feed.innerHTML = `<div class="macro-error-state">Network error loading events.</div>`;
    } finally {
      this.isLoading = false;
      if (refreshBtn) refreshBtn.classList.remove('spin');
    }
  }

  async loadData(ticker) {
    if (!ticker) return;
    this.currentTicker = ticker;
    try {
      const resp = await fetchWithAuth(`/api/economic-events/macro?ticker=${ticker}`);
      let profile = null;
      if (resp && resp.ok) {
        const data = await resp.json();
        profile = data.sensitivity_profile;
      }
      
      if (!profile) {
        const fallback = await fetchWithAuth(`/api/economic-events/sensitivity?ticker=${ticker}`);
        if (fallback && fallback.ok) {
          const fallbackData = await fallback.json();
          profile = fallbackData.sensitivity_profile || fallbackData;
        }
      }
      
      this.renderSensitivityRibbon(profile, ticker);
    } catch (err) {
      console.error('Error loading macro sensitivity:', err);
      this.renderSensitivityRibbon(null, ticker);
    }
  }

  renderSensitivityRibbon(profile, ticker) {
    const container = this.container?.querySelector('#macro-sensitivity-ribbon');
    if (!container) return;

    if (!profile) {
      container.innerHTML = `
        <div class="macro-sensitivity-ribbon empty">
          <span class="ticker-badge">${ticker} MACRO PROFILE</span>
          <span class="sensitivity-placeholder">Calculating sensitivity profile...</span>
        </div>
      `;
      return;
    }

    const rateBeta = profile.beta_rates !== undefined ? profile.beta_rates : (profile.rate_beta || 0);
    const rateHigh = Math.abs(rateBeta) > 0.8 ? 'rate-high' : '';
    const solvency = profile.interest_coverage !== undefined && profile.interest_coverage !== null
      ? `${profile.interest_coverage}x`
      : (profile.debt_to_equity !== undefined && profile.debt_to_equity !== null ? `${profile.debt_to_equity} D/E` : 'N/A');
    const isSolvencyAlert = profile.interest_coverage !== undefined && profile.interest_coverage !== null && Number(profile.interest_coverage) < 2.5 ? 'solvency-alert' : '';
    const oilBeta = profile.beta_oil !== undefined ? profile.beta_oil : (profile.oil_beta || 0);
    
    const catalysts = profile.primary_catalysts || [];

    container.innerHTML = `
      <div class="macro-sensitivity-ribbon">
        <span class="ticker-badge">${ticker} MACRO PROFILE</span>
        <div class="sensitivity-pill ${rateHigh}">⚡ Rate Beta: ${rateBeta > 0 ? '+' : ''}${rateBeta}</div>
        <div class="sensitivity-pill ${isSolvencyAlert}">⚠️ Int Coverage: ${solvency}</div>
        <div class="sensitivity-pill energy">🛢️ Oil Beta: ${oilBeta > 0 ? '+' : ''}${oilBeta}</div>
        <div class="catalyst-tags">
          ${catalysts.map(c => `<button class="catalyst-chip" data-catalyst="${c}">[${c}]</button>`).join('')}
        </div>
      </div>
    `;

    const chips = container.querySelectorAll('.catalyst-chip');
    chips.forEach(chip => {
      chip.addEventListener('click', (e) => {
        const isActive = chip.classList.contains('active');
        chips.forEach(c => c.classList.remove('active'));
        if (!isActive) {
          chip.classList.add('active');
          this.activeFilter = `CATALYST:${chip.dataset.catalyst}`;
        } else {
          this.activeFilter = 'ALL';
        }
        this.renderEventCards();
      });
    });
  }

  getFilteredEvents() {
    if (this.activeFilter === 'ALL') return this.currentEvents;
    if (this.activeFilter.startsWith('CATALYST:')) {
      const cat = this.activeFilter.split(':')[1].toLowerCase();
      return this.currentEvents.filter(e => {
        const title = (e.title || '').toLowerCase();
        const summary = (e.synthetic_summary || '').toLowerCase();
        return title.includes(cat) || summary.includes(cat);
      });
    }
    if (this.activeFilter === 'HIGH') {
      return this.currentEvents.filter(e => (e.impact_tier || '').toLowerCase() === 'high');
    }
    return this.currentEvents.filter(e => (e.country || '').toUpperCase() === this.activeFilter);
  }

  formatCountdown(timestampStr) {
    if (!timestampStr) return 'UPCOMING';
    const eventTime = new Date(timestampStr).getTime();
    const now = Date.now();
    const diffMs = eventTime - now;

    if (diffMs <= 0) return 'RELEASED';

    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) return `in ${diffDays}d ${diffHours % 24}h`;
    if (diffHours > 0) return `in ${diffHours}h`;
    const diffMins = Math.floor(diffMs / (1000 * 60));
    return `in ${diffMins}m`;
  }

  getCountryFlag(country) {
    const map = {
      USD: '🇺🇸',
      EUR: '🇪🇺',
      GBP: '🇬🇧',
      JPY: '🇯🇵',
      CAD: '🇨🇦',
      AUD: '🇦🇺',
      NZD: '🇳🇿',
      CHF: '🇨🇭',
      CNY: '🇨🇳',
      BRL: '🇧🇷'
    };
    return map[(country || '').toUpperCase()] || '🌐';
  }

  renderEventCards() {
    const feed = this.container?.querySelector('#macroEventsFeed');
    const countTag = this.container?.querySelector('#macroEventCountTag');
    if (!feed) return;

    const filtered = this.getFilteredEvents();
    if (countTag) countTag.textContent = `${filtered.length} EVENTS`;

    if (filtered.length === 0) {
      feed.innerHTML = `<div class="macro-empty-state">No events matching "${this.activeFilter}" filter.</div>`;
      return;
    }

    feed.innerHTML = '';
    filtered.forEach((ev, idx) => {
      const card = document.createElement('div');
      const tier = (ev.impact_tier || 'Low').toLowerCase();
      card.className = `macro-event-card tier-${tier}`;
      card.id = `macroCard_${ev.event_id || idx}`;

      const flag = this.getCountryFlag(ev.country);
      const countdown = this.formatCountdown(ev.event_timestamp);
      const isReleased = Boolean(ev.actual);
      const tsFormatted = ev.event_timestamp ? new Date(ev.event_timestamp).toUTCString().replace(':00 GMT', ' UTC') : '';

      card.innerHTML = `
        <div class="macro-card-header">
          <div class="macro-card-left">
            <span class="macro-flag">${flag}</span>
            <div class="macro-info-col">
              <span class="macro-card-title">${ev.title || 'Untitled Event'}</span>
              <span class="macro-card-ts">${tsFormatted}</span>
            </div>
          </div>
          <div class="macro-card-right">
            <span class="macro-tier-badge tier-${tier}">${ev.impact_tier || 'Low'}</span>
            <span class="macro-countdown-badge ${isReleased ? 'badge-released' : ''}">${countdown}</span>
          </div>
        </div>

        <div class="macro-card-metrics">
          <div class="metric-pill">
            <span class="metric-label">FORECAST</span>
            <span class="metric-val">${ev.forecast || '--'}</span>
          </div>
          <div class="metric-pill">
            <span class="metric-label">PREVIOUS</span>
            <span class="metric-val">${ev.previous || '--'}</span>
          </div>
          <div class="metric-pill">
            <span class="metric-label">ACTUAL</span>
            <span class="metric-val ${isReleased ? 'val-highlight' : ''}">${ev.actual || 'PENDING'}</span>
          </div>
        </div>

        <div class="macro-card-body">
          <div class="macro-summary-text">${ev.synthetic_summary || 'No summary available.'}</div>
        </div>
      `;

      // Toggle accordion expansion on card header click
      card.querySelector('.macro-card-header').addEventListener('click', () => {
        card.classList.toggle('expanded');
      });

      feed.appendChild(card);
    });
  }
}
