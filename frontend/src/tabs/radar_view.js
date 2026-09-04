import { fetchWithAuth } from '../state.js';

export class RadarView {
  constructor() {
    this.container = null;
    this.currentData = null;
    this.activeFilter = 'all';
    this.sortColumn = 'confluence_score';
    this.sortDirection = 'desc'; // 'desc' | 'asc' | 'natural'
    this.selectedDate = null;
    this.availableDates = [];
    this.isLoading = false;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="radar-view-container">
        <!-- Top Session & Control Bar -->
        <div class="radar-header-bar">
          <div class="radar-title-group">
            <span class="radar-badge-icon">📡</span>
            <h1 class="radar-title">Confluence Radar</h1>
            <span class="radar-session-tag" id="radarSessionTag">
              <span class="status-dot dot-live"></span>
              <span class="tag-text" id="radarSessionText">LOADING EOD SCAN...</span>
            </span>
          </div>

          <div class="radar-date-control">
            <label for="radarDateSelect" class="date-label">SESSION DATE:</label>
            <select id="radarDateSelect" class="radar-date-select">
              <option value="">Latest Session</option>
            </select>
            <button type="button" class="radar-refresh-btn" id="radarRefreshBtn" title="Reload Scan">↻</button>
          </div>
        </div>

        <!-- 4 Summary Metric Cards (Zero Derivation) -->
        <div class="radar-metric-cards" id="radarMetricCards">
          <div class="radar-card" id="cardTotalScanned">
            <span class="card-label">TOTAL SCANNED</span>
            <strong class="card-val" id="valTotalScanned">--</strong>
            <span class="card-sub">Institutional Flow Tickers</span>
          </div>
          <div class="radar-card" id="cardConfirmedSetups">
            <span class="card-label">CONFIRMED SETUPS</span>
            <strong class="card-val text-bull" id="valConfirmedSetups">--</strong>
            <span class="card-sub" id="subConfirmedSetups">Bull / Bear Confluence</span>
          </div>
          <div class="radar-card" id="cardTopWhale">
            <span class="card-label">TOP WHALE VOLUME</span>
            <strong class="card-val text-cyan" id="valTopWhale">--</strong>
            <span class="card-sub" id="subTopWhale">Largest Single Sweep</span>
          </div>
          <div class="radar-card" id="cardMarketRegime">
            <span class="card-label">MARKET REGIME</span>
            <strong class="card-val" id="valMarketRegime">--</strong>
            <span class="card-sub">Dominant Structural Bias</span>
          </div>
        </div>

        <!-- Filter Chips Bar -->
        <div class="radar-filter-bar">
          <div class="radar-filter-chips" id="radarFilterChips">
            <button type="button" class="radar-chip active" data-filter="all">All Setups</button>
            <button type="button" class="radar-chip" data-filter="CONFIRMED_BULL">Confirmed Bull</button>
            <button type="button" class="radar-chip" data-filter="CONFIRMED_BEAR">Confirmed Bear</button>
            <button type="button" class="radar-chip" data-filter="VOL_PIN">Volatility Pin</button>
            <button type="button" class="radar-chip" data-filter="STRUCTURAL_HEDGE">Structural Hedge</button>
            <button type="button" class="radar-chip" data-filter="whales">Whales &gt;$1M Only 🐳</button>
          </div>
          <div class="radar-count-badge" id="radarCountBadge">0 TICKERS</div>
        </div>

        <!-- Leaderboard Table Container -->
        <div class="radar-table-card">
          <div class="radar-table-wrapper" id="radarTableWrapper">
            <table class="radar-table" id="radarTable">
              <thead>
                <tr>
                  <th class="col-ticker" data-col="ticker">TICKER</th>
                  <th class="col-spot" data-col="spot_price">SPOT</th>
                  <th class="col-flow" data-col="total_flow_premium">FLOW ($)</th>
                  <th class="col-callpct" data-col="call_premium_pct">CALL %</th>
                  <th class="col-bias" data-col="flow_bias">FLOW BIAS</th>
                  <th class="col-regime" data-col="gamma_regime">GEX REGIME</th>
                  <th class="col-netgex" data-col="net_gex">NET GEX</th>
                  <th class="col-walls" data-col="wall_spread_range">WALL SPREAD</th>
                  <th class="col-status" data-col="confluence_status">STATUS</th>
                  <th class="col-score sort-desc" data-col="confluence_score">SCORE</th>
                </tr>
              </thead>
              <tbody id="radarTableBody">
                <tr>
                  <td colspan="10" class="radar-empty-state">Loading confluence radar data...</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    this.loadAvailableDates();
    this.loadScanData();
  }

  bindEvents() {
    if (!this.container) return;

    // Date selector change
    const dateSelect = this.container.querySelector('#radarDateSelect');
    if (dateSelect) {
      dateSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        this.selectedDate = val || null;
        this.loadScanData(this.selectedDate);
      });
    }

    // Refresh button
    const refreshBtn = this.container.querySelector('#radarRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.loadScanData(this.selectedDate);
      });
    }

    // Filter chips
    const chips = this.container.querySelectorAll('.radar-chip');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.activeFilter = chip.dataset.filter || 'all';
        this.renderTableRows();
      });
    });

    // Table Header Sorting (Tri-state)
    const ths = this.container.querySelectorAll('#radarTable th[data-col]');
    ths.forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (this.sortColumn === col) {
          if (this.sortDirection === 'desc') this.sortDirection = 'asc';
          else if (this.sortDirection === 'asc') this.sortDirection = 'natural';
          else this.sortDirection = 'desc';
        } else {
          this.sortColumn = col;
          this.sortDirection = 'desc';
        }
        this.updateHeaderSortClasses();
        this.renderTableRows();
      });
    });

    // Click on row to drill down into Cockpit
    const tbody = this.container.querySelector('#radarTableBody');
    if (tbody) {
      tbody.addEventListener('click', (e) => {
        const tr = e.target.closest ? e.target.closest('tr[data-ticker]') : null;
        if (tr && tr.dataset.ticker) {
          const sym = tr.dataset.ticker;
          this.drillDownToCockpit(sym);
        }
      });
    }
  }

  updateHeaderSortClasses() {
    const ths = this.container?.querySelectorAll('#radarTable th[data-col]');
    if (!ths) return;
    ths.forEach(th => {
      th.classList.remove('sort-desc', 'sort-asc');
      if (th.dataset.col === this.sortColumn && this.sortDirection !== 'natural') {
        th.classList.add(`sort-${this.sortDirection}`);
      }
    });
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

  async loadAvailableDates() {
    try {
      const dates = await fetchWithAuth('/api/scanner/dates');
      if (Array.isArray(dates)) {
        this.availableDates = dates;
        const select = this.container?.querySelector('#radarDateSelect');
        if (select) {
          select.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');
          if (dates.length > 0 && !this.selectedDate) {
            this.selectedDate = dates[0];
            select.value = dates[0];
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load scanner dates:', e);
    }
  }

  async loadScanData(dateParam = null) {
    if (this.isLoading) return;
    this.isLoading = true;

    const url = dateParam ? `/api/scanner/by-date?date=${encodeURIComponent(dateParam)}` : '/api/scanner/latest';
    try {
      const data = await fetchWithAuth(url);
      this.currentData = data || { summary: None, rows: [] };
      this.renderSummaryCards();
      this.renderTableRows();
    } catch (e) {
      console.error('Error fetching confluence scan data:', e);
      const tbody = this.container?.querySelector('#radarTableBody');
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="10" class="radar-empty-state error">Failed to load confluence scan. Ensure database is connected.</td></tr>`;
      }
    } finally {
      this.isLoading = false;
    }
  }

  renderSummaryCards() {
    if (!this.container || !this.currentData) return;
    const s = this.currentData.summary;

    const sessionText = this.container.querySelector('#radarSessionText');
    const valTotal = this.container.querySelector('#valTotalScanned');
    const valConfirmed = this.container.querySelector('#valConfirmedSetups');
    const subConfirmed = this.container.querySelector('#subConfirmedSetups');
    const valWhale = this.container.querySelector('#valTopWhale');
    const subWhale = this.container.querySelector('#subTopWhale');
    const valRegime = this.container.querySelector('#valMarketRegime');

    if (!s) {
      if (sessionText) sessionText.textContent = 'NO ACTIVE EOD SCAN';
      if (valTotal) valTotal.textContent = '0';
      if (valConfirmed) valConfirmed.textContent = '--';
      if (valWhale) valWhale.textContent = '--';
      if (valRegime) valRegime.textContent = 'NEUTRAL';
      return;
    }

    if (sessionText) sessionText.textContent = s.session_label || `EOD Scan (${s.scan_date})`;
    if (valTotal) valTotal.textContent = String(s.total_scanned_count || 0);

    const bull = s.confirmed_bull_count || 0;
    const bear = s.confirmed_bear_count || 0;
    if (valConfirmed) {
      valConfirmed.textContent = `${bull} Bull / ${bear} Bear`;
      valConfirmed.className = `card-val ${bull >= bear ? 'text-bull' : 'text-bear'}`;
    }
    if (subConfirmed) {
      subConfirmed.textContent = `${s.vol_pin_count || 0} Vol Pin | ${s.divergent_count || 0} Divergent`;
    }

    if (valWhale) {
      valWhale.textContent = s.top_whale_ticker ? `${s.top_whale_ticker} (${s.formatted_top_whale_premium})` : 'None';
    }
    if (subWhale) {
      subWhale.textContent = 'Top Institutional Whale Sweep';
    }

    if (valRegime) {
      valRegime.textContent = s.market_regime_summary || 'BALANCED FLOW REGIME';
    }
  }

  renderTableRows() {
    const tbody = this.container?.querySelector('#radarTableBody');
    const badge = this.container?.querySelector('#radarCountBadge');
    if (!tbody || !this.currentData) return;

    let rows = Array.isArray(this.currentData.rows) ? [...this.currentData.rows] : [];

    // Filter
    if (this.activeFilter === 'whales') {
      rows = rows.filter(r => (r.whale_prints_count || 0) > 0);
    } else if (this.activeFilter !== 'all') {
      rows = rows.filter(r => r.confluence_status === this.activeFilter);
    }

    if (badge) {
      badge.textContent = `${rows.length} TICKERS`;
    }

    // Sort
    if (this.sortDirection !== 'natural') {
      const col = this.sortColumn;
      const asc = this.sortDirection === 'asc';
      rows.sort((a, b) => {
        let va = a[col];
        let vb = b[col];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      });
    }

    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="radar-empty-state">No matching setups found for the selected filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const biasClass = r.flow_bias === 'BULLISH' ? 'bias-bull' : (r.flow_bias === 'BEARISH' ? 'bias-bear' : 'bias-neutral');
      const statusClass = (r.confluence_status || '').toLowerCase().replace('_', '-');
      const whaleTag = (r.whale_prints_count || 0) > 0 ? `<span class="whale-indicator" title="${r.whale_prints_count} Whale Sweeps">🐳 ${r.whale_prints_count}</span>` : '';
      const spotVsFlipStr = r.spot_vs_flip_pct !== null && r.spot_vs_flip_pct !== undefined ? `<span class="flip-dist">${r.spot_vs_flip_pct > 0 ? '+' : ''}${r.spot_vs_flip_pct}% vs Flip</span>` : '';

      return `
        <tr data-ticker="${r.ticker}" class="radar-row clickable" title="Click to view ${r.ticker} in Cockpit">
          <td class="col-ticker">
            <span class="ticker-pill">${r.ticker}</span>
            ${whaleTag}
          </td>
          <td class="col-spot">
            <strong>${r.formatted_spot_price || '$0.00'}</strong>
            ${spotVsFlipStr}
          </td>
          <td class="col-flow">${r.formatted_flow_premium || '$0.00'}</td>
          <td class="col-callpct">${r.call_premium_pct !== undefined ? r.call_premium_pct + '%' : '--'}</td>
          <td class="col-bias"><span class="badge ${biasClass}">${r.flow_bias || 'NEUTRAL'}</span></td>
          <td class="col-regime"><span class="regime-text">${r.gamma_regime || 'N/A'}</span></td>
          <td class="col-netgex"><strong>${r.formatted_net_gex || '$0.00'}</strong></td>
          <td class="col-walls">${r.wall_spread_range || 'N/A'}</td>
          <td class="col-status"><span class="status-pill ${statusClass}">${r.confluence_status}</span></td>
          <td class="col-score"><strong class="score-badge">${r.confluence_score}</strong></td>
        </tr>
      `;
    }).join('');
  }
}
