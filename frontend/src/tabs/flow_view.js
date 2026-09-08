import { fetchWithAuth } from '../state.js?v=30';

export class FlowView {
  constructor() {
    this.container = null;
    this.currentData = null;
    this.activeDuration = '3d'; // '3d' | '7d'
    this.isLoading = false;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="flow-view-container">
        <!-- Top Controls & Session Header Bar -->
        <div class="flow-header-bar">
          <div class="flow-title-group">
            <span class="flow-badge-icon">🌊</span>
            <h1 class="flow-title">Options Flow Aggregate</h1>
            <span class="flow-session-tag" id="flowSessionTag">
              <span class="status-dot dot-live"></span>
              <span class="tag-text" id="flowSessionText">LOADING SESSIONS...</span>
            </span>
          </div>

          <div class="flow-controls-group">
            <div class="flow-duration-toggle" id="flowDurationToggle">
              <button type="button" class="flow-duration-btn active" data-duration="3d">3 Days</button>
              <button type="button" class="flow-duration-btn" data-duration="7d">7 Days</button>
            </div>
            <button type="button" class="flow-refresh-btn" id="flowRefreshBtn" title="Reload Flow Aggregates">↻</button>
          </div>
        </div>

        <!-- Info Ribbon with Included Dates & Drill-Down Hint -->
        <div class="flow-info-ribbon">
          <span>📅 Sessions: <strong class="flow-info-dates" id="flowDatesText">Resolving market days...</strong></span>
          <span>💡 Click any ticker to inspect in Cockpit ↗</span>
        </div>

        <!-- 3 Primary Ranking Sections Grid -->
        <div class="flow-sections-grid" id="flowSectionsGrid">
          
          <!-- Section 1: Top Bullish by Premium Spent -->
          <div class="flow-card card-premium" id="cardTopPremium">
            <div class="flow-card-header">
              <div class="flow-card-title-group">
                <span class="flow-card-icon">💰</span>
                <h3 class="flow-card-title">Top Bullish Premium</h3>
              </div>
              <span class="flow-card-badge badge-gold">TOP 5</span>
            </div>
            <div class="flow-card-subtitle">Top 5 bullish symbols by dollar premium spent on calls & put-sales</div>
            <div class="flow-table-wrapper">
              <table class="flow-table">
                <thead>
                  <tr>
                    <th style="width: 40px;">#</th>
                    <th>TICKER</th>
                    <th>PREMIUM SPENT</th>
                    <th>HITS</th>
                    <th>DAYS</th>
                  </tr>
                </thead>
                <tbody id="flowBodyPremium">
                  <tr><td colspan="5" class="flow-empty-state">Loading premium flow...</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Section 2: Top Bullish by Contract Hits -->
          <div class="flow-card card-bullish" id="cardTopBullish">
            <div class="flow-card-header">
              <div class="flow-card-title-group">
                <span class="flow-card-icon">🐂</span>
                <h3 class="flow-card-title">Top Bullish Contracts</h3>
              </div>
              <span class="flow-card-badge badge-green">TOP 5</span>
            </div>
            <div class="flow-card-subtitle">Top 5 bullish symbols by frequency of bullish sweeps & blocks</div>
            <div class="flow-table-wrapper">
              <table class="flow-table">
                <thead>
                  <tr>
                    <th style="width: 40px;">#</th>
                    <th>TICKER</th>
                    <th>BULLISH HITS</th>
                    <th>PREMIUM</th>
                    <th>DAYS</th>
                  </tr>
                </thead>
                <tbody id="flowBodyBullish">
                  <tr><td colspan="5" class="flow-empty-state">Loading bullish contracts...</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Section 3: Top Bearish by Contract Hits -->
          <div class="flow-card card-bearish" id="cardTopBearish">
            <div class="flow-card-header">
              <div class="flow-card-title-group">
                <span class="flow-card-icon">🐻</span>
                <h3 class="flow-card-title">Top Bearish Contracts</h3>
              </div>
              <span class="flow-card-badge badge-red">TOP 5</span>
            </div>
            <div class="flow-card-subtitle">Top 5 bearish symbols by frequency of bearish sweeps & blocks</div>
            <div class="flow-table-wrapper">
              <table class="flow-table">
                <thead>
                  <tr>
                    <th style="width: 40px;">#</th>
                    <th>TICKER</th>
                    <th>BEARISH HITS</th>
                    <th>PREMIUM</th>
                    <th>DAYS</th>
                  </tr>
                </thead>
                <tbody id="flowBodyBearish">
                  <tr><td colspan="5" class="flow-empty-state">Loading bearish contracts...</td></tr>
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div>
    `;

    this.bindEvents();
    this.loadFlowData();
  }

  bindEvents() {
    if (!this.container) return;

    // Duration Switcher (3D vs 7D)
    const toggleBtns = this.container.querySelectorAll('#flowDurationToggle .flow-duration-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activeDuration = btn.dataset.duration || '3d';
        this.renderActiveTables();
      });
    });

    // Refresh Button
    const refreshBtn = this.container.querySelector('#flowRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.loadFlowData();
      });
    }

    // Row Click Delegation for Cockpit Drill-Down
    const grid = this.container.querySelector('#flowSectionsGrid');
    if (grid) {
      grid.addEventListener('click', (e) => {
        const tr = e.target.closest ? e.target.closest('tr[data-ticker]') : null;
        if (tr && tr.dataset.ticker) {
          this.drillDownToCockpit(tr.dataset.ticker);
        }
      });
    }
  }

  async loadFlowData() {
    if (this.isLoading) return;
    this.isLoading = true;

    try {
      const res = await fetchWithAuth('/api/flow/aggregate');
      if (res && res.ok) {
        const data = await res.json();
        this.currentData = data;
        this.renderSessionHeader();
        this.renderActiveTables();
      } else {
        throw new Error(`Server returned HTTP ${res?.status || 500}`);
      }
    } catch (e) {
      console.error('Failed to load options flow aggregates:', e);
      this.renderErrorState();
    } finally {
      this.isLoading = false;
    }
  }

  renderSessionHeader() {
    if (!this.container || !this.currentData) return;
    const sessionText = this.container.querySelector('#flowSessionText');
    if (sessionText) {
      const asOf = this.currentData.as_of_date || this.currentData.latest_market_day || 'CURRENT';
      sessionText.textContent = `AS OF ${asOf}`;
    }
  }

  renderActiveTables() {
    if (!this.container || !this.currentData) return;

    const windowKey = this.activeDuration === '7d' ? 'window_7d' : 'window_3d';
    const windowData = this.currentData[windowKey] || {
      market_dates: [],
      top_premium_bullish: [],
      top_hits_bullish: [],
      top_hits_bearish: []
    };

    // Update Dates text in info ribbon
    const datesText = this.container.querySelector('#flowDatesText');
    if (datesText) {
      const mDates = windowData.market_dates || [];
      datesText.textContent = mDates.length > 0 ? mDates.join(', ') : 'None';
    }

    // Render Table 1: Top Bullish Premium
    const bodyPremium = this.container.querySelector('#flowBodyPremium');
    if (bodyPremium) {
      const rows = windowData.top_premium_bullish || [];
      if (rows.length === 0) {
        bodyPremium.innerHTML = `<tr><td colspan="5" class="flow-empty-state">No qualifying bullish premium prints found.</td></tr>`;
      } else {
        bodyPremium.innerHTML = rows.map(r => `
          <tr data-ticker="${r.symbol}" title="Open ${r.symbol} in Cockpit">
            <td><span class="flow-rank-pill flow-rank-${r.rank}">${r.rank}</span></td>
            <td><span class="flow-ticker-btn">${r.symbol}</span></td>
            <td><strong class="flow-metric-primary metric-gold">${r.formatted_premium}</strong></td>
            <td><span class="flow-metric-secondary">${r.contract_count} prints</span></td>
            <td><span class="flow-days-pill">${r.active_days}d</span></td>
          </tr>
        `).join('');
      }
    }

    // Render Table 2: Top Bullish Hits
    const bodyBullish = this.container.querySelector('#flowBodyBullish');
    if (bodyBullish) {
      const rows = windowData.top_hits_bullish || [];
      if (rows.length === 0) {
        bodyBullish.innerHTML = `<tr><td colspan="5" class="flow-empty-state">No qualifying bullish hits found.</td></tr>`;
      } else {
        bodyBullish.innerHTML = rows.map(r => `
          <tr data-ticker="${r.symbol}" title="Open ${r.symbol} in Cockpit">
            <td><span class="flow-rank-pill flow-rank-${r.rank}">${r.rank}</span></td>
            <td><span class="flow-ticker-btn">${r.symbol}</span></td>
            <td><strong class="flow-metric-primary metric-green">${r.contract_count} prints</strong></td>
            <td><span class="flow-metric-secondary">${r.formatted_premium}</span></td>
            <td><span class="flow-days-pill">${r.active_days}d</span></td>
          </tr>
        `).join('');
      }
    }

    // Render Table 3: Top Bearish Hits
    const bodyBearish = this.container.querySelector('#flowBodyBearish');
    if (bodyBearish) {
      const rows = windowData.top_hits_bearish || [];
      if (rows.length === 0) {
        bodyBearish.innerHTML = `<tr><td colspan="5" class="flow-empty-state">No qualifying bearish hits found.</td></tr>`;
      } else {
        bodyBearish.innerHTML = rows.map(r => `
          <tr data-ticker="${r.symbol}" title="Open ${r.symbol} in Cockpit">
            <td><span class="flow-rank-pill flow-rank-${r.rank}">${r.rank}</span></td>
            <td><span class="flow-ticker-btn">${r.symbol}</span></td>
            <td><strong class="flow-metric-primary metric-red">${r.contract_count} prints</strong></td>
            <td><span class="flow-metric-secondary">${r.formatted_premium}</span></td>
            <td><span class="flow-days-pill">${r.active_days}d</span></td>
          </tr>
        `).join('');
      }
    }
  }

  renderErrorState() {
    if (!this.container) return;
    for (const id of ['#flowBodyPremium', '#flowBodyBullish', '#flowBodyBearish']) {
      const el = this.container.querySelector(id);
      if (el) {
        el.innerHTML = `<tr><td colspan="5" class="flow-empty-state error">Failed to load options flow aggregates.</td></tr>`;
      }
    }
  }

  drillDownToCockpit(ticker) {
    if (!ticker) return;
    if (typeof window !== 'undefined' && window.quantApp) {
      if (window.quantApp.tabManager) {
        window.quantApp.tabManager.switchTab('cockpit');
      }
      if (window.quantApp.cockpitView && typeof window.quantApp.cockpitView.searchTicker === 'function') {
        const input = document.querySelector('#cockpitSearchInput');
        if (input) input.value = ticker;
        window.quantApp.cockpitView.searchTicker(ticker);
      }
    }
  }
}
