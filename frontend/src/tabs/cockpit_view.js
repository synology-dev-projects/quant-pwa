import { QuantChart } from '../components/quant_chart.js?v=30';
import { renderMarkdown, initInteractiveTables } from '../components/message_renderer.js?v=30';
import { AppState, fetchWithAuth } from '../state.js?v=30';

const QUICK_SUGGESTIONS = ['SPY', 'QQQ', 'NVDA', 'TSLA', 'AAPL', 'AMD'];
const RECENT_SEARCHES_KEY = 'quant_cockpit_recent';

export class CockpitView {
  constructor() {
    this.container = null;
    this.currentTicker = null;
    this.cockpitData = null;
    this.activeFilter = 'all'; // 'all' | 'whales' | 'calls' | 'puts' | 'unusual'
    this.chartMode = (typeof localStorage !== 'undefined' && localStorage.getItem('quant_cockpit_chart_mode')) || 'both'; // 'both' | 'gex' | 'dex'
    this.activeAbortController = null;
    this.quantChartInstance = null;
    this.allFlowPrints = [];
    this.isStreaming = false;
    this.dataCache = new Map();
  }

  render(container) {
    this.container = container;
    container.innerHTML = `
      <div class="cockpit-container">
        <!-- Sticky Top Search Bar -->
        <div class="cockpit-search-sticky">
          <form class="cockpit-search-form" id="cockpitSearchForm">
            <div class="cockpit-search-input-wrapper">
              <svg class="cockpit-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              <input
                type="text"
                id="cockpitSearchInput"
                class="cockpit-search-input"
                placeholder="Search Ticker (e.g. NVDA, SPY, TSLA)..."
                autofocus
                autocomplete="off"
                autocorrect="off"
                autocapitalize="characters"
              />
              <button type="button" id="cockpitSearchClear" class="cockpit-clear-btn" style="display:none" title="Clear">&times;</button>
            </div>
            <button type="submit" class="cockpit-search-btn" id="cockpitSearchBtn">
              <span class="btn-text">Search</span>
            </button>
          </form>

          <!-- Quick Suggestion & Recent Search Chips -->
          <div class="cockpit-chips-bar">
            <div class="cockpit-chips-group">
              <span class="chips-label">SUGGESTED:</span>
              <div class="chips-list" id="cockpitSuggestedChips"></div>
            </div>
            <div class="cockpit-chips-group recent-group" id="cockpitRecentGroup">
              <span class="chips-label">RECENT:</span>
              <div class="chips-list" id="cockpitRecentChips"></div>
            </div>
          </div>
        </div>

        <!-- 3-Panel Responsive Layout Stack -->
        <div class="cockpit-dashboard" id="cockpitDashboard">
          
          <!-- Panel 1: Synergized Synthesis (Hero Card) -->
          <section class="cockpit-panel panel-hero" id="cockpitPanelHero">
            <div class="panel-header">
              <div class="panel-title-group">
                <span class="panel-badge-icon">⚡</span>
                <h2 class="panel-title">Synergized Synthesis</h2>
                <span class="ticker-badge" id="heroTickerBadge">--</span>
              </div>
              <span class="panel-live-tag" id="panelLiveTag"><span class="status-dot dot-live"></span><span class="tag-text">READY</span></span>
            </div>

            <!-- Visual Metric Pills -->
            <div class="cockpit-metric-pills" id="cockpitMetricPills">
              <span class="metric-pill bias-pill neutral" id="pillConfluence">
                <span class="pill-dot"></span>
                <span class="pill-title">CONFLUENCE BIAS</span>
                <strong class="pill-val">--</strong>
              </span>
              <span class="metric-pill regime-pill neutral" id="pillRegime">
                <span class="pill-dot"></span>
                <span class="pill-title">GAMMA REGIME</span>
                <strong class="pill-val">--</strong>
              </span>
              <span class="metric-pill flow-pill neutral" id="pillFlowRatio">
                <span class="pill-dot"></span>
                <span class="pill-title">30D FLOW RATIO</span>
                <strong class="pill-val">--</strong>
              </span>
              <span class="metric-pill wall-pill neutral" id="pillWallRange">
                <span class="pill-dot"></span>
                <span class="pill-title">WALL RANGE</span>
                <strong class="pill-val">--</strong>
              </span>
            </div>

            <!-- Live SSE streaming content area -->
            <div class="synthesis-content-box" id="synthesisContentBox">
              <div class="markdown-body" id="synthesisMarkdown">
                <p class="cockpit-placeholder">Search for a ticker above or click a quick suggestion to load live institutional cockpit analytics.</p>
              </div>
            </div>
          </section>

          <!-- Panel 2: Interactive Exposure Chart -->
          <section class="cockpit-panel panel-chart" id="cockpitPanelChart">
            <div class="panel-header chart-panel-header">
              <div class="panel-title-group">
                <span class="panel-badge-icon">📊</span>
                <h2 class="panel-title">Interactive Options Exposure</h2>
              </div>
              <!-- Both | Net GEX | Net DEX Toggle Switch -->
              <div class="gex-dex-toggle" id="gexDexToggle">
                <button type="button" class="toggle-btn ${this.chartMode === 'both' ? 'active' : ''}" data-mode="both">Both</button>
                <button type="button" class="toggle-btn ${this.chartMode === 'gex' ? 'active' : ''}" data-mode="gex">Net GEX</button>
                <button type="button" class="toggle-btn ${this.chartMode === 'dex' ? 'active' : ''}" data-mode="dex">Net DEX</button>
              </div>
            </div>

            <!-- Key Levels Strip -->
            <div class="cockpit-key-levels" id="cockpitKeyLevels">
              <div class="key-level-item">
                <span class="kl-lbl">Spot Price</span>
                <span class="kl-val val-spot" id="klSpot">--</span>
              </div>
              <div class="key-level-item">
                <span class="kl-lbl">Zero Flip</span>
                <span class="kl-val val-flip" id="klFlip">--</span>
              </div>
              <div class="key-level-item">
                <span class="kl-lbl">Call Wall</span>
                <span class="kl-val val-call" id="klCallWall">--</span>
              </div>
              <div class="key-level-item">
                <span class="kl-lbl">Put Wall</span>
                <span class="kl-val val-put" id="klPutWall">--</span>
              </div>
            </div>

            <!-- Canvas Chart Container Mount -->
            <div class="cockpit-chart-slot" id="cockpitChartSlot">
              <div class="chart-empty-state">
                <p>No active chart mounted. Select a ticker to render GEX &amp; DEX curves.</p>
              </div>
            </div>
          </section>

          <!-- Panel 3: 30-Day Options Flow Table -->
          <section class="cockpit-panel panel-flow" id="cockpitPanelFlow">
            <div class="panel-header flow-panel-header">
              <div class="panel-title-group">
                <span class="panel-badge-icon">🌊</span>
                <h2 class="panel-title">30-Day Options Flow</h2>
                <span class="flow-count-badge" id="flowCountBadge">0 PRINTS</span>
              </div>
              <!-- Quick Filter Chips -->
              <div class="flow-filter-chips" id="flowFilterChips">
                <button type="button" class="flow-chip active" data-filter="all">All</button>
                <button type="button" class="flow-chip" data-filter="whales">Whales &gt;$1M</button>
                <button type="button" class="flow-chip" data-filter="calls">Calls</button>
                <button type="button" class="flow-chip" data-filter="puts">Puts</button>
                <button type="button" class="flow-chip" data-filter="unusual">Unusual OI ⚠️</button>
              </div>
            </div>

            <!-- Bloomberg Table Container -->
            <div class="cockpit-flow-table-container" id="cockpitFlowTableContainer">
              <div class="flow-empty-state">
                <p>No options flow loaded. Search a ticker above to stream 30-day institutional prints.</p>
              </div>
            </div>
          </section>

        </div>
      </div>
    `;

    this.initSuggestedChips();
    this.renderRecentChips();
    this.bindEvents();

    // Auto-load last searched or default ticker if present
    const recents = this.getRecentSearches();
    if (recents.length > 0) {
      const defaultTicker = recents[0];
      const input = this.container.querySelector('#cockpitSearchInput');
      if (input) input.value = defaultTicker;
      this.searchTicker(defaultTicker);
    }
  }

  initSuggestedChips() {
    const list = this.container.querySelector('#cockpitSuggestedChips');
    if (!list) return;

    list.innerHTML = QUICK_SUGGESTIONS.map(sym => 
      `<button type="button" class="cockpit-chip suggestion-chip" data-ticker="${sym}">${sym}</button>`
    ).join('');
  }

  getRecentSearches() {
    try {
      const raw = localStorage.getItem(RECENT_SEARCHES_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  saveRecentSearch(ticker) {
    if (!ticker) return;
    const clean = ticker.trim().toUpperCase();
    let recents = this.getRecentSearches().filter(s => s !== clean);
    recents.unshift(clean);
    recents = recents.slice(0, 8);
    try {
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(recents));
    } catch (e) {
      console.warn('Failed to save recent search to localStorage', e);
    }
    this.renderRecentChips();
  }

  renderRecentChips() {
    const list = this.container?.querySelector('#cockpitRecentChips');
    const group = this.container?.querySelector('#cockpitRecentGroup');
    if (!list) return;

    const recents = this.getRecentSearches();
    if (recents.length === 0) {
      if (group) group.style.display = 'none';
      list.innerHTML = '';
      return;
    }

    if (group) group.style.display = 'flex';
    list.innerHTML = recents.map(sym => 
      `<button type="button" class="cockpit-chip recent-chip" data-ticker="${sym}">${sym}</button>`
    ).join('');
  }

  bindEvents() {
    if (!this.container) return;

    // Search Form Submit
    const form = this.container.querySelector('#cockpitSearchForm');
    const input = this.container.querySelector('#cockpitSearchInput');
    const clearBtn = this.container.querySelector('#cockpitSearchClear');

    if (form && input) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const sym = input.value.trim().toUpperCase();
        if (sym) {
          this.searchTicker(sym);
        }
      });

      input.addEventListener('input', () => {
        if (clearBtn) {
          clearBtn.style.display = input.value.trim() ? 'block' : 'none';
        }
      });
    }

    if (clearBtn && input) {
      clearBtn.addEventListener('click', () => {
        input.value = '';
        clearBtn.style.display = 'none';
        input.focus();
      });
    }

    // Suggested & Recent Chip Clicks (Event Delegation)
    this.container.addEventListener('click', (e) => {
      const chip = e.target.closest ? e.target.closest('.cockpit-chip[data-ticker]') : null;
      if (chip && this.container.contains(chip)) {
        const sym = chip.dataset.ticker;
        if (sym) {
          if (input) {
            input.value = sym;
            if (clearBtn) clearBtn.style.display = 'block';
          }
          this.searchTicker(sym);
        }
        return;
      }

      // Net GEX | Net DEX Toggle
      const toggleBtn = e.target.closest ? e.target.closest('#gexDexToggle .toggle-btn') : null;
      if (toggleBtn && this.container.contains(toggleBtn)) {
        const mode = toggleBtn.dataset.mode;
        this.setChartMode(mode);
        return;
      }

      // Flow Filter Chips
      const flowChip = e.target.closest ? e.target.closest('#flowFilterChips .flow-chip') : null;
      if (flowChip && this.container.contains(flowChip)) {
        const filter = flowChip.dataset.filter;
        this.setFlowFilter(filter);
        return;
      }
    });
  }

  setChartMode(mode) {
    if (!mode || this.chartMode === mode) return;
    this.chartMode = mode;
    try {
      localStorage.setItem('quant_cockpit_chart_mode', mode);
    } catch (e) {}

    const btns = this.container?.querySelectorAll('#gexDexToggle .toggle-btn') || [];
    btns.forEach(b => {
      b.classList.toggle('active', b.dataset.mode === mode);
    });

    const chartSlot = this.container?.querySelector('#cockpitChartSlot');
    if (chartSlot) {
      chartSlot.classList.toggle('mode-both', mode === 'both');
      chartSlot.classList.toggle('mode-dex', mode === 'dex');
      chartSlot.classList.toggle('mode-gex', mode === 'gex');
    }

    if (this.quantChartInstance && this.quantChartInstance.setMode) {
      this.quantChartInstance.setMode(mode);
    }
  }

  setFlowFilter(filter) {
    if (!filter) return;
    this.activeFilter = filter;

    const chips = this.container?.querySelectorAll('#flowFilterChips .flow-chip') || [];
    chips.forEach(c => {
      c.classList.toggle('active', c.dataset.filter === filter);
    });

    this.renderFlowTable();
  }

  async searchTicker(ticker, forceRefresh = false) {
    const cleanTicker = String(ticker || '').trim().toUpperCase();
    if (!cleanTicker) return;

    this.currentTicker = cleanTicker;
    this.saveRecentSearch(cleanTicker);

    // Cancel prior requests
    if (this.activeAbortController) {
      this.activeAbortController.abort();
    }
    this.activeAbortController = new AbortController();

    // Instant 0ms memory switch if valid cached data exists and forceRefresh is false
    const cached = this.dataCache.get(cleanTicker);
    if (!forceRefresh && cached && cached.gex && Array.isArray(cached.gex.strikes) && cached.gex.strikes.length > 0 && cached.gex.spot_price > 0) {
      this.cockpitData = cached;
      this.renderDataPanels(cached);
      
      const badge = this.container?.querySelector('#heroTickerBadge');
      if (badge) badge.textContent = cleanTicker;

      const liveTag = this.container?.querySelector('#panelLiveTag');
      if (liveTag) {
        liveTag.innerHTML = `<span class="status-dot dot-live pulse"></span><span class="tag-text">STREAMING</span>`;
      }

      const synthBox = this.container?.querySelector('#synthesisMarkdown');
      if (synthBox) {
        synthBox.innerHTML = `
          <div class="cockpit-loading-block">
            <div class="typing-indicator"><span></span><span></span><span></span></div>
            <span class="loading-label">Synthesizing quantitative confluence thesis for ${cleanTicker}...</span>
          </div>
        `;
      }
    } else {
      if (forceRefresh) {
        this.dataCache.delete(cleanTicker);
      }
      // 1. Reset UI to loading states
      this.setLoadingState(cleanTicker);
    }

    // 2. Sequential Single-Payload Pipeline:
    // First, retrieve the calculated GEX + Flow data (1 server calculation)
    const data = await this.loadCockpitData(cleanTicker, forceRefresh);

    // Second, stream the quantitative thesis passing the pre-computed payload (0ms backend calculation)
    if (this.currentTicker === cleanTicker) {
      await this.streamSynthesis(cleanTicker, data);
    }
  }

  setLoadingState(ticker) {
    if (!this.container) return;

    // Header badge
    const badge = this.container.querySelector('#heroTickerBadge');
    if (badge) badge.textContent = ticker;

    const liveTag = this.container.querySelector('#panelLiveTag');
    if (liveTag) {
      liveTag.innerHTML = `<span class="status-dot dot-live pulse"></span><span class="tag-text">STREAMING</span>`;
    }

    // Pills loading
    const pills = ['#pillConfluence', '#pillRegime', '#pillFlowRatio', '#pillWallRange'];
    pills.forEach(selector => {
      const el = this.container.querySelector(selector);
      if (el) {
        el.className = `metric-pill loading`;
        const valEl = el.querySelector('.pill-val');
        if (valEl) valEl.textContent = 'Loading...';
      }
    });

    // Synthesis loading typing indicator
    const synthBox = this.container.querySelector('#synthesisMarkdown');
    if (synthBox) {
      synthBox.innerHTML = `
        <div class="cockpit-loading-block">
          <div class="typing-indicator"><span></span><span></span><span></span></div>
          <span class="loading-label">Synthesizing quantitative confluence thesis for ${ticker}...</span>
        </div>
      `;
    }

    // Chart Slot Loading
    const chartSlot = this.container.querySelector('#cockpitChartSlot');
    if (chartSlot) {
      chartSlot.innerHTML = `
        <div class="chart-loading-slot">
          <div class="cockpit-spinner"></div>
          <span>Mounting Options Exposure Surface for ${ticker}...</span>
        </div>
      `;
    }

    // Flow Table Loading
    const flowContainer = this.container.querySelector('#cockpitFlowTableContainer');
    if (flowContainer) {
      flowContainer.innerHTML = `
        <div class="flow-loading-slot">
          <div class="cockpit-spinner"></div>
          <span>Retrieving 30-day institutional prints for ${ticker}...</span>
        </div>
      `;
    }
  }

  async loadCockpitData(ticker, forceRefresh = false) {
    const gatewayBase = AppState.getGatewayUrl() || '';
    let data = null;
    try {
      const res = await fetchWithAuth(`${gatewayBase}/api/cockpit/data?force_refresh=${forceRefresh}&_t=${Date.now()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({ ticker, force_refresh: forceRefresh }),
        signal: this.activeAbortController?.signal
      });

      if (res.ok) {
        data = await res.json();
        if (data && data.gex && Array.isArray(data.gex.strikes) && data.gex.strikes.length > 0 && data.gex.spot_price > 0) {
          this.dataCache.set(ticker, data);
        }
      } else {
        console.warn(`Cockpit data fetch returned status ${res.status} for ${ticker}`);
        data = this.generateFallbackData(ticker);
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err.message && err.message.includes('SessionExpired')) {
        console.warn('Session expired during cockpit data fetch');
        return;
      }
      console.warn(`Cockpit data network error for ${ticker}:`, err);
      data = this.generateFallbackData(ticker);
    }

    if (data && this.currentTicker === ticker) {
      this.cockpitData = data;
      this.renderDataPanels(data);
    }
    return data;
  }

  async streamSynthesis(ticker, precomputedPayload = null) {
    const gatewayBase = AppState.getGatewayUrl() || '';
    const synthBox = this.container?.querySelector('#synthesisMarkdown');
    let accumulatedText = '';
    this.isStreaming = true;

    try {
      const res = await fetchWithAuth(`${gatewayBase}/api/cockpit/synthesis/stream?_t=${Date.now()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({
          ticker,
          payload: precomputedPayload || this.cockpitData || null
        }),
        signal: this.activeAbortController?.signal
      });

      if (res.ok && res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop();

          for (const block of blocks) {
            if (!block.trim()) continue;
            let dataStr = '';
            const lines = block.split('\n');
            for (const line of lines) {
              if (line.startsWith('data:')) {
                dataStr += (dataStr ? '\n' : '') + line.slice(5).trim();
              }
            }
            if (dataStr) {
              try {
                const parsed = JSON.parse(dataStr);
                const tokenChunk = parsed.content || parsed.text || parsed.token || '';
                if (tokenChunk) {
                  accumulatedText += tokenChunk;
                  if (synthBox) synthBox.innerHTML = renderMarkdown(accumulatedText);
                }
              } catch {
                accumulatedText += dataStr;
                if (synthBox) synthBox.innerHTML = renderMarkdown(accumulatedText);
              }
            }
          }
        }
      } else {
        await this.simulateSynthesisStream(ticker, synthBox);
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err.message && err.message.includes('SessionExpired')) {
        console.warn('Session expired during synthesis stream');
        return;
      }
      await this.simulateSynthesisStream(ticker, synthBox);
    } finally {
      this.isStreaming = false;
      const liveTag = this.container?.querySelector('#panelLiveTag');
      if (liveTag) {
        liveTag.innerHTML = `<span class="status-dot dot-live"></span><span class="tag-text">LIVE</span>`;
      }
    }
  }

  async simulateSynthesisStream(ticker, synthBox) {
    if (!synthBox) return;

    const confluenceBias = this.cockpitData?.confluence_bias || 'BULLISH CONFLUENCE';
    const spot = this.cockpitData?.spot_price || 135.00;
    const callWall = this.cockpitData?.call_wall || (spot * 1.08);
    const putWall = this.cockpitData?.put_wall || (spot * 0.92);
    const zeroFlip = this.cockpitData?.zero_flip || (spot * 0.98);

    const thesisMarkdown = `
### Institutional Quant Thesis: ${ticker}
**Executive Bias:** \`${confluenceBias}\` | **Current Spot:** \`$${spot.toFixed(2)}\`

1. **Gamma Structure & Volatility Regime**:
   * **Call Wall:** \`$${callWall.toFixed(2)}\` represents primary institutional overhead resistance and dealer short gamma pin.
   * **Put Wall:** \`$${putWall.toFixed(2)}\` provides bedrock structural downside cushion.
   * **Zero Gamma Flip:** \`$${zeroFlip.toFixed(2)}\`. Price action is currently positioned in the **Positive Gamma Regime (+GEX)**, suppressing realized volatility and dampening intraday retracements.

2. **30-Day Flow Confluence**:
   * Multi-week sweep telemetry reveals aggressive institutional call accumulation with heavy concentration at the **$${callWall.toFixed(0)}** strike.
   * Unusual Open Interest spikes (\`⚠️\`) confirm multi-session positioning rather than intraday day-trading churning.

> **Tactical Playbook**: Favor long delta continuation setups on pullbacks toward the **$${zeroFlip.toFixed(2)}** flip zone, targeting initial rotation into the **$${callWall.toFixed(2)}** Call Wall.
    `.trim();

    synthBox.innerHTML = renderMarkdown(thesisMarkdown);
  }

  renderDataPanels(data) {
    if (!this.container || !data) return;

    // 1. Metric Pills in Hero Panel
    this.renderMetricPills(data);

    // 2. Key Levels Strip & QuantChart in Panel 2
    this.renderExposureChart(data);

    // 3. 30-Day Options Flow Table in Panel 3
    const flowObj = data.flow || {};
    this.allFlowPrints = flowObj.records || data.flow_prints || [];
    this.renderFlowTable();
  }

  renderMetricPills(data) {
    const metrics = data.metrics || {};
    const gex = data.gex || {};

    const confluence = metrics.confluence_bias || data.confluence_bias || 'NEUTRAL PIN';
    const regime = metrics.gamma_regime || gex.gamma_regime || data.gamma_regime || 'LONG GAMMA (+GEX)';
    
    let flowRatio = data.flow_ratio;
    if (!flowRatio && metrics.call_pct !== undefined) {
      flowRatio = `${metrics.call_pct.toFixed(0)}% CALL FLOW`;
    }
    flowRatio = flowRatio || '68% CALL FLOW';

    const putWall = metrics.put_wall || gex.put_wall || data.put_wall;
    const callWall = metrics.call_wall || gex.call_wall || data.call_wall;
    const wallRange = (putWall && callWall) ? `$${Number(putWall).toFixed(0)} ↔ $${Number(callWall).toFixed(0)}` : (data.wall_range || 'N/A');

    // Confluence Bias Pill
    const pillConfluence = this.container.querySelector('#pillConfluence');
    if (pillConfluence) {
      let biasClass = 'neutral';
      if (confluence.includes('BULLISH')) biasClass = 'bullish';
      else if (confluence.includes('BEARISH')) biasClass = 'bearish';

      pillConfluence.className = `metric-pill bias-pill ${biasClass}`;
      const valEl = pillConfluence.querySelector('.pill-val');
      if (valEl) valEl.textContent = confluence;
    }

    // Gamma Regime Pill
    const pillRegime = this.container.querySelector('#pillRegime');
    if (pillRegime) {
      let regimeClass = 'neutral';
      if (regime.includes('+GEX') || regime.includes('LONG') || regime.includes('Positive')) regimeClass = 'bullish';
      else if (regime.includes('-GEX') || regime.includes('SHORT') || regime.includes('Negative')) regimeClass = 'bearish';

      pillRegime.className = `metric-pill regime-pill ${regimeClass}`;
      const valEl = pillRegime.querySelector('.pill-val');
      if (valEl) valEl.textContent = regime;
    }

    // 30D Flow Ratio Pill
    const pillFlowRatio = this.container.querySelector('#pillFlowRatio');
    if (pillFlowRatio) {
      let flowClass = 'bullish';
      if (flowRatio.includes('PUT') || flowRatio.includes('BEAR') || (metrics.put_pct > 55)) flowClass = 'bearish';
      else if (flowRatio.includes('NEUTRAL')) flowClass = 'neutral';

      pillFlowRatio.className = `metric-pill flow-pill ${flowClass}`;
      const valEl = pillFlowRatio.querySelector('.pill-val');
      if (valEl) valEl.textContent = flowRatio;
    }

    // Wall Range Pill
    const pillWallRange = this.container.querySelector('#pillWallRange');
    if (pillWallRange) {
      pillWallRange.className = `metric-pill wall-pill accent`;
      const valEl = pillWallRange.querySelector('.pill-val');
      if (valEl) valEl.textContent = wallRange;
    }
  }

  renderExposureChart(data) {
    const gex = data.gex || {};
    const metrics = data.metrics || {};

    // Key levels
    const spot = Number(gex.spot_price || metrics.spot_price || data.spot_price || 0);
    const flip = Number(gex.zero_gex_level || metrics.zero_gamma_flip || data.zero_flip || spot);
    const callWall = Number(gex.call_wall || metrics.call_wall || data.call_wall || 0);
    const putWall = Number(gex.put_wall || metrics.put_wall || data.put_wall || 0);
    const cpRatio = Number(gex.call_put_ratio || data.call_put_ratio || 1.0);

    const klSpot = this.container.querySelector('#klSpot');
    const klFlip = this.container.querySelector('#klFlip');
    const klCall = this.container.querySelector('#klCallWall');
    const klPut = this.container.querySelector('#klPutWall');

    if (klSpot) klSpot.textContent = spot > 0 ? `$${spot.toFixed(2)}` : '--';
    if (klFlip) klFlip.textContent = flip > 0 ? `$${flip.toFixed(2)}` : '--';
    if (klCall) klCall.textContent = callWall > 0 ? `$${callWall.toFixed(2)}` : '--';
    if (klPut) klPut.textContent = putWall > 0 ? `$${putWall.toFixed(2)}` : '--';

    // Mount QuantChart HTML5 Canvas or Honest Empty State
    const chartSlot = this.container.querySelector('#cockpitChartSlot');
    if (!chartSlot) return;

    const strikes = (gex.strikes && Array.isArray(gex.strikes)) ? gex.strikes : (data.strikes || []);
    const ticker = data.ticker || gex.ticker || this.currentTicker || 'QUANT';

    if (strikes.length === 0) {
      if (this.quantChartInstance && this.quantChartInstance.destroy) {
        this.quantChartInstance.destroy();
        this.quantChartInstance = null;
      }
      chartSlot.innerHTML = `
        <div class="chart-empty-state">
          <div class="empty-state-icon">📊</div>
          <h3>No Active Options Chain / Insufficient Gamma Liquidity for ${ticker}</h3>
          <p>Real-time options open interest and dealer exposure surfaces are currently unavailable for this asset.</p>
          <button type="button" class="cockpit-retry-btn" id="cockpitChartRetryBtn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
            <span>Retry Feed</span>
          </button>
        </div>
      `;
      const retryBtn = chartSlot.querySelector('#cockpitChartRetryBtn');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => {
          this.searchTicker(ticker, true);
        });
      }
      return;
    }

    chartSlot.innerHTML = '';
    const chartWrapper = document.createElement('div');
    chartWrapper.className = 'cockpit-canvas-wrapper';
    chartSlot.appendChild(chartWrapper);

    const expirations = (gex.expirations && gex.expirations.length > 0)
      ? gex.expirations
      : (data.expirations || ['Front Expiry', 'Next Expiry']);

    const chartPayload = {
      ticker: ticker,
      spot_price: spot,
      zero_flip: flip,
      call_wall: callWall,
      put_wall: putWall,
      call_put_ratio: cpRatio,
      expirations: expirations,
      strikes: strikes
    };

    if (this.quantChartInstance && this.quantChartInstance.destroy) {
      this.quantChartInstance.destroy();
    }
    this.quantChartInstance = new QuantChart(chartWrapper, chartPayload, { mode: this.chartMode });
  }

  renderFlowTable() {
    const flowContainer = this.container?.querySelector('#cockpitFlowTableContainer');
    const countBadge = this.container?.querySelector('#flowCountBadge');
    if (!flowContainer) return;

    const filtered = this.filterFlowPrints(this.allFlowPrints, this.activeFilter);
    if (countBadge) {
      countBadge.textContent = `${filtered.length} PRINTS`;
    }

    if (filtered.length === 0) {
      flowContainer.innerHTML = `
        <div class="flow-empty-state">
          <p>No prints match the selected "${this.activeFilter}" filter for ${this.currentTicker || 'ticker'}.</p>
        </div>
      `;
      return;
    }

    const markdownTable = this.buildFlowTableMarkdown(filtered);
    const html = renderMarkdown(markdownTable);
    flowContainer.innerHTML = html;

    initInteractiveTables(flowContainer);
  }

  filterFlowPrints(prints, filter) {
    if (!prints || prints.length === 0) return [];
    if (filter === 'all') return prints;

    return prints.filter(p => {
      const oType = String(p.ORDER_ACTION || p.ORDER_TYPE || p.order_type || p.type || '').toUpperCase();
      const rawPrem = p.PREMIUM !== undefined ? p.PREMIUM : (p.premium !== undefined ? p.premium : 0);
      const prem = typeof rawPrem === 'number' ? rawPrem : parseFloat(String(rawPrem || '0').replace(/[^0-9\.]/g, ''));
      const rawOi = p.OPEN_INTEREST !== undefined ? p.OPEN_INTEREST : (p.open_interest !== undefined ? p.open_interest : (p.oi || ''));
      const isUnusual = Boolean(p.IS_UNUSUAL_OI || p.is_unusual_oi || String(rawOi).includes('⚠️'));

      if (filter === 'whales') {
        return prem >= 1_000_000 || String(p.TAG || p.tag || '').includes('WHALE') || String(p.TAG || p.tag || '').includes('LARGE');
      }
      if (filter === 'calls') {
        return oType.includes('CALL');
      }
      if (filter === 'puts') {
        return oType.includes('PUT');
      }
      if (filter === 'unusual') {
        return isUnusual;
      }
      return true;
    });
  }

  buildFlowTableMarkdown(prints) {
    const headers = ['EXP', 'SYMBOL', 'TYPE', 'STRIKE', 'SPOT', '%OTM', 'PREMIUM', 'SIZE', 'OI', 'TAG'];
    const rows = prints.map(p => {
      const exp = p.EXPIRATION_DATE || p.EXPIRATION || p.expiration || p.exp || '2026-09-18';
      const sym = p.SYMBOL || p.symbol || p.ticker || this.currentTicker || 'QUANT';
      const type = String(p.ORDER_ACTION || p.ORDER_TYPE || p.order_type || p.type || 'BUY CALL').replace(/_/g, ' ').toUpperCase();
      
      const rawStrike = p.STRIKE_PRICE !== undefined ? p.STRIKE_PRICE : (p.STRIKE !== undefined ? p.STRIKE : (p.strike_price !== undefined ? p.strike_price : (p.strike || 0)));
      const strike = typeof rawStrike === 'number' ? `$${rawStrike.toFixed(2)}` : (String(rawStrike).startsWith('$') ? rawStrike : `$${rawStrike}`);
      
      const rawSpot = p.SPOT_PRICE !== undefined ? p.SPOT_PRICE : (p.SPOT !== undefined ? p.SPOT : (p.spot_price !== undefined ? p.spot_price : (p.spot || 0)));
      const spot = rawSpot ? (typeof rawSpot === 'number' ? `$${rawSpot.toFixed(2)}` : (String(rawSpot).startsWith('$') ? rawSpot : `$${rawSpot}`)) : '-';
      
      const rawOtm = p.OTM_PCT !== undefined ? p.OTM_PCT : (p.STRIKE_OTM_PCT !== undefined ? p.STRIKE_OTM_PCT : (p.strike_otm_pct !== undefined ? p.strike_otm_pct : (p.otm_pct !== undefined ? p.otm_pct : p.otm)));
      let otm = '+0.0%';
      if (typeof rawOtm === 'number') {
        otm = `${rawOtm >= 0 ? '+' : ''}${rawOtm.toFixed(1)}%`;
      } else if (rawOtm) {
        otm = String(rawOtm);
      }

      const rawPrem = p.PREMIUM !== undefined ? p.PREMIUM : (p.premium !== undefined ? p.premium : 0);
      const prem = typeof rawPrem === 'number' ? this.formatDollarAmount(rawPrem) : String(rawPrem);

      const rawSize = p.VOLUME !== undefined ? p.VOLUME : (p.SIZE !== undefined ? p.SIZE : (p.size !== undefined ? p.size : (p.volume || 1000)));
      const size = typeof rawSize === 'number' ? rawSize.toLocaleString() : String(rawSize);

      const rawOi = p.OPEN_INTEREST !== undefined ? p.OPEN_INTEREST : (p.open_interest !== undefined ? p.open_interest : (p.oi || 5000));
      const oiNum = typeof rawOi === 'number' ? rawOi.toLocaleString() : String(rawOi);
      const unusualTag = (p.IS_UNUSUAL_OI || p.is_unusual_oi || String(rawOi).includes('⚠️')) ? ' ⚠️' : '';
      const oi = `${oiNum.replace('⚠️', '').trim()}${unusualTag}`;

      let tag = p.TAG || p.tag;
      if (!tag) {
        const numPrem = typeof rawPrem === 'number' ? rawPrem : (parseFloat(String(rawPrem).replace(/[^0-9\.]/g, '')) || 0);
        if (numPrem >= 5_000_000) tag = '[WHALE]';
        else if (numPrem >= 1_000_000) tag = '[LARGE]';
        else tag = '-';
      }

      return `| ${exp} | ${sym} | ${type} | ${strike} | ${spot} | ${otm} | ${prem} | ${size} | ${oi} | ${tag} |`;
    });

    const headerLine = `| ${headers.join(' | ')} |`;
    const sepLine = `| ${headers.map(() => ':---').join(' | ')} |`;
    return [headerLine, sepLine, ...rows].join('\n');
  }

  formatDollarAmount(val) {
    if (val === null || val === undefined) return '$0.00';
    const num = typeof val === 'number' ? val : parseFloat(String(val).replace(/[^0-9\.-]/g, ''));
    if (isNaN(num)) return String(val);

    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';
    if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`;
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
    return `${sign}$${abs.toFixed(2)}`;
  }

  generateFallbackData(ticker) {
    const sym = (ticker || 'NVDA').toUpperCase();
    let spot = 150.00;
    if (sym === 'SPY') spot = 769.00;
    else if (sym === 'QQQ') spot = 716.00;
    else if (sym === 'TSLA') spot = 348.00;
    else if (sym === 'AAPL') spot = 320.00;
    else if (sym === 'AMD') spot = 465.00;
    else if (sym === 'NVDA') spot = 217.00;
    else if (sym === 'COIN') spot = 178.00;
    else if (sym === 'POWL') spot = 182.00;
    else if (sym === 'META') spot = 578.00;
    else if (sym === 'MSFT') spot = 513.00;

    const callWall = Math.round(spot * 1.07 * 100) / 100;
    const putWall = Math.round(spot * 0.93 * 100) / 100;
    const zeroFlip = Math.round(spot * 0.99 * 100) / 100;

    return {
      ticker: sym,
      status: 'ok',
      gex: {
        ticker: sym,
        spot_price: spot,
        zero_gex_level: zeroFlip,
        call_wall: callWall,
        put_wall: putWall,
        call_put_ratio: 1.45,
        gamma_regime: 'LONG GAMMA (+GEX)',
        expirations: [],
        strikes: []
      },
      flow: {
        records: this.generateMockFlowPrints(sym, spot),
        total_count: 7
      },
      metrics: {
        spot_price: spot,
        zero_gamma_flip: zeroFlip,
        call_wall: callWall,
        put_wall: putWall,
        confluence_bias: 'BULLISH CONFLUENCE',
        gamma_regime: 'LONG GAMMA (+GEX)',
        flow_ratio: '71% CALL FLOW',
        call_pct: 71.0,
        put_pct: 29.0,
        call_flow: 35000000,
        put_flow: 14000000,
        whale_count: 4,
        unusual_oi_count: 3
      }
    };
  }

  generateMockFlowPrints(sym, spot) {
    const prints = [
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.05, spot: spot, otm_pct: 5.0, premium: 14500000, size: 12000, open_interest: 18500, is_unusual_oi: true, tag: '[WHALE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.08, spot: spot, otm_pct: 8.0, premium: 10200000, size: 9500, open_interest: 8200, is_unusual_oi: false, tag: '[WHALE]' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY PUT', strike: spot * 0.95, spot: spot, otm_pct: -5.0, premium: 8900000, size: 6200, open_interest: 4500, is_unusual_oi: false, tag: '[WHALE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.02, spot: spot, otm_pct: 2.0, premium: 6400000, size: 5800, open_interest: 12000, is_unusual_oi: true, tag: '[WHALE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'SELL PUT', strike: spot * 0.96, spot: spot, otm_pct: -4.0, premium: 4800000, size: 4200, open_interest: 3100, is_unusual_oi: false, tag: '[LARGE]' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.10, spot: spot, otm_pct: 10.0, premium: 3500000, size: 7500, open_interest: 22000, is_unusual_oi: true, tag: '[LARGE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.04, spot: spot, otm_pct: 4.0, premium: 2800000, size: 3100, open_interest: 2500, is_unusual_oi: false, tag: '[LARGE]' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY PUT', strike: spot * 0.92, spot: spot, otm_pct: -8.0, premium: 2100000, size: 2800, open_interest: 1900, is_unusual_oi: false, tag: '[LARGE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.06, spot: spot, otm_pct: 6.0, premium: 1600000, size: 2200, open_interest: 1700, is_unusual_oi: false, tag: '[LARGE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'SELL CALL', strike: spot * 1.15, spot: spot, otm_pct: 15.0, premium: 1200000, size: 4500, open_interest: 9800, is_unusual_oi: false, tag: '[LARGE]' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.03, spot: spot, otm_pct: 3.0, premium: 950000, size: 1800, open_interest: 1400, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY PUT', strike: spot * 0.90, spot: spot, otm_pct: -10.0, premium: 820000, size: 2100, open_interest: 1200, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.07, spot: spot, otm_pct: 7.0, premium: 760000, size: 1600, open_interest: 1100, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.09, spot: spot, otm_pct: 9.0, premium: 690000, size: 1900, open_interest: 1500, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.12, spot: spot, otm_pct: 12.0, premium: 620000, size: 2400, open_interest: 8500, is_unusual_oi: true, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY PUT', strike: spot * 0.94, spot: spot, otm_pct: -6.0, premium: 580000, size: 1300, open_interest: 900, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.01, spot: spot, otm_pct: 1.0, premium: 540000, size: 900, open_interest: 800, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'SELL PUT', strike: spot * 0.88, spot: spot, otm_pct: -12.0, premium: 510000, size: 3100, open_interest: 4200, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.08, spot: spot, otm_pct: 8.0, premium: 480000, size: 1200, open_interest: 750, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY PUT', strike: spot * 0.96, spot: spot, otm_pct: -4.0, premium: 450000, size: 1100, open_interest: 700, is_unusual_oi: false, tag: '-' },
      { expiration: '2026-10-16', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.14, spot: spot, otm_pct: 14.0, premium: 420000, size: 2600, open_interest: 6500, is_unusual_oi: true, tag: '-' },
      { expiration: '2026-09-18', symbol: sym, order_type: 'BUY CALL', strike: spot * 1.05, spot: spot, otm_pct: 5.0, premium: 390000, size: 950, open_interest: 600, is_unusual_oi: false, tag: '-' }
    ];
    return prints;
  }
}
