import { fetchWithAuth } from '../state.js?v=30';
import { CandlestickChart } from '../components/candlestick_chart.js?v=36';
import { LevelsView } from './levels_view.js?v=36';
import { MacroView } from './macro_view.js?v=36';

const STORAGE_KEY = 'quant_overview_tickers';
const DEFAULT_TICKERS = ['SPX', 'NDX', 'VIX', 'QQQ'];
const MAX_TICKERS = 12;

export class OverviewView {
  constructor() {
    this.container = null;
    this.timeframe = 'intraday'; // 'intraday' | 'daily'
    this.tickers = this.loadSavedTickers();
    this.charts = new Map();
    this.spxLevelsData = null;
    this.isLoading = false;

    this.levelsView = new LevelsView({
      hideCandlestick: true,
      onLevelsLoaded: (data) => {
        this.spxLevelsData = data;
        const spxChart = this.charts.get('SPX');
        if (spxChart && this.timeframe === 'intraday' && data) {
          spxChart.updateData({
            levels: data.levels || [],
            spot_price: data.spot_price != null ? data.spot_price : spxChart.spotPrice
          });
        }
      }
    });
    this.macroView = new MacroView();
  }

  loadSavedTickers() {
    try {
      const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed
            .map((t) => String(t).trim().toUpperCase())
            .filter((t) => /^[A-Z0-9^.=_-]{1,12}$/.test(t))
            .slice(0, MAX_TICKERS);
        }
      }
    } catch (e) {
      // Ignore storage errors
    }
    return [...DEFAULT_TICKERS];
  }

  saveTickers() {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.tickers));
      }
    } catch (e) {
      // Ignore storage errors
    }
  }

  render(container) {
    this.container = container;
    this.destroyCharts();

    this.container.innerHTML = `
      <div class="overview-container" id="overviewContainer">
        <!-- Top Toolbar: Timeframe Toggle + Customizable Ticker Chips -->
        <div class="overview-toolbar">
          <div class="overview-toolbar-row">
            <div class="overview-tf-toggle" role="group" aria-label="Chart Timeframe">
              <button type="button" class="overview-tf-btn ${this.timeframe === 'intraday' ? 'active' : ''}" data-tf="intraday">
                Intraday (5m + VWAP)
              </button>
              <button type="button" class="overview-tf-btn ${this.timeframe === 'daily' ? 'active' : ''}" data-tf="daily">
                Daily (6M)
              </button>
            </div>
            <button type="button" class="overview-refresh-btn" id="overviewRefreshBtn" title="Refresh Market Charts">
              ↻ Refresh
            </button>
          </div>

          <div class="overview-tickers-bar">
            <div class="overview-chips-list" id="overviewChipsList"></div>
            <form class="overview-add-form" id="overviewAddForm">
              <input
                type="text"
                class="overview-add-input"
                id="overviewAddInput"
                placeholder="+ Add ticker (e.g. SPY)"
                maxlength="12"
                aria-label="Add Ticker"
              />
              <button type="submit" class="overview-add-btn" id="overviewAddBtn">Add</button>
            </form>
          </div>
        </div>

        <!-- 2x2 Responsive Candlestick Grid -->
        <div class="overview-charts-grid" id="overviewChartsGrid"></div>

        <!-- Integrated SPX Quant Levels -->
        <section class="overview-section" id="overviewLevelsSection">
          <div id="overviewLevelsMount"></div>
        </section>

        <!-- Integrated Economic Events -->
        <section class="overview-section" id="overviewMacroSection">
          <div id="overviewMacroMount"></div>
        </section>
      </div>
    `;

    this.renderTickerChips();
    this.bindEvents();

    const levelsMount = this.container.querySelector('#overviewLevelsMount');
    if (levelsMount) {
      this.levelsView.render(levelsMount);
    }

    const macroMount = this.container.querySelector('#overviewMacroMount');
    if (macroMount) {
      this.macroView.render(macroMount);
    }

    this.loadCharts();
  }

  renderTickerChips() {
    const list = this.container ? this.container.querySelector('#overviewChipsList') : null;
    if (!list) return;

    list.innerHTML = this.tickers.map((ticker) => `
      <span class="overview-ticker-chip" data-ticker="${ticker}">
        <span class="chip-symbol">${ticker}</span>
        ${this.tickers.length > 1 ? `<button type="button" class="chip-remove-btn" data-remove="${ticker}" aria-label="Remove ${ticker}">&times;</button>` : ''}
      </span>
    `).join('');

    list.querySelectorAll('.chip-remove-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const target = e.currentTarget.getAttribute('data-remove');
        this.removeTicker(target);
      });
    });
  }

  bindEvents() {
    if (!this.container) return;

    const tfBtns = this.container.querySelectorAll('.overview-tf-btn');
    tfBtns.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const nextTf = e.currentTarget.getAttribute('data-tf');
        if (!nextTf || nextTf === this.timeframe) return;
        this.timeframe = nextTf;
        tfBtns.forEach((b) => b.classList.toggle('active', b.getAttribute('data-tf') === nextTf));
        this.loadCharts();
      });
    });

    const refreshBtn = this.container.querySelector('#overviewRefreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => this.loadCharts());
    }

    const addForm = this.container.querySelector('#overviewAddForm');
    const addInput = this.container.querySelector('#overviewAddInput');
    if (addForm && addInput) {
      addForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.addTicker(addInput.value);
        addInput.value = '';
      });
    }
  }

  addTicker(rawTicker) {
    const clean = String(rawTicker || '').trim().toUpperCase();
    if (!clean || !/^[A-Z0-9^.=_-]{1,12}$/.test(clean)) return;
    if (this.tickers.includes(clean)) return;
    if (this.tickers.length >= MAX_TICKERS) return;

    this.tickers.push(clean);
    this.saveTickers();
    this.renderTickerChips();
    this.loadCharts();
  }

  removeTicker(ticker) {
    if (this.tickers.length <= 1) return;
    this.tickers = this.tickers.filter((t) => t !== ticker);
    this.saveTickers();
    this.renderTickerChips();
    this.loadCharts();
  }

  destroyCharts() {
    this.charts.forEach((chart) => {
      if (chart && typeof chart.destroy === 'function') {
        chart.destroy();
      }
    });
    this.charts.clear();
  }

  async loadCharts() {
    const grid = this.container ? this.container.querySelector('#overviewChartsGrid') : null;
    if (!grid || this.tickers.length === 0) return;

    this.isLoading = true;
    this.destroyCharts();

    grid.innerHTML = this.tickers.map((t) => `
      <div class="overview-chart-slot" id="overviewSlot_${t.replace(/[^A-Z0-9]/g, '_')}">
        <div class="candlestick-loading-placeholder">
          <div class="candlestick-pulse-spinner"></div>
          <span>Loading ${t} (${this.timeframe === 'daily' ? 'Daily 6M' : 'Intraday 5m + VWAP'})...</span>
        </div>
      </div>
    `).join('');

    try {
      const qs = new URLSearchParams({
        tickers: this.tickers.join(','),
        timeframe: this.timeframe
      });
      const resp = await fetchWithAuth(`/api/market/candles?${qs.toString()}`);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      const results = Array.isArray(data.results) ? data.results : [];

      for (const item of results) {
        const slotId = `overviewSlot_${item.ticker.replace(/[^A-Z0-9]/g, '_')}`;
        const slot = grid.querySelector(`#${slotId}`);
        if (!slot) continue;
        slot.innerHTML = '';

        const isSpxIntraday = item.ticker === 'SPX' && this.timeframe === 'intraday';
        const levels = isSpxIntraday && this.spxLevelsData ? (this.spxLevelsData.levels || []) : [];
        const spot = isSpxIntraday && this.spxLevelsData && this.spxLevelsData.spot_price != null
          ? this.spxLevelsData.spot_price
          : item.spot_price;

        const chart = new CandlestickChart(slot, {
          ticker: item.ticker,
          timeframe: this.timeframe,
          showVwap: this.timeframe === 'intraday',
          candles: item.candles || [],
          levels,
          spot_price: spot,
          as_of_date: item.as_of_date || ''
        });
        this.charts.set(item.ticker, chart);
      }
    } catch (err) {
      grid.innerHTML = `
        <div class="candlestick-card fallback" style="grid-column: 1 / -1;">
          <div class="candlestick-empty-overlay">
            <div class="candlestick-empty-icon">&#128200;</div>
            <div class="candlestick-empty-title">Market Charts Unavailable</div>
            <div class="candlestick-empty-desc">Unable to load ${this.timeframe} market data (${err.message}).</div>
          </div>
        </div>
      `;
    } finally {
      this.isLoading = false;
    }
  }
}
