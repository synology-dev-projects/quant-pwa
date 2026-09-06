import { fetchWithAuth } from '../state.js';

export class RadarView {
  constructor() {
    this.container = null;
    this.currentData = null;
    this.activeFilter = 'all';
    this.sortColumn = 'rank';
    this.sortDirection = 'asc'; // 'asc' | 'desc' | 'natural'
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
            <span class="radar-badge-icon">🎯</span>
            <h1 class="radar-title">Asymmetric Options Radar</h1>
            <span class="radar-session-tag" id="radarSessionTag">
              <span class="status-dot dot-live"></span>
              <span class="tag-text" id="radarSessionText">LOADING SCAN...</span>
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
            <span class="card-label">WATCHLIST SCANNED</span>
            <strong class="card-val" id="valTotalScanned">--</strong>
            <span class="card-sub">Top Liquidity Watchlist</span>
          </div>
          <div class="radar-card" id="cardConfirmedSetups">
            <span class="card-label">QUALIFYING PLAYS</span>
            <strong class="card-val text-bull" id="valConfirmedSetups">--</strong>
            <span class="card-sub" id="subConfirmedSetups">Meeting &ge;80% Imbalance</span>
          </div>
          <div class="radar-card" id="cardTopWhale">
            <span class="card-label">TOP OPPORTUNITY</span>
            <strong class="card-val text-cyan" id="valTopWhale">--</strong>
            <span class="card-sub" id="subTopWhale">Highest Viability Play</span>
          </div>
          <div class="radar-card" id="cardMarketRegime">
            <span class="card-label">NEAREST PIN CATALYST</span>
            <strong class="card-val" id="valMarketRegime">--</strong>
            <span class="card-sub" id="subMarketRegime">Dominant Expiration Pin</span>
          </div>
        </div>

        <!-- Filter Chips Bar -->
        <div class="radar-filter-bar">
          <div class="radar-filter-chips" id="radarFilterChips">
            <button type="button" class="radar-chip active" data-filter="all">All Top 10</button>
            <button type="button" class="radar-chip" data-filter="BULL_SPRING">Bull Springs (Spot &lt; 80%)</button>
            <button type="button" class="radar-chip" data-filter="BEAR_EXHAUSTION">Bear Exhaustions (Spot &gt; 80%)</button>
          </div>
          <div class="radar-count-badge" id="radarCountBadge">0 PLAYS</div>
        </div>

        <!-- Leaderboard Table Container -->
        <div class="radar-table-card">
          <div class="radar-table-wrapper" id="radarTableWrapper">
            <table class="radar-table" id="radarTable">
              <thead>
                <tr>
                  <th class="col-rank sort-asc" data-col="rank">RANK</th>
                  <th class="col-ticker" data-col="ticker">TICKER</th>
                  <th class="col-spot" data-col="spot_price">SPOT</th>
                  <th class="col-play" data-col="play_type">PLAY TYPE</th>
                  <th class="col-imbalance" data-col="exposure_imbalance_pct">EXPOSURE IMBALANCE</th>
                  <th class="col-pin" data-col="pin_wall_strike">PINNING NODE</th>
                  <th class="col-flowacc" data-col="flow_call_put_ratio">FLOW ACCUMULATION</th>
                  <th class="col-score" data-col="viability_score">VIABILITY SCORE</th>
                </tr>
              </thead>
              <tbody id="radarTableBody">
                <tr>
                  <td colspan="8" class="radar-empty-state">Loading asymmetric options radar data...</td>
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
          if (this.sortDirection === 'asc') this.sortDirection = 'desc';
          else if (this.sortDirection === 'desc') this.sortDirection = 'natural';
          else this.sortDirection = 'asc';
        } else {
          this.sortColumn = col;
          this.sortDirection = 'asc';
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
      const res = await fetchWithAuth('/api/scanner/dates');
      if (res && res.ok) {
        const dates = await res.json();
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
      const res = await fetchWithAuth(url);
      if (res && res.ok) {
        const data = await res.json();
        this.currentData = data || { summary: null, rows: [] };
        this.renderSummaryCards();
        this.renderTableRows();
      } else {
        throw new Error(`Server returned HTTP ${res?.status || 500}`);
      }
    } catch (e) {
      console.error('Error fetching confluence scan data:', e);
      const tbody = this.container?.querySelector('#radarTableBody');
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="radar-empty-state error">Failed to load confluence scan. Ensure database is connected.</td></tr>`;
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
    const subRegime = this.container.querySelector('#subMarketRegime');

    if (!s) {
      if (sessionText) sessionText.textContent = 'NO ACTIVE EOD SCAN';
      if (valTotal) valTotal.textContent = '0';
      if (valConfirmed) valConfirmed.textContent = '--';
      if (valWhale) valWhale.textContent = '--';
      if (valRegime) valRegime.textContent = 'NEUTRAL';
      return;
    }

    if (sessionText) sessionText.textContent = s.session_label || `EOD Scan (${s.scan_date})`;
    if (valTotal) valTotal.textContent = String(s.total_watchlist_count || s.total_scanned_count || 0);

    const bull = s.qualifying_bull_spring_count ?? s.confirmed_bull_count ?? 0;
    const bear = s.qualifying_bear_exhaustion_count ?? s.confirmed_bear_count ?? 0;
    if (valConfirmed) {
      valConfirmed.textContent = `${bull} Bull / ${bear} Bear`;
      valConfirmed.className = `card-val ${bull >= bear ? 'text-bull' : 'text-bear'}`;
    }
    if (subConfirmed) {
      subConfirmed.textContent = 'Meeting ≥80% Imbalance';
    }

    // Top Opportunity (top ranked row or ticker from summary)
    const rows = this.currentData.rows || [];
    const topPlay = rows.length > 0 ? rows[0] : null;
    if (valWhale) {
      if (topPlay && (topPlay.viability_score || topPlay.confluence_score)) {
        valWhale.textContent = `${topPlay.ticker} (Score ${topPlay.viability_score || topPlay.confluence_score})`;
      } else if (s.top_whale_ticker && s.top_whale_ticker !== 'N/A') {
        valWhale.textContent = `${s.top_whale_ticker} (${s.formatted_top_whale_premium})`;
      } else {
        valWhale.textContent = 'None';
      }
    }
    if (subWhale) {
      subWhale.textContent = 'Highest Viability Play';
    }

    if (valRegime) {
      if (s.top_catalyst_ticker && s.top_catalyst_ticker !== 'None' && s.top_catalyst_ticker !== 'N/A') {
        valRegime.textContent = `${s.top_catalyst_ticker}: ${s.top_catalyst_expiry || ''}`;
      } else {
        valRegime.textContent = s.market_regime_summary || 'BALANCED ASYMMETRIC BIAS';
      }
    }
  }

  renderTableRows() {
    const tbody = this.container?.querySelector('#radarTableBody');
    const badge = this.container?.querySelector('#radarCountBadge');
    if (!tbody || !this.currentData) return;

    let rows = Array.isArray(this.currentData.rows) ? [...this.currentData.rows] : [];
    // Strict Zero-Noise filter: only show qualifying plays (ranked or valid play type)
    rows = rows.filter(r => r.rank != null || r.play_type != null || r.confluence_status === 'CONFIRMED_BULL' || r.confluence_status === 'CONFIRMED_BEAR');

    // Filter
    if (this.activeFilter === 'BULL_SPRING') {
      rows = rows.filter(r => r.play_type === 'BULL_SPRING' || r.confluence_status === 'BULL_SPRING' || r.confluence_status === 'CONFIRMED_BULL');
    } else if (this.activeFilter === 'BEAR_EXHAUSTION') {
      rows = rows.filter(r => r.play_type === 'BEAR_EXHAUSTION' || r.confluence_status === 'BEAR_EXHAUSTION' || r.confluence_status === 'CONFIRMED_BEAR');
    } else if (this.activeFilter === 'whales') {
      rows = rows.filter(r => (r.whale_prints_count || 0) > 0);
    } else if (this.activeFilter !== 'all') {
      rows = rows.filter(r => r.play_type === this.activeFilter || r.confluence_status === this.activeFilter);
    }

    if (badge) {
      badge.textContent = `${rows.length} PLAYS`;
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
        if (va === undefined || va === null) return 1;
        if (vb === undefined || vb === null) return -1;
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      });
    }

    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="radar-empty-state">No matching asymmetric plays found for the selected filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map((r, idx) => {
      const rankNum = r.rank || (idx + 1);
      const isSpring = r.play_type === 'BULL_SPRING' || r.confluence_status === 'BULL_SPRING';
      const isExhaust = r.play_type === 'BEAR_EXHAUSTION' || r.confluence_status === 'BEAR_EXHAUSTION';
      const playClass = isSpring ? 'badge-spring' : (isExhaust ? 'badge-exhaustion' : 'badge-neutral');
      const playLabel = isSpring ? 'BULL SPRING' : (isExhaust ? 'BEAR EXHAUST' : (r.play_type || r.confluence_status || 'N/A'));

      const dirLabel = isSpring ? 'Above' : (isExhaust ? 'Below' : '');
      const imbType = r.imbalance_type || 'GEX';
      const imbPct = r.exposure_imbalance_pct !== null && r.exposure_imbalance_pct !== undefined ? `${r.exposure_imbalance_pct}%` : '--';
      const imbText = `${imbPct} ${imbType} ${dirLabel}`.trim();

      const pinStrike = r.pin_wall_strike ? `$${r.pin_wall_strike.toFixed(2)}` : (r.call_wall ? `$${r.call_wall.toFixed(2)}` : '--');
      const pinType = (r.pin_wall_type || 'Wall').replace('_', ' ').toUpperCase();
      const dteText = r.pin_dte !== null && r.pin_dte !== undefined ? `${r.pin_dte} DTE` : '';
      const distText = r.pin_dist_pct !== null && r.pin_dist_pct !== undefined ? `${r.pin_dist_pct}%` : '';

      const ratioVal = r.flow_call_put_ratio !== null && r.flow_call_put_ratio !== undefined ? `${r.flow_call_put_ratio}x` : '--';
      const ratioType = isExhaust ? 'P/C' : 'C/P';
      const hitsCount = r.flow_hits_count || r.whale_prints_count || 0;
      const hitsText = hitsCount > 0 ? `${hitsCount} Prints` : '';

      const scoreVal = r.viability_score !== null && r.viability_score !== undefined ? r.viability_score : (r.confluence_score || '--');
      const isTopScore = typeof scoreVal === 'number' && scoreVal >= 85.0;

      return `
        <tr data-ticker="${r.ticker}" class="radar-row clickable" title="Click to view ${r.ticker} in Cockpit">
          <td class="col-rank">
            <span class="rank-badge rank-${rankNum <= 3 ? rankNum : 'other'}">#${rankNum}</span>
          </td>
          <td class="col-ticker">
            <span class="ticker-pill">${r.ticker}</span>
          </td>
          <td class="col-spot">
            <strong>${r.formatted_spot_price || (r.spot_price ? '$' + r.spot_price.toFixed(2) : '$0.00')}</strong>
          </td>
          <td class="col-play">
            <span class="play-badge ${playClass}">${playLabel}</span>
          </td>
          <td class="col-imbalance">
            <span class="imbalance-pill">${imbText}</span>
          </td>
          <td class="col-pin">
            <div class="pin-cell">
              <strong>${pinStrike} ${pinType}</strong>
              <span class="pin-meta">${dteText}${distText ? ' • ' + distText : ''}</span>
            </div>
          </td>
          <td class="col-flowacc">
            <div class="flow-cell">
              <strong>${ratioVal} ${ratioType}</strong>
              <span class="flow-meta">${hitsText}</span>
            </div>
          </td>
          <td class="col-score">
            <strong class="score-badge ${isTopScore ? 'score-high' : ''}">${scoreVal}</strong>
          </td>
        </tr>
      `;
    }).join('');
  }
}

