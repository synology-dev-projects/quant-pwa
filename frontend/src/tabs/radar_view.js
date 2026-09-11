import { fetchWithAuth } from '../state.js?v=30';

export class RadarView {
  constructor() {
    this.container = null;
    this.currentData = null;
    this.availableDates = [];
    this.selectedDate = null;
    this.sortColumn = 'premium_7d';
    this.sortDirection = 'desc'; // 'desc' | 'asc' | 'natural'
    this.isLoading = false;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="radar-view-container">
        <!-- Top Controls & Session Header Bar -->
        <div class="radar-header-bar">
          <div class="radar-title-group">
            <span class="radar-badge-icon">🎯</span>
            <h1 class="radar-title">Confluence Radar</h1>
            <span class="radar-session-tag" id="radarSessionTag">
              <span class="status-dot dot-live"></span>
              <span class="tag-text" id="radarSessionText">RESOLVING...</span>
            </span>
          </div>

          <div class="radar-controls-group">
            <div class="radar-date-picker-wrap">
              <label for="radarDateSelect" class="radar-control-label">SESSION:</label>
              <select id="radarDateSelect" class="radar-date-select">
                <option value="">LATEST</option>
              </select>
            </div>
            <button type="button" class="radar-refresh-btn" id="radarRefreshBtn" title="Reload Unified Table">↻</button>
          </div>
        </div>

        <!-- Info Ribbon with Included Dates & Metric Stats -->
        <div class="radar-info-ribbon" id="radarInfoRibbon">
          <div class="radar-ribbon-item">
            <span class="ribbon-label">TRAIL 3D:</span>
            <strong class="ribbon-val" id="radarDates3d">-</strong>
          </div>
          <div class="radar-ribbon-item">
            <span class="ribbon-label">TRAIL 7D:</span>
            <strong class="ribbon-val" id="radarDates7d">-</strong>
          </div>
          <div class="radar-ribbon-item">
            <span class="ribbon-label">TICKERS:</span>
            <strong class="ribbon-val" id="radarTotalTickers">0</strong>
          </div>
          <div class="radar-ribbon-item">
            <span class="ribbon-label">TOP FLOW:</span>
            <strong class="ribbon-val accent-gold" id="radarTopFlow">-</strong>
          </div>
          <div class="radar-ribbon-hint">
            <span>💡 Click any ticker to inspect in Cockpit ↗</span>
          </div>
        </div>

        <!-- Unified GEX/DEX & Options Flow Matrix Table -->
        <div class="radar-table-card">
          <div class="radar-table-wrapper quant-table-wrapper" id="radarTableWrapper">
            <table class="radar-table flow-table" id="radarTable">
              <thead>
                <tr>
                  <th data-col="ticker" class="sortable col-ticker">TICKER</th>
                  <th data-col="spot_price" class="sortable col-num">SPOT</th>
                  <th data-col="call_put_ratio" class="sortable col-ratio">C/P RATIO</th>
                  <th data-col="prints_3d" class="sortable col-num">PRINTS (3D)</th>
                  <th data-col="prints_7d" class="sortable col-num">PRINTS (7D)</th>
                  <th data-col="premium_3d" class="sortable col-prem">PREM (3D)</th>
                  <th data-col="premium_7d" class="sortable col-prem sort-desc">PREM (7D)</th>
                  <th data-col="call_wall" class="sortable col-num">CALL WALL</th>
                  <th data-col="put_wall" class="sortable col-num">PUT WALL</th>
                  <th data-col="zero_flip" class="sortable col-num">ZERO FLIP</th>
                  <th data-col="net_gex" class="sortable col-prem">NET GEX</th>
                  <th data-col="gamma_regime" class="sortable col-regime">REGIME</th>
                </tr>
              </thead>
              <tbody id="radarTableBody">
                <tr>
                  <td colspan="12" class="radar-loading-cell">
                    <div class="cockpit-loading-block">
                      <div class="typing-indicator"><span></span><span></span><span></span></div>
                      <span class="loading-label">Loading Confluence Radar unified matrix...</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    if (typeof window !== 'undefined' && window.location && window.location.origin) {
      this.loadAvailableDates();
    }
  }

  bindEvents() {
    if (!this.container || typeof this.container.querySelector !== 'function') return;

    // Refresh Button
    const refreshBtn = this.container.querySelector('#radarRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.loadScanData(this.selectedDate);
      });
    }

    // Date Selector
    const dateSelect = this.container.querySelector('#radarDateSelect');
    if (dateSelect) {
      dateSelect.addEventListener('change', (e) => {
        this.selectedDate = e.target.value || null;
        this.loadScanData(this.selectedDate);
      });
    }

    // Table Header Sorting
    const thead = this.container.querySelector('#radarTable thead');
    if (thead) {
      thead.addEventListener('click', (e) => {
        const th = e.target.closest('th.sortable');
        if (!th) return;
        const col = th.getAttribute('data-col');
        if (!col) return;
        this.handleSort(col);
      });
    }

    // Row / Ticker Click-to-Cockpit Drilldown
    const tbody = this.container.querySelector('#radarTableBody');
    if (tbody) {
      tbody.addEventListener('click', (e) => {
        const row = e.target.closest('tr[data-ticker]');
        if (!row) return;
        const ticker = row.getAttribute('data-ticker');
        if (ticker) {
          this.drillDownToCockpit(ticker);
        }
      });
    }
  }

  async loadAvailableDates() {
    try {
      const res = await fetchWithAuth('/api/radar/dates');
      if (res && res.ok) {
        this.availableDates = await res.json();
        this.renderDateSelect();
      }
    } catch (err) {
      console.warn('[RadarView] Failed to load available dates:', err);
    }
  }

  renderDateSelect() {
    if (!this.container) return;
    const select = this.container.querySelector('#radarDateSelect');
    if (!select) return;

    if (!this.availableDates || this.availableDates.length === 0) {
      select.innerHTML = '<option value="">LATEST</option>';
      return;
    }

    select.innerHTML = this.availableDates.map(d => `
      <option value="${d}" ${d === this.selectedDate ? 'selected' : ''}>${d}</option>
    `).join('');
  }

  async loadScanData(targetDate = null) {
    if (!this.container || this.isLoading) return;
    this.isLoading = true;
    this.renderLoadingState();

    try {
      const url = targetDate ? `/api/radar/unified-table?date=${encodeURIComponent(targetDate)}` : '/api/radar/unified-table';
      const res = await fetchWithAuth(url);
      if (res && res.ok) {
        this.currentData = await res.json();
        this.selectedDate = this.currentData.session_date;
        if (this.currentData.available_dates) {
          this.availableDates = this.currentData.available_dates;
          this.renderDateSelect();
        }
        this.renderHeaderAndRibbon();
        this.renderRows();
      } else {
        this.renderErrorState();
      }
    } catch (err) {
      console.error('[RadarView] Load unified table error:', err);
      this.renderErrorState();
    } finally {
      this.isLoading = false;
    }
  }

  renderLoadingState() {
    if (!this.container) return;
    const tbody = this.container.querySelector('#radarTableBody');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="12" class="radar-loading-cell">
            <div class="cockpit-loading-block">
              <div class="typing-indicator"><span></span><span></span><span></span></div>
              <span class="loading-label">Loading Confluence Radar unified matrix...</span>
            </div>
          </td>
        </tr>
      `;
    }
  }

  renderErrorState() {
    if (!this.container) return;
    const tbody = this.container.querySelector('#radarTableBody');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="12" class="radar-empty-cell error">
            ⚠️ Failed to load Confluence Radar data. Please retry.
          </td>
        </tr>
      `;
    }
  }

  renderHeaderAndRibbon() {
    if (!this.container || !this.currentData) return;

    // Session Tag
    const sessionText = this.container.querySelector('#radarSessionText');
    if (sessionText) {
      sessionText.textContent = `SESSION: ${this.currentData.session_date}`;
    }

    // Ribbon Stats
    const d3 = this.container.querySelector('#radarDates3d');
    if (d3) {
      d3.textContent = (this.currentData.dates_3d || []).join(', ') || '-';
    }

    const d7 = this.container.querySelector('#radarDates7d');
    if (d7) {
      const dArr = this.currentData.dates_7d || [];
      d7.textContent = dArr.length > 0 ? `${dArr[dArr.length - 1]} → ${dArr[0]} (${dArr.length}d)` : '-';
    }

    const totalEl = this.container.querySelector('#radarTotalTickers');
    if (totalEl) {
      totalEl.textContent = `${this.currentData.total_tickers || 0}`;
    }

    const topFlowEl = this.container.querySelector('#radarTopFlow');
    if (topFlowEl) {
      topFlowEl.textContent = this.currentData.top_flow_ticker || '-';
    }
  }

  handleSort(column) {
    if (this.sortColumn === column) {
      if (this.sortDirection === 'desc') {
        this.sortDirection = 'asc';
      } else if (this.sortDirection === 'asc') {
        this.sortDirection = 'natural';
      } else {
        this.sortDirection = 'desc';
      }
    } else {
      this.sortColumn = column;
      this.sortDirection = 'desc';
    }

    this.updateHeaderSortClasses();
    this.renderRows();
  }

  updateHeaderSortClasses() {
    if (!this.container) return;
    const headers = this.container.querySelectorAll('#radarTable th.sortable');
    headers.forEach(th => {
      const col = th.getAttribute('data-col');
      th.classList.remove('sort-desc', 'sort-asc');
      if (col === this.sortColumn && this.sortDirection !== 'natural') {
        th.classList.add(this.sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
      }
    });
  }

  getSortedRows() {
    if (!this.currentData || !this.currentData.rows) return [];
    const rows = [...this.currentData.rows];

    if (this.sortDirection === 'natural') {
      return rows;
    }

    const col = this.sortColumn;
    const isAsc = this.sortDirection === 'asc';

    rows.sort((a, b) => {
      let valA = a[col];
      let valB = b[col];

      // Handle numeric parses for ratios or null values
      if (valA === null || valA === undefined || valA === 'N/A') valA = isAsc ? Infinity : -Infinity;
      if (valB === null || valB === undefined || valB === 'N/A') valB = isAsc ? Infinity : -Infinity;

      if (typeof valA === 'string' && typeof valB === 'string') {
        const numA = parseFloat(valA);
        const numB = parseFloat(valB);
        if (!isNaN(numA) && !isNaN(numB)) {
          return isAsc ? numA - numB : numB - numA;
        }
        return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }

      if (valA < valB) return isAsc ? -1 : 1;
      if (valA > valB) return isAsc ? 1 : -1;
      return 0;
    });

    return rows;
  }

  renderRows() {
    if (!this.container || !this.currentData) return;
    const tbody = this.container.querySelector('#radarTableBody');
    if (!tbody) return;

    const rows = this.getSortedRows();
    if (rows.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="12" class="radar-empty-cell">
            No qualifying tickers found for session ${this.selectedDate || 'current'}.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const gexClass = (r.net_gex || 0) > 0 ? 'metric-green' : ((r.net_gex || 0) < 0 ? 'metric-blood' : '');
      const regimeClass = r.gamma_regime === 'Positive' || r.gamma_regime === 'PINNED / LOW VOL' 
        ? 'regime-bull' 
        : (r.gamma_regime === 'Negative' || r.gamma_regime === 'HIGH VOL' ? 'regime-bear' : 'regime-neutral');

      return `
        <tr data-ticker="${r.ticker}" title="Open ${r.ticker} in Cockpit">
          <td class="col-ticker">
            <span class="flow-ticker-btn radar-ticker-btn">${r.ticker}</span>
          </td>
          <td class="col-num">${r.formatted_spot_price}</td>
          <td class="col-ratio"><span class="radar-ratio-pill">${r.call_put_ratio}</span></td>
          <td class="col-num"><strong class="flow-metric-primary">${r.prints_3d}</strong></td>
          <td class="col-num"><strong class="flow-metric-primary">${r.prints_7d}</strong></td>
          <td class="col-prem"><span class="flow-metric-secondary">${r.formatted_premium_3d}</span></td>
          <td class="col-prem"><strong class="flow-metric-primary metric-gold">${r.formatted_premium_7d}</strong></td>
          <td class="col-num">${r.formatted_call_wall}</td>
          <td class="col-num">${r.formatted_put_wall}</td>
          <td class="col-num">${r.formatted_zero_flip}</td>
          <td class="col-prem"><span class="${gexClass}">${r.formatted_net_gex}</span></td>
          <td class="col-regime"><span class="radar-regime-pill ${regimeClass}">${r.gamma_regime}</span></td>
        </tr>
      `;
    }).join('');
  }

  drillDownToCockpit(ticker) {
    if (!ticker) return;
    if (typeof window !== 'undefined' && window.quantApp) {
      if (window.quantApp.tabManager) {
        window.quantApp.tabManager.switchTab('cockpit');
      }
      if (window.quantApp.cockpitView && typeof window.quantApp.cockpitView.searchTicker === 'function') {
        const input = typeof document !== 'undefined' ? document.querySelector('#cockpitSearchInput') : null;
        if (input) input.value = ticker;
        window.quantApp.cockpitView.searchTicker(ticker);
      }
    }
  }

  destroy() {
    if (this.container) {
      this.container.innerHTML = '';
    }
  }
}
