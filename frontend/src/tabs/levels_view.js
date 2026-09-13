/**
 * quant-pwa/frontend/src/tabs/levels_view.js - SPX Quant Levels Tab (PWA-01)
 *
 * Exclusively locked to ticker SPX (S&P 500 Index).
 * Renders:
 * 1. SPX Header with As-Of Date selector and sync controls.
 * 2. Hero HUD cards (Spot Price, Immediate Resistance, Immediate Support, Channel Width).
 * 3. Interactive Visual Price Ladder with dynamic Spot Price marker insertion.
 * 4. Institutional Structured Levels Table.
 */

import { fetchWithAuth } from '../state.js';
import { CandlestickChart } from '../components/candlestick_chart.js';

export function sanitizeComment(raw) {
  if (raw == null) return '';
  const s = String(raw).trim();
  if (/^(nan|none|null|nat|—|-)$/i.test(s)) return '';
  return s;
}

export function getEasternMarketStatus(now = new Date()) {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      weekday: 'short',
      hour12: false
    });
    const parts = formatter.formatToParts(now);
    const map = {};
    for (const p of parts) {
      map[p.type] = p.value;
    }
    const year = map.year;
    const month = map.month;
    const day = map.day;
    const hour = parseInt(map.hour, 10);
    const minute = parseInt(map.minute, 10);
    const weekday = map.weekday;

    const todayDateStr = `${year}-${month}-${day}`;
    const isWeekend = weekday === 'Sat' || weekday === 'Sun';
    const totalMinutes = hour * 60 + minute;
    // Regular Trading Hours: 09:30 - 16:15 ET (570 to 975 minutes)
    const isMarketHours = !isWeekend && (totalMinutes >= 570 && totalMinutes <= 975);

    return {
      todayDateStr,
      isMarketHours,
      weekday,
      timeStr: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
    };
  } catch (err) {
    const today = new Date().toISOString().split('T')[0];
    return {
      todayDateStr: today,
      isMarketHours: false,
      weekday: 'Unknown',
      timeStr: '00:00'
    };
  }
}

export class LevelsView {
  constructor() {
    this.ticker = 'SPX'; // Strictly locked to SPX
    this.container = null;
    this.availableDates = [];
    this.selectedDate = '';
    this.currentData = null;
    this.isLoading = false;
    this.candlestickChart = null;
    this.pollInterval = null;
    this._onVisibilityChange = null;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="levels-container" id="levelsContainer">
        <!-- Header Bar -->
        <div class="levels-header-bar">
          <div class="levels-title-group">
            <span class="levels-ticker-badge">SPX 500</span>
            <div>
              <h2 class="levels-main-title">Quant Levels Terminal</h2>
              <p class="levels-subtitle">S&P 500 Daily Pivot &amp; Structure Sheet</p>
            </div>
          </div>
          <div class="levels-controls levels-controls-group">
            <button type="button" class="levels-step-btn" id="levelsPrevBtn" title="Previous Session">◄ Prev</button>
            <input type="date" class="levels-date-picker" id="levelsDatePicker" max="${new Date().toISOString().split('T')[0]}" aria-label="Select Date">
            <button type="button" class="levels-step-btn" id="levelsNextBtn" title="Next Session">Next ►</button>
            <select class="levels-date-select" id="levelsDateSelect" aria-label="Select As-Of Date">
              <option value="">Latest Session</option>
            </select>
            <button class="levels-refresh-btn" id="levelsRefreshBtn" title="Refresh SPX Levels">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M23 4v6h-6"></path>
                <path d="M1 20v-6h6"></path>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        <!-- Content Mount Target -->
        <div id="levelsContentMount">
          <div class="levels-empty-state">
            <p class="levels-empty-title">Loading SPX Quant Levels...</p>
            <p class="levels-empty-desc">Connecting to PostgreSQL database &amp; quote feed...</p>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    this.loadInitialData();
  }

  bindEvents() {
    this._onVisibilityChange = () => {
      if (typeof document !== 'undefined' && document.hidden) {
        this.updateLiveIndicator(false, 'PAUSED (TAB HIDDEN)');
      } else {
        this.checkAndStartPolling();
      }
    };
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('visibilitychange', this._onVisibilityChange);
    }

    const datePicker = this.container.querySelector('#levelsDatePicker');
    if (datePicker) {
      datePicker.addEventListener('change', (e) => {
        this.selectedDate = e.target.value;
        const dateSelect = this.container.querySelector('#levelsDateSelect');
        if (dateSelect) {
          if (this.availableDates.includes(this.selectedDate)) {
            dateSelect.value = this.selectedDate;
          } else {
            dateSelect.value = '';
          }
        }
        this.updateStepButtons();
        this.loadLevelsData();
        this.checkAndStartPolling();
      });
    }

    const dateSelect = this.container.querySelector('#levelsDateSelect');
    if (dateSelect) {
      dateSelect.addEventListener('change', (e) => {
        this.selectedDate = e.target.value;
        if (datePicker) {
          datePicker.value = this.selectedDate;
        }
        this.updateStepButtons();
        this.loadLevelsData();
        this.checkAndStartPolling();
      });
    }

    const prevBtn = this.container.querySelector('#levelsPrevBtn');
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        this.stepSession(-1);
        this.checkAndStartPolling();
      });
    }

    const nextBtn = this.container.querySelector('#levelsNextBtn');
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        this.stepSession(1);
        this.checkAndStartPolling();
      });
    }

    const refreshBtn = this.container.querySelector('#levelsRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.loadInitialData();
      });
    }
  }

  destroy() {
    this.stopPolling();
    if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function' && this._onVisibilityChange) {
      document.removeEventListener('visibilitychange', this._onVisibilityChange);
      this._onVisibilityChange = null;
    }
    if (this.candlestickChart) {
      if (typeof this.candlestickChart.destroy === 'function') {
        this.candlestickChart.destroy();
      }
      this.candlestickChart = null;
    }
  }

  getPreviousWeekday(dateStr) {
    if (!dateStr) dateStr = new Date().toISOString().split('T')[0];
    const d = new Date(dateStr + 'T12:00:00Z');
    do {
      d.setUTCDate(d.getUTCDate() - 1);
    } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
    return d.toISOString().split('T')[0];
  }

  getNextWeekday(dateStr) {
    if (!dateStr) dateStr = new Date().toISOString().split('T')[0];
    const d = new Date(dateStr + 'T12:00:00Z');
    do {
      d.setUTCDate(d.getUTCDate() + 1);
    } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
    return d.toISOString().split('T')[0];
  }

  stepSession(direction) {
    const datePicker = this.container ? this.container.querySelector('#levelsDatePicker') : null;
    const dateSelect = this.container ? this.container.querySelector('#levelsDateSelect') : null;

    if (direction < 0) {
      // ◄ Prev session (older date)
      let targetDate = '';
      const currDate = this.selectedDate || (this.availableDates.length > 0 ? this.availableDates[0] : '');
      if (this.availableDates.length > 0) {
        const currIdx = this.availableDates.indexOf(currDate);
        if (currIdx !== -1 && currIdx < this.availableDates.length - 1) {
          targetDate = this.availableDates[currIdx + 1];
        } else if (currIdx === -1) {
          const older = this.availableDates.find(d => d < currDate);
          targetDate = older || this.getPreviousWeekday(currDate);
        } else {
          targetDate = this.getPreviousWeekday(currDate);
        }
      } else {
        targetDate = this.getPreviousWeekday(currDate);
      }
      this.selectedDate = targetDate;
    } else if (direction > 0) {
      // Next ► session (newer date)
      if (this.availableDates.length > 0) {
        const currDate = this.selectedDate || this.availableDates[0];
        const currIdx = this.availableDates.indexOf(currDate);
        if (currIdx > 0) {
          this.selectedDate = this.availableDates[currIdx - 1];
        } else if (currIdx === 0) {
          return; // Already at latest available date
        } else {
          const newerDates = this.availableDates.filter(d => d > currDate);
          if (newerDates.length > 0) {
            this.selectedDate = newerDates[newerDates.length - 1];
          } else {
            this.selectedDate = this.availableDates[0];
          }
        }
      } else {
        this.selectedDate = this.getNextWeekday(this.selectedDate);
      }
    }

    if (datePicker) {
      datePicker.value = this.selectedDate;
    }
    if (dateSelect) {
      if (this.availableDates.includes(this.selectedDate)) {
        dateSelect.value = this.selectedDate;
      } else {
        dateSelect.value = '';
      }
    }
    this.updateStepButtons();
    this.loadLevelsData();
  }

  updateStepButtons() {
    const nextBtn = this.container ? this.container.querySelector('#levelsNextBtn') : null;
    if (!nextBtn) return;

    if (this.availableDates.length > 0) {
      const latestDate = this.availableDates[0];
      const isLatest = !this.selectedDate || this.selectedDate === latestDate || this.selectedDate >= latestDate;
      nextBtn.disabled = isLatest;
    } else {
      const today = new Date().toISOString().split('T')[0];
      nextBtn.disabled = !this.selectedDate || this.selectedDate >= today;
    }
  }

  async loadInitialData() {
    await this.loadDates();
    await this.loadLevelsData();
  }

  async loadDates() {
    try {
      const resp = await fetchWithAuth(`/api/quant-levels/dates?ticker=${this.ticker}`);
      if (resp && resp.ok) {
        const dates = await resp.json();
        this.availableDates = Array.isArray(dates) ? dates : [];
        this.updateDateSelector();
      }
    } catch (e) {
      console.warn('[LevelsView] Failed to load available dates:', e);
    }
  }

  updateDateSelector() {
    const dateSelect = this.container ? this.container.querySelector('#levelsDateSelect') : null;
    const datePicker = this.container ? this.container.querySelector('#levelsDatePicker') : null;

    if (dateSelect) {
      dateSelect.innerHTML = '<option value="">Latest Session</option>';
      this.availableDates.forEach((d) => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        if (d === this.selectedDate) {
          opt.selected = true;
        }
        dateSelect.appendChild(opt);
      });
      if (this.selectedDate && this.availableDates.includes(this.selectedDate)) {
        dateSelect.value = this.selectedDate;
      } else if (!this.selectedDate) {
        dateSelect.value = '';
      }
    }

    if (datePicker && this.selectedDate) {
      datePicker.value = this.selectedDate;
    }

    this.updateStepButtons();
  }

  async loadLevelsData() {
    const mount = this.container ? this.container.querySelector('#levelsContentMount') : null;
    if (!mount) return;

    this.isLoading = true;
    let url = `/api/quant-levels/data?ticker=${this.ticker}`;
    if (this.selectedDate) {
      url += `&as_of_date=${encodeURIComponent(this.selectedDate)}`;
    }

    try {
      const resp = await fetchWithAuth(url);
      if (!resp || !resp.ok) {
        this.renderErrorState(mount, `Server error: HTTP ${resp ? resp.status : 'offline'}`);
        return;
      }
      const data = await resp.json();
      this.currentData = data;

      if (data.status === 'empty' || !data.levels || data.levels.length === 0) {
        this.renderEmptyState(mount, data.message || 'No SPX quant levels recorded for this date.');
        return;
      }

      this.renderLevelsUI(mount, data);
    } catch (err) {
      this.renderErrorState(mount, err.message || 'Failed connecting to gateway');
    } finally {
      this.isLoading = false;
    }
  }

  renderLevelsUI(mount, data) {
    const summary = data.summary || {};
    const spot = data.spot_price;
    const isHistorical = data.spot_type === 'HISTORICAL_CLOSE' || (summary && summary.spot_label === 'SPX Session Close');

    // Sync date picker if datePicker has no value
    const datePicker = this.container ? this.container.querySelector('#levelsDatePicker') : null;
    if (datePicker && !datePicker.value && (data.as_of_date || this.selectedDate)) {
      datePicker.value = data.as_of_date || this.selectedDate;
    }

    mount.innerHTML = `
      <!-- Price Ladder Table Section -->
      <div class="levels-ladder-section">
        <div class="levels-ladder-header">
          <div class="levels-ladder-title-group">
            <h3 class="levels-ladder-title">Interactive Price Ladder</h3>
            <span class="levels-subtitle">Top-to-Bottom Structure</span>
          </div>
          <div class="levels-ladder-header-right" id="levelsHeaderRightMount">
            <div class="levels-live-pill" id="levelsLivePill">
              <span class="live-indicator-dot"></span>
              <span class="live-text">LIVE 30S</span>
            </div>
          </div>
        </div>
        <div class="levels-table-wrapper">
          <table class="levels-table levels-ladder-table">
            <thead>
              <tr>
                <th style="width: 90px;">Type</th>
                <th style="width: 200px;">Level / Range</th>
                <th>Commentary</th>
              </tr>
            </thead>
            <tbody id="priceLadderMount">
              ${this.buildLadderHtml(data.levels, spot, isHistorical)}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Candlestick Chart Section -->
      <div class="levels-candlestick-section" id="levelsCandlestickMount">
        <div class="candlestick-loading-placeholder">
          <div class="candlestick-pulse-spinner"></div>
          <span>Loading SPX Intraday Candlesticks (5m)...</span>
        </div>
      </div>
    `;

    // Asynchronously load and mount 5-minute session candlesticks
    this.loadCandlesData(data);

    // Evaluate live market hours & start polling if viewing today's session
    this.checkAndStartPolling();
  }

  checkAndStartPolling() {
    const status = getEasternMarketStatus();
    const isToday = !this.selectedDate || this.selectedDate === status.todayDateStr;

    if (!isToday) {
      this.stopPolling();
      this.updateLiveIndicator(false, 'HISTORICAL');
      return;
    }

    if (!status.isMarketHours) {
      this.stopPolling();
      this.updateLiveIndicator(false, 'MARKET CLOSED');
      return;
    }

    this.startPolling();
  }

  startPolling() {
    this.updateLiveIndicator(true, 'LIVE 30S');
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
    this.pollInterval = setInterval(() => {
      this.pollTick();
    }, 30000);
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  updateLiveIndicator(isActive, text = 'LIVE 30S') {
    const pill = this.container?.querySelector?.('#levelsLivePill');
    if (!pill) return;
    if (isActive) {
      pill.className = 'levels-live-pill active';
      pill.innerHTML = `<span class="live-indicator-dot"></span><span class="live-text">${text}</span>`;
      pill.title = 'Live market polling active (refreshes every 30 seconds)';
    } else {
      pill.className = 'levels-live-pill paused';
      pill.innerHTML = `<span class="live-indicator-dot"></span><span class="live-text">${text}</span>`;
      pill.title = 'Live polling paused';
    }
  }

  async pollTick() {
    if (this.isLoading) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    if (this.container && this.container.isConnected === false) {
      this.stopPolling();
      return;
    }

    const status = getEasternMarketStatus();
    const isToday = !this.selectedDate || this.selectedDate === status.todayDateStr;
    if (!isToday || !status.isMarketHours) {
      this.checkAndStartPolling();
      return;
    }

    // If user is actively inspecting a candle bar, do not wipe out tooltip/crosshair
    if (this.candlestickChart && this.candlestickChart.hoveredIndex != null) {
      return;
    }

    try {
      await this.refreshLiveData();
    } catch (err) {
      console.warn('[LevelsView] Polling tick error:', err);
    }
  }

  async refreshLiveData() {
    let dataUrl = `/api/quant-levels/data?ticker=${this.ticker}`;
    if (this.selectedDate) {
      dataUrl += `&as_of_date=${encodeURIComponent(this.selectedDate)}`;
    }
    const resp = await fetchWithAuth(dataUrl);
    if (!resp || !resp.ok) return;
    const data = await resp.json();
    if (!data || data.status === 'empty' || !data.levels) return;

    this.currentData = data;
    const spot = data.spot_price;
    const isHistorical = data.spot_type === 'HISTORICAL_CLOSE';

    // Update Price Ladder rows in place
    const tbody = this.container?.querySelector?.('#priceLadderMount');
    if (tbody) {
      tbody.innerHTML = this.buildLadderHtml(data.levels, spot, isHistorical);
    }

    // Refresh candles and chart in place
    let candleUrl = `/api/quant-levels/candles?ticker=${this.ticker}`;
    const targetDate = data.as_of_date || this.selectedDate;
    if (targetDate) {
      candleUrl += `&as_of_date=${encodeURIComponent(targetDate)}`;
    }
    const candleResp = await fetchWithAuth(candleUrl);
    if (candleResp && candleResp.ok) {
      const cData = await candleResp.json();
      if (this.candlestickChart && cData.candles) {
        this.candlestickChart.updateData({
          candles: cData.candles,
          levels: data.levels,
          spot_price: spot,
          as_of_date: targetDate,
          ticker: this.ticker
        });
      }
    }
  }

  async loadCandlesData(levelsData) {
    const mount = this.container ? this.container.querySelector('#levelsCandlestickMount') : null;
    if (!mount) return;

    let url = `/api/quant-levels/candles?ticker=${this.ticker}`;
    const targetDate = levelsData?.as_of_date || this.selectedDate;
    if (targetDate) {
      url += `&as_of_date=${encodeURIComponent(targetDate)}`;
    }

    try {
      const resp = await fetchWithAuth(url);
      if (!resp || !resp.ok) {
        this.renderCandlesFallback(mount, `Failed to load candles: HTTP ${resp ? resp.status : 'offline'}`);
        return;
      }
      const candleResp = await resp.json();
      const candles = Array.isArray(candleResp.candles) ? candleResp.candles : [];

      if (this.candlestickChart) {
        this.candlestickChart.destroy();
        this.candlestickChart = null;
      }

      mount.innerHTML = '';
      this.candlestickChart = new CandlestickChart(mount, {
        candles,
        levels: levelsData.levels || [],
        spot_price: levelsData.spot_price,
        as_of_date: targetDate,
        ticker: this.ticker
      });
    } catch (err) {
      console.warn('[LevelsView] Failed to load candlestick chart:', err);
      this.renderCandlesFallback(mount, err.message || 'Network error fetching intraday candles.');
    }
  }

  renderCandlesFallback(mount, message) {
    if (!mount) return;
    mount.innerHTML = `
      <div class="candlestick-card fallback">
        <div class="candlestick-card-header">
          <span class="candlestick-badge">SPX 5M</span>
          <span class="candlestick-title">SPX Intraday Structure Chart</span>
        </div>
        <div class="candlestick-empty-overlay">
          <div class="candlestick-empty-icon">&#128200;</div>
          <div class="candlestick-empty-title">Intraday Data Unavailable</div>
          <div class="candlestick-empty-desc">${message || 'Session candles could not be loaded.'}</div>
        </div>
      </div>
    `;
  }

  calcDistanceSub(target, spot, direction) {
    if (target == null || spot == null || spot <= 0) return 'Relative to spot';
    const delta = target - spot;
    const deltaPct = ((delta / spot) * 100).toFixed(2);
    const sign = delta >= 0 ? '+' : '';
    return `${sign}${delta.toFixed(2)} pts (${sign}${deltaPct}%)`;
  }

  buildLadderHtml(levels, spot, isHistorical = false) {
    if (!levels || levels.length === 0) return '';

    let html = '';
    let spotInserted = false;

    // levels are sorted descending by start_price
    for (let i = 0; i < levels.length; i++) {
      const lvl = levels[i];
      const midPrice = lvl.end_price ? (lvl.start_price + lvl.end_price) / 2 : lvl.start_price;

      // Insert spot marker if spot is higher than current level and not yet inserted
      if (!spotInserted && spot != null && spot >= midPrice) {
        html += this.buildSpotMarkerHtml(spot, isHistorical);
        spotInserted = true;
      }

      html += this.buildLadderRowHtml(lvl);
    }

    // If spot was lower than all levels, insert at bottom
    if (!spotInserted && spot != null) {
      html += this.buildSpotMarkerHtml(spot, isHistorical);
    }

    return html;
  }

  buildSpotMarkerHtml(spot, isHistorical = false) {
    const markerClass = isHistorical ? 'ladder-table-spot-row historical' : 'ladder-table-spot-row';
    const labelText = isHistorical ? 'SPX SESSION CLOSE' : 'SPX LIVE SPOT';
    const formattedSpot = spot != null ? `$${spot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A';
    return `
      <tr class="${markerClass}" id="ladderSpotMarker">
        <td colspan="3">
          <div class="ladder-spot-marker-cell">
            <div class="spot-marker-label">
              <span class="spot-marker-pulse"></span>
              <span>${labelText}</span>
            </div>
            <div class="spot-marker-price">${formattedSpot}</div>
          </div>
        </td>
      </tr>
    `;
  }

  buildLadderRowHtml(lvl) {
    let typeTag = '';
    if (lvl.type === 'SELL') {
      typeTag = '<span class="ladder-tag tag-sell">SELL</span>';
    } else if (lvl.type === 'BUY') {
      typeTag = '<span class="ladder-tag tag-buy">BUY</span>';
    } else {
      // PIVOT or any other category is completely removed and left blank
      typeTag = '';
    }

    const immRes = lvl.is_immediate_resistance ? ' <span class="ladder-tag tag-sell imm-badge">IMM RES</span>' : '';
    const immSup = lvl.is_immediate_support ? ' <span class="ladder-tag tag-buy imm-badge">IMM SUP</span>' : '';
    const immClass = lvl.is_immediate_resistance ? 'immediate-res' : lvl.is_immediate_support ? 'immediate-sup' : '';
    const commentText = sanitizeComment(lvl.comments || lvl.comment || lvl.COMMENTS);

    return `
      <tr class="ladder-table-row ${immClass}" data-start-price="${lvl.start_price}">
        <td>${typeTag}</td>
        <td><strong class="ladder-price">${lvl.price_display}</strong>${immRes}${immSup}</td>
        <td class="ladder-comment-text">${commentText || '—'}</td>
      </tr>
    `;
  }

  buildTableRowHtml(lvl) {
    return this.buildLadderRowHtml(lvl);
  }

  renderEmptyState(mount, msg) {
    if (this.selectedDate) {
      mount.innerHTML = `
        <div class="levels-empty-state">
          <p class="levels-empty-title">No SPX Levels Recorded for ${this.selectedDate}</p>
          <p class="levels-empty-desc">${msg}</p>
          <div class="levels-extract-action-box">
            <button class="levels-refresh-btn levels-extract-btn" id="levelsExtractTargetBtn" style="margin: 0 auto;">
              <span>Extract Quant Levels for ${this.selectedDate}</span>
            </button>
            <div class="levels-extract-status" id="levelsExtractStatus" style="display: none; margin-top: 0.75rem;"></div>
          </div>
        </div>
      `;

      const extractBtn = mount.querySelector('#levelsExtractTargetBtn');
      const statusDiv = mount.querySelector('#levelsExtractStatus');
      if (extractBtn) {
        extractBtn.addEventListener('click', async () => {
          extractBtn.disabled = true;
          extractBtn.innerHTML = `
            <span class="candlestick-pulse-spinner" style="display:inline-block; vertical-align:middle; width:12px; height:12px; margin-right:6px;"></span>
            <span>Extracting Quant Levels for ${this.selectedDate}...</span>
          `;
          if (statusDiv) {
            statusDiv.style.display = 'block';
            statusDiv.style.color = '#38bdf8';
            statusDiv.textContent = `Running targeted ingestion pipeline for ${this.selectedDate}...`;
          }

          try {
            const resp = await fetchWithAuth(`/api/quant-levels/extract-date?target_date=${encodeURIComponent(this.selectedDate)}`, {
              method: 'POST'
            });
            if (resp && resp.ok) {
              const result = await resp.json().catch(() => ({}));
              if (statusDiv) {
                statusDiv.style.color = '#4ade80';
                statusDiv.textContent = result.message || `Successfully ingested levels for ${this.selectedDate}. Reloading...`;
              }
              await this.loadInitialData();
            } else {
              let errDetail = 'Extraction failed. Ensure Trading Edge session post exists.';
              try {
                const errJson = await resp.json();
                if (errJson && (errJson.detail || errJson.message)) {
                  errDetail = errJson.detail || errJson.message;
                }
              } catch (_) {}
              if (statusDiv) {
                statusDiv.style.color = '#f87171';
                statusDiv.textContent = `Error: ${errDetail}`;
              }
              extractBtn.disabled = false;
              extractBtn.innerHTML = `<span>Retry Extraction for ${this.selectedDate}</span>`;
            }
          } catch (e) {
            if (statusDiv) {
              statusDiv.style.color = '#f87171';
              statusDiv.textContent = `Network error: ${e.message}`;
            }
            extractBtn.disabled = false;
            extractBtn.innerHTML = `<span>Retry Extraction for ${this.selectedDate}</span>`;
          }
        });
      }
    } else {
      mount.innerHTML = `
        <div class="levels-empty-state">
          <p class="levels-empty-title">No SPX Levels Available</p>
          <p class="levels-empty-desc">${msg}</p>
          <button class="levels-refresh-btn" id="levelsEmptySyncBtn" style="margin: 0 auto;">
            <span>Trigger SPX Levels Ingestion</span>
          </button>
        </div>
      `;

      const syncBtn = mount.querySelector('#levelsEmptySyncBtn');
      if (syncBtn) {
        syncBtn.addEventListener('click', async () => {
          syncBtn.disabled = true;
          syncBtn.innerHTML = '<span>Triggering Ingestion...</span>';
          try {
            const resp = await fetchWithAuth('/api/quant-levels/sync', { method: 'POST' });
            if (resp && resp.ok) {
              await this.loadInitialData();
            } else {
              alert('Sync failed. Please check backend logs or authorization.');
            }
          } catch (e) {
            alert(`Sync error: ${e.message}`);
          }
        });
      }
    }
  }

  renderErrorState(mount, err) {
    mount.innerHTML = `
      <div class="levels-empty-state">
        <p class="levels-empty-title" style="color: #f87171;">Failed to Load SPX Levels</p>
        <p class="levels-empty-desc">${err}</p>
        <button class="levels-refresh-btn" id="levelsRetryBtn" style="margin: 0 auto;">
          <span>Retry Connection</span>
        </button>
      </div>
    `;

    const retryBtn = mount.querySelector('#levelsRetryBtn');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => this.loadInitialData());
    }
  }
}
