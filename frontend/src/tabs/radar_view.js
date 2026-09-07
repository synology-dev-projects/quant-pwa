import { fetchWithAuth } from '../state.js?v=30';
import { QuantChart } from '../components/quant_chart.js?v=30';

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

    // Inspector State
    this.selectedTicker = null;
    this.quantChartInstance = null;
    this.chartMode = 'both'; // 'both' | 'gex' | 'dex'
    this.flowFilter = 'all'; // 'all' | 'whales' | 'calls' | 'puts'
    this.currentFlowRecords = [];
    this.tickerDataCache = new Map();
    this.activeAbortController = null;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="radar-view-container">
        <!-- Top Session & Control Bar -->
        <div class="radar-header-bar">
          <div class="radar-title-group">
            <span class="radar-badge-icon">🎯</span>
            <h1 class="radar-title">Top 10 Asymmetric Options Radar</h1>
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

        <!-- Filter Chips Bar -->
        <div class="radar-filter-bar">
          <div class="radar-filter-chips" id="radarFilterChips">
            <button type="button" class="radar-chip active" data-filter="all">All Top 10</button>
            <button type="button" class="radar-chip" data-filter="BULL_SPRING">Bull Springs (Spot &lt; 80%)</button>
            <button type="button" class="radar-chip" data-filter="BEAR_EXHAUSTION">Bear Exhaustions (Spot &gt; 80%)</button>
          </div>
          <div class="radar-count-badge" id="radarCountBadge">0 PLAYS</div>
        </div>

        <!-- Leaderboard Table Container (Positioned Prominently at the Top) -->
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

        <!-- Deep-Dive Inspector Section (Positioned Directly Below Top 10 Table) -->
        <div class="radar-inspector-section" id="radarInspectorSection">
          
          <!-- Box 1: Deterministic Quantitative Rationale Card -->
          <div class="radar-explain-card" id="radarExplainCard">
            <div class="radar-explain-header">
              <div class="explain-title-group">
                <span class="explain-badge-icon">💡</span>
                <h3 class="explain-title">Opportunity Rationale: <span id="radarInspectTickerBadge" class="inspect-ticker-badge">--</span></h3>
                <span id="radarInspectPlayBadge" class="inspect-play-badge">--</span>
                <span id="radarInspectScoreBadge" class="inspect-score-badge">--</span>
              </div>
              <button type="button" class="radar-open-cockpit-btn" id="radarOpenCockpitBtn" title="Drill Down to Full Cockpit">
                <span>Open in Cockpit ↗</span>
              </button>
            </div>
            <div class="radar-explain-body" id="radarExplainBox">
              <p class="explain-placeholder">Select a ticker from the Top 10 list above to inspect quantitative drivers.</p>
            </div>
          </div>

          <!-- Box 2: Interactive Options Exposure Chart Card -->
          <div class="radar-chart-card" id="radarChartCard">
            <div class="radar-chart-header">
              <div class="chart-title-group">
                <span class="chart-badge-icon">📊</span>
                <h3 class="chart-title">Options Exposure Profile</h3>
                <span class="chart-ticker-tag" id="radarChartTickerTag">--</span>
              </div>
              <div class="radar-key-levels" id="radarKeyLevels">
                <span class="kl-item"><span class="kl-label">SPOT</span> <strong id="radarKlSpot">--</strong></span>
                <span class="kl-item"><span class="kl-label">ZERO FLIP</span> <strong id="radarKlFlip">--</strong></span>
                <span class="kl-item"><span class="kl-label">CALL WALL</span> <strong id="radarKlCall">--</strong></span>
                <span class="kl-item"><span class="kl-label">PUT WALL</span> <strong id="radarKlPut">--</strong></span>
              </div>
              <div class="gex-dex-toggle" id="radarGexDexToggle">
                <button type="button" class="toggle-btn ${this.chartMode === 'both' ? 'active' : ''}" data-mode="both">Both</button>
                <button type="button" class="toggle-btn ${this.chartMode === 'gex' ? 'active' : ''}" data-mode="gex">Net GEX</button>
                <button type="button" class="toggle-btn ${this.chartMode === 'dex' ? 'active' : ''}" data-mode="dex">Net DEX</button>
              </div>
            </div>
            <div class="radar-chart-slot" id="radarChartSlot">
              <div class="chart-loading-slot">
                <span>Select a ticker above to mount options exposure surface...</span>
              </div>
            </div>
          </div>

          <!-- Box 3: 30-Day Options Flow Hits Table Card -->
          <div class="radar-flow-card" id="radarFlowCard">
            <div class="radar-flow-header">
              <div class="flow-title-group">
                <span class="flow-badge-icon">🌊</span>
                <h3 class="flow-title">Past Month Options Flow Prints</h3>
                <span class="flow-count-badge" id="radarFlowCountBadge">0 PRINTS</span>
              </div>
              <div class="radar-flow-filter-chips" id="radarFlowFilterChips">
                <button type="button" class="flow-chip ${this.flowFilter === 'all' ? 'active' : ''}" data-flow-filter="all">All</button>
                <button type="button" class="flow-chip ${this.flowFilter === 'whales' ? 'active' : ''}" data-flow-filter="whales">Whales (> $1M)</button>
                <button type="button" class="flow-chip ${this.flowFilter === 'calls' ? 'active' : ''}" data-flow-filter="calls">Calls</button>
                <button type="button" class="flow-chip ${this.flowFilter === 'puts' ? 'active' : ''}" data-flow-filter="puts">Puts</button>
              </div>
            </div>
            <div class="radar-flow-slot" id="radarFlowSlot">
              <div class="flow-loading-slot">
                <span>Select a ticker above to retrieve 30-day prints...</span>
              </div>
            </div>
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

    // Play Filter chips (Top 10 table)
    const chips = this.container.querySelectorAll('#radarFilterChips .radar-chip');
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

    // Row selection on Top 10 Table
    const tbody = this.container.querySelector('#radarTableBody');
    if (tbody) {
      tbody.addEventListener('click', (e) => {
        const tr = e.target.closest ? e.target.closest('tr[data-ticker]') : null;
        if (tr && tr.dataset.ticker) {
          const sym = tr.dataset.ticker;
          const rows = Array.isArray(this.currentData?.rows) ? this.currentData.rows : [];
          const rowData = rows.find(r => r.ticker === sym);
          this.selectTicker(sym, rowData);
        }
      });
    }

    // Open Cockpit Drill-Down Button in Inspector Header
    const openCockpitBtn = this.container.querySelector('#radarOpenCockpitBtn');
    if (openCockpitBtn) {
      openCockpitBtn.addEventListener('click', () => {
        if (this.selectedTicker) {
          this.drillDownToCockpit(this.selectedTicker);
        }
      });
    }

    // GEX/DEX Mode Switcher in Chart Header
    const toggleBtns = this.container.querySelectorAll('#radarGexDexToggle .toggle-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.chartMode = btn.dataset.mode || 'both';
        if (this.quantChartInstance) {
          this.quantChartInstance.setMode(this.chartMode);
        }
      });
    });

    // Flow Table Filter Chips in Flow Header
    const flowChips = this.container.querySelectorAll('#radarFlowFilterChips .flow-chip');
    flowChips.forEach(chip => {
      chip.addEventListener('click', () => {
        flowChips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.flowFilter = chip.dataset.flowFilter || 'all';
        this.renderFlowTable();
      });
    });
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

  renderSummaryHeader() {
    if (!this.container || !this.currentData) return;
    const s = this.currentData.summary;
    const sessionText = this.container.querySelector('#radarSessionText');
    if (sessionText) {
      if (s) {
        sessionText.textContent = s.session_label || `Post-Market EOD Scan (${s.scan_date})`;
      } else {
        sessionText.textContent = 'NO ACTIVE EOD SCAN';
      }
    }
  }

  // Backward compatibility alias
  renderSummaryCards() {
    this.renderSummaryHeader();
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

    // Default select #1 play if not currently set or if selected ticker is filtered out
    if (!this.selectedTicker || !rows.some(r => r.ticker === this.selectedTicker)) {
      this.selectedTicker = rows[0].ticker;
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

      const pinStrike = r.pin_wall_strike ? `$${Number(r.pin_wall_strike).toFixed(2)}` : (r.call_wall ? `$${Number(r.call_wall).toFixed(2)}` : '--');
      const pinType = (r.pin_wall_type || 'Wall').replace('_', ' ').toUpperCase();
      const dteText = r.pin_dte !== null && r.pin_dte !== undefined ? `${r.pin_dte} DTE` : '';
      const distText = r.pin_dist_pct !== null && r.pin_dist_pct !== undefined ? `${r.pin_dist_pct}%` : '';

      const ratioVal = r.flow_call_put_ratio !== null && r.flow_call_put_ratio !== undefined ? `${r.flow_call_put_ratio}x` : '--';
      const ratioType = isExhaust ? 'P/C' : 'C/P';
      const hitsCount = r.flow_hits_count || r.whale_prints_count || 0;
      const hitsText = hitsCount > 0 ? `${hitsCount} Prints` : '';

      const scoreVal = r.viability_score !== null && r.viability_score !== undefined ? r.viability_score : (r.confluence_score || '--');
      const isTopScore = typeof scoreVal === 'number' && scoreVal >= 85.0;
      const isSelected = r.ticker === this.selectedTicker;

      return `
        <tr data-ticker="${r.ticker}" class="radar-play-row ${isSelected ? 'radar-row-selected' : ''}" title="Click to inspect ${r.ticker}">
          <td class="col-rank">
            <span class="rank-badge rank-${rankNum <= 3 ? rankNum : 'other'}">#${rankNum}</span>
          </td>
          <td class="col-ticker">
            <span class="ticker-pill">${r.ticker}</span>
          </td>
          <td class="col-spot">
            <strong>${r.formatted_spot_price || (r.spot_price ? '$' + Number(r.spot_price).toFixed(2) : '$0.00')}</strong>
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

    // Trigger inspection of the selected ticker
    if (this.selectedTicker) {
      const activeRow = rows.find(r => r.ticker === this.selectedTicker) || rows[0];
      this.selectTicker(activeRow.ticker, activeRow);
    }
  }

  selectTicker(ticker, rowData = null) {
    if (!ticker) return;
    this.selectedTicker = ticker;

    // Update table row highlighting
    const rows = this.container?.querySelectorAll('#radarTableBody tr[data-ticker]');
    if (rows) {
      rows.forEach(tr => {
        if (tr.dataset.ticker === ticker) {
          tr.classList.add('radar-row-selected');
        } else {
          tr.classList.remove('radar-row-selected');
        }
      });
    }

    // Resolve row data if not provided directly
    if (!rowData && Array.isArray(this.currentData?.rows)) {
      rowData = this.currentData.rows.find(r => r.ticker === ticker);
    }

    // 1. Render Explainability Rationale immediately
    this.renderExplainability(ticker, rowData);

    // 2. Fetch Cockpit strike structures & flow prints
    this.loadTickerDetails(ticker);
  }

  renderExplainability(ticker, r) {
    const tickerBadge = this.container?.querySelector('#radarInspectTickerBadge');
    const playBadge = this.container?.querySelector('#radarInspectPlayBadge');
    const scoreBadge = this.container?.querySelector('#radarInspectScoreBadge');
    const explainBox = this.container?.querySelector('#radarExplainBox');
    const chartTag = this.container?.querySelector('#radarChartTickerTag');

    if (tickerBadge) tickerBadge.textContent = ticker;
    if (chartTag) chartTag.textContent = ticker;

    if (!r) {
      if (explainBox) {
        explainBox.innerHTML = `<p class="explain-placeholder">Retrieving quantitative thesis for ${ticker}...</p>`;
      }
      return;
    }

    const isBull = r.play_type === 'BULL_SPRING' || r.confluence_status === 'CONFIRMED_BULL';
    const playType = isBull ? 'BULL SPRING' : 'BEAR EXHAUSTION';
    const score = Number(r.viability_score || r.confluence_score || 0).toFixed(1);
    const spot = r.formatted_spot_price || (r.spot_price ? `$${Number(r.spot_price).toFixed(2)}` : '--');
    const imbalance = Number(r.exposure_imbalance_pct || 0).toFixed(1);
    const imbType = r.imbalance_type || 'GEX';
    const imbFullName = imbType === 'DEX' ? 'Delta Exposure (DEX)' : 'Gamma Exposure (GEX)';
    const pinStrike = r.pin_wall_strike ? `$${Number(r.pin_wall_strike).toFixed(2)}` : (r.call_wall ? `$${Number(r.call_wall).toFixed(2)}` : 'Key Wall');
    const pinType = (r.pin_wall_type || 'WALL').replace('_', ' ').toUpperCase();
    const pinDte = r.pin_dte !== undefined && r.pin_dte !== null ? `${r.pin_dte} DTE` : 'Near-Term';
    const pinDist = r.pin_dist_pct !== undefined && r.pin_dist_pct !== null ? `${Number(r.pin_dist_pct).toFixed(1)}%` : '0%';
    const flowRatio = r.flow_call_put_ratio !== undefined && r.flow_call_put_ratio !== null ? `${Number(r.flow_call_put_ratio).toFixed(1)}x` : '1.0x';
    const flowHits = r.flow_hits_count || r.whale_prints_count || 1;

    if (playBadge) {
      playBadge.className = `inspect-play-badge ${isBull ? 'badge-spring' : 'badge-exhaustion'}`;
      playBadge.textContent = playType;
    }
    if (scoreBadge) {
      scoreBadge.className = `inspect-score-badge ${Number(score) >= 80 ? 'score-elite' : 'score-high'}`;
      scoreBadge.textContent = `Score: ${score}`;
    }

    if (explainBox) {
      if (isBull) {
        explainBox.innerHTML = `
          <div class="explain-summary-card">
            <div class="explain-lead">
              <span class="lead-icon">⚡</span>
              <p><strong>${ticker}</strong> was ranked <strong>#${r.rank || 1}</strong> as a high-conviction <strong>BULL SPRING</strong> play with a Viability Score of <strong>${score}</strong>.</p>
            </div>
            <ul class="explain-factors-list">
              <li>
                <span class="factor-bullet">1</span>
                <div>
                  <strong>Extreme Exposure Compression:</strong> Spot price (<strong>${spot}</strong>) is compressed below <strong>${imbalance}%</strong> of dealer ${imbFullName}, creating massive potential kinetic energy once dealer gamma flips positive.
                </div>
              </li>
              <li>
                <span class="factor-bullet">2</span>
                <div>
                  <strong>Imminent Pin Catalyst:</strong> The asset is pinned directly beneath a dominant <strong>${pinStrike} ${pinType}</strong> expiring in <strong>${pinDte}</strong> (${pinDist} from spot), serving as an active upward gravitational magnet.
                </div>
              </li>
              <li>
                <span class="factor-bullet">3</span>
                <div>
                  <strong>Aggressive Institutional Flow:</strong> Reinforced by a <strong>${flowRatio} Call/Put ratio</strong> across <strong>${flowHits}</strong> institutional flow print(s) on the watchlist.
                </div>
              </li>
            </ul>
          </div>
        `;
      } else {
        explainBox.innerHTML = `
          <div class="explain-summary-card">
            <div class="explain-lead">
              <span class="lead-icon">⚠️</span>
              <p><strong>${ticker}</strong> was ranked <strong>#${r.rank || 1}</strong> as a high-conviction <strong>BEAR EXHAUSTION</strong> play with a Viability Score of <strong>${score}</strong>.</p>
            </div>
            <ul class="explain-factors-list">
              <li>
                <span class="factor-bullet">1</span>
                <div>
                  <strong>Exhausted Upside Exposure:</strong> Spot price (<strong>${spot}</strong>) is trading overextended above <strong>${imbalance}%</strong> of dealer ${imbFullName}, signaling dealer inventory saturation and vulnerability to sharp deceleration.
                </div>
              </li>
              <li>
                <span class="factor-bullet">2</span>
                <div>
                  <strong>Downside Pin Cushion:</strong> Protected by a heavy <strong>${pinStrike} ${pinType}</strong> expiring in <strong>${pinDte}</strong> (${pinDist} from spot), marking the primary downside stabilization level.
                </div>
              </li>
              <li>
                <span class="factor-bullet">3</span>
                <div>
                  <strong>Elevated Put Accumulation:</strong> Backed by a <strong>${flowRatio} Put/Call flow ratio</strong> across <strong>${flowHits}</strong> institutional print(s) in the options flow database.
                </div>
              </li>
            </ul>
          </div>
        `;
      }
    }
  }

  async loadTickerDetails(ticker) {
    if (this.activeAbortController) {
      this.activeAbortController.abort();
    }
    this.activeAbortController = new AbortController();

    // Check memory cache
    const cached = this.tickerDataCache.get(ticker);
    if (cached) {
      this.renderExposureChart(cached);
      this.renderFlowTable(cached.flow?.records || []);
      return;
    }

    // Set loading slots
    const chartSlot = this.container?.querySelector('#radarChartSlot');
    const flowSlot = this.container?.querySelector('#radarFlowSlot');
    if (chartSlot) {
      chartSlot.innerHTML = `
        <div class="chart-loading-slot">
          <div class="cockpit-spinner"></div>
          <span>Retrieving GEX/DEX strikes for ${ticker}...</span>
        </div>
      `;
    }
    if (flowSlot) {
      flowSlot.innerHTML = `
        <div class="flow-loading-slot">
          <div class="cockpit-spinner"></div>
          <span>Loading 30-day options flow prints for ${ticker}...</span>
        </div>
      `;
    }

    try {
      const res = await fetchWithAuth(`/api/cockpit/data?force_refresh=false&_t=${Date.now()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, force_refresh: false }),
        signal: this.activeAbortController.signal
      });

      if (res && res.ok) {
        const data = await res.json();
        if (data) {
          this.tickerDataCache.set(ticker, data);
          if (this.selectedTicker === ticker) {
            this.renderExposureChart(data);
            this.renderFlowTable(data.flow?.records || []);
          }
        }
      } else {
        throw new Error(`HTTP ${res?.status || 500}`);
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      console.warn(`Failed to fetch details for ${ticker}:`, err);
      if (chartSlot) {
        chartSlot.innerHTML = `
          <div class="radar-chart-empty">
            <span class="empty-icon">⚠️</span>
            <p>Could not load live strike structure for <strong>${ticker}</strong>.</p>
          </div>
        `;
      }
      if (flowSlot) {
        flowSlot.innerHTML = `
          <div class="flow-empty-state">
            <span>Could not load options flow prints for <strong>${ticker}</strong>.</span>
          </div>
        `;
      }
    }
  }

  renderExposureChart(data) {
    const chartSlot = this.container?.querySelector('#radarChartSlot');
    if (!chartSlot || !data) return;

    const gex = data.gex || {};
    const metrics = data.metrics || {};

    const spot = Number(gex.spot_price || metrics.spot_price || data.spot_price || 0);
    const flip = Number(gex.zero_gex_level || metrics.zero_gamma_flip || data.zero_flip || spot);
    const callWall = Number(gex.call_wall || metrics.call_wall || data.call_wall || 0);
    const putWall = Number(gex.put_wall || metrics.put_wall || data.put_wall || 0);
    const cpRatio = Number(
      gex.call_put_ratio !== undefined && gex.call_put_ratio !== null ? gex.call_put_ratio :
      (metrics.call_put_ratio !== undefined && metrics.call_put_ratio !== null ? metrics.call_put_ratio :
      (data.call_put_ratio !== undefined && data.call_put_ratio !== null ? data.call_put_ratio : 0))
    );

    const klSpot = this.container.querySelector('#radarKlSpot');
    const klFlip = this.container.querySelector('#radarKlFlip');
    const klCall = this.container.querySelector('#radarKlCall');
    const klPut = this.container.querySelector('#radarKlPut');

    if (klSpot) klSpot.textContent = spot > 0 ? `$${spot.toFixed(2)}` : '--';
    if (klFlip) klFlip.textContent = flip > 0 ? `$${flip.toFixed(2)}` : '--';
    if (klCall) klCall.textContent = callWall > 0 ? `$${callWall.toFixed(2)}` : '--';
    if (klPut) klPut.textContent = putWall > 0 ? `$${putWall.toFixed(2)}` : '--';

    const strikes = (gex.strikes && Array.isArray(gex.strikes)) ? gex.strikes : (data.strikes || []);
    const ticker = data.ticker || gex.ticker || this.selectedTicker || 'QUANT';

    if (!strikes || strikes.length === 0) {
      chartSlot.innerHTML = `
        <div class="radar-chart-empty">
          <span class="empty-icon">📊</span>
          <p>No option strike exposure data available for <strong>${ticker}</strong>.</p>
        </div>
      `;
      return;
    }

    chartSlot.innerHTML = '';
    const expirations = (Array.isArray(gex.expirations) && gex.expirations.length > 0)
      ? gex.expirations
      : ((Array.isArray(data.expirations) && data.expirations.length > 0)
        ? data.expirations
        : (strikes[0]?.exp_gex ? Object.keys(strikes[0].exp_gex) : []));

    const chartData = {
      ticker,
      spot_price: spot,
      zero_flip: flip,
      call_wall: callWall,
      put_wall: putWall,
      call_put_ratio: cpRatio,
      strikes,
      expirations
    };

    try {
      this.quantChartInstance = new QuantChart(chartSlot, chartData, { mode: this.chartMode });
    } catch (err) {
      console.error('Failed to mount QuantChart in Radar Inspector:', err);
    }
  }

  renderFlowTable(records = null) {
    const flowSlot = this.container?.querySelector('#radarFlowSlot');
    const countBadge = this.container?.querySelector('#radarFlowCountBadge');
    if (!flowSlot) return;

    if (records !== null) {
      this.currentFlowRecords = records || [];
    }

    let items = [...this.currentFlowRecords];
    if (this.flowFilter === 'whales') {
      items = items.filter(r => (r.premium || 0) >= 1000000);
    } else if (this.flowFilter === 'calls') {
      items = items.filter(r => (r.put_call || r.type || '').toUpperCase().includes('CALL'));
    } else if (this.flowFilter === 'puts') {
      items = items.filter(r => (r.put_call || r.type || '').toUpperCase().includes('PUT'));
    }

    if (countBadge) {
      countBadge.textContent = `${items.length} PRINTS`;
    }

    if (items.length === 0) {
      flowSlot.innerHTML = `
        <div class="flow-empty-state">
          <span>No ${this.flowFilter !== 'all' ? this.flowFilter : ''} options flow prints found in the past 30 days.</span>
        </div>
      `;
      return;
    }

    const rowsHtml = items.slice(0, 30).map(r => {
      const isCall = (r.put_call || r.type || '').toUpperCase().includes('CALL');
      const isWhale = (r.premium || 0) >= 1000000;
      const premStr = r.premium ? `$${(r.premium >= 1000000 ? (r.premium / 1000000).toFixed(2) + 'M' : (r.premium / 1000).toFixed(0) + 'K')}` : '--';
      const actionClass = (r.action || '').toUpperCase() === 'BUY' ? 'action-buy' : 'action-sell';
      const typeClass = isCall ? 'type-call' : 'type-put';
      const strikeVal = Number(r.strike || 0);
      const strikeStr = strikeVal > 0 ? `$${strikeVal.toFixed(1)}` : '--';

      return `
        <tr>
          <td class="cell-mono">${r.trade_date || r.date || '--'}</td>
          <td class="cell-mono">${strikeStr}</td>
          <td class="cell-mono">${r.expiration || '--'}</td>
          <td><span class="flow-type-badge ${typeClass}">${isCall ? 'CALL' : 'PUT'}</span></td>
          <td class="cell-mono ${isWhale ? 'text-whale' : ''}">${premStr} ${isWhale ? '🐳' : ''}</td>
          <td><span class="flow-action-badge ${actionClass}">${r.action || 'AUTO'}</span></td>
          <td class="cell-mono">${r.spot ? '$' + Number(r.spot).toFixed(2) : '--'}</td>
          <td class="cell-mono text-dim">${r.order_type || 'SWEEP'}</td>
        </tr>
      `;
    }).join('');

    flowSlot.innerHTML = `
      <div class="radar-flow-table-wrapper">
        <table class="radar-flow-table">
          <thead>
            <tr>
              <th>DATE</th>
              <th>STRIKE</th>
              <th>EXPIRATION</th>
              <th>TYPE</th>
              <th>PREMIUM</th>
              <th>ACTION</th>
              <th>SPOT</th>
              <th>ORDER</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;
  }
}

