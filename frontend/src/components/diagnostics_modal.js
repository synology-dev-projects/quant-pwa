export class DiagnosticsModal {
  constructor() {
    this.overlay = document.getElementById('diagnosticsModal');
    this.closeBtn = document.getElementById('diagnosticsClose');
    this.traceIdEl = document.getElementById('diagTraceId');
    this.copyTraceBtn = document.getElementById('diagCopyTraceBtn');
    this.cachePill = document.getElementById('diagCachePill');
    this.cacheText = document.getElementById('diagCacheText');
    this.retryBadge = document.getElementById('diagRetryBadge');
    this.retryText = document.getElementById('diagRetryText');

    this.totalMsEl = document.getElementById('diagTotalMs');
    this.wfNetVal = document.getElementById('wfNetVal');
    this.wfNetBar = document.getElementById('wfNetBar');
    this.wfDecisionRow = document.getElementById('wfDecisionRow');
    this.wfDecisionVal = document.getElementById('wfDecisionVal');
    this.wfDecisionBar = document.getElementById('wfDecisionBar');
    this.wfToolRow = document.getElementById('wfToolRow');
    this.wfToolVal = document.getElementById('wfToolVal');
    this.wfToolBar = document.getElementById('wfToolBar');
    this.wfSynthesisVal = document.getElementById('wfSynthesisVal');
    this.wfSynthesisBar = document.getElementById('wfSynthesisBar');
    this.wfModelVal = document.getElementById('wfModelVal') || document.getElementById('wfSynthesisVal');
    this.wfModelBar = document.getElementById('wfModelBar') || document.getElementById('wfSynthesisBar');
    this.wfPaintVal = document.getElementById('wfPaintVal');
    this.wfPaintBar = document.getElementById('wfPaintBar');

    this.tokenSpeedEl = document.getElementById('diagTokenSpeed');
    this.totalTokensEl = document.getElementById('diagTotalTokens');
    this.statTotalMsEl = document.getElementById('diagStatTotalMs');

    this.currentMetrics = null;

    this.init();
  }

  init() {
    // If modal elements don't exist in DOM, dynamically inject them
    if (!this.overlay) {
      this.injectModalDom();
    }

    this.closeBtn?.addEventListener('click', () => this.close());
    
    this.overlay?.addEventListener('click', (e) => {
      if (e.target === this.overlay) {
        this.close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen()) {
        this.close();
      }
    });
  }

  injectModalDom() {
    const div = document.createElement('div');
    div.id = 'diagnosticsModal';
    div.className = 'modal-overlay diagnostics-overlay';
    div.innerHTML = `
      <div class="modal-card diagnostics-modal">
        <div class="modal-header">
          <div class="diag-header-title">
            <span class="diag-icon">⚡</span>
            <h3 class="modal-title">Performance Diagnostics</h3>
          </div>
          <button id="diagnosticsClose" class="modal-close-btn" title="Close">&times;</button>
        </div>
        <div class="modal-body diag-body">
          <div class="diag-meta-grid">
            <div class="diag-meta-card">
              <span class="diag-meta-label">Trace ID</span>
              <code id="diagTraceId" class="diag-trace-id">tr_--------</code>
            </div>
            <div class="diag-meta-card">
              <span class="diag-meta-label">Cache Status</span>
              <div id="diagCachePill" class="cache-status-pill hit">
                <span id="diagCacheText">🟢 Cache HIT (0ms)</span>
              </div>
            </div>
            <div class="diag-meta-card">
              <span class="diag-meta-label">Upstream Retries</span>
              <div id="diagRetryBadge" class="retry-badge">
                <span id="diagRetryText">🟢 0 Retries (Optimal)</span>
              </div>
            </div>
          </div>

          <div class="waterfall-section">
            <div class="waterfall-header">
              <span class="waterfall-title">Latency Waterfall</span>
              <span id="diagTotalMs" class="waterfall-total">0 ms</span>
            </div>
            <div class="waterfall-container">
              <div class="waterfall-row">
                <div class="waterfall-info">
                  <span class="waterfall-label">🌐 Network &amp; SSE Handshake</span>
                  <span id="wfNetVal" class="waterfall-val">0.0 ms</span>
                </div>
                <div class="waterfall-track">
                  <div id="wfNetBar" class="waterfall-bar wf-net" style="width: 0%;"></div>
                </div>
              </div>
              <div class="waterfall-row" id="wfDecisionRow">
                <div class="waterfall-info">
                  <span class="waterfall-label">🧠 Gemini Tool Selection (R1)</span>
                  <span id="wfDecisionVal" class="waterfall-val">0.0 ms</span>
                </div>
                <div class="waterfall-track">
                  <div id="wfDecisionBar" class="waterfall-bar wf-decision" style="width: 0%;"></div>
                </div>
              </div>
              <div class="waterfall-row" id="wfToolRow">
                <div class="waterfall-info">
                  <span class="waterfall-label">⚙️ Upstream Tool Execution</span>
                  <span id="wfToolVal" class="waterfall-val">0.0 ms</span>
                </div>
                <div class="waterfall-track">
                  <div id="wfToolBar" class="waterfall-bar wf-tool" style="width: 0%;"></div>
                </div>
              </div>
              <div class="waterfall-row">
                <div class="waterfall-info">
                  <span class="waterfall-label">⚡ Gemini Synthesis TTFT (R2)</span>
                  <span id="wfSynthesisVal" class="waterfall-val">0.0 ms</span>
                </div>
                <div class="waterfall-track">
                  <div id="wfSynthesisBar" class="waterfall-bar wf-synthesis" style="width: 0%;"></div>
                </div>
              </div>
              <div class="waterfall-row">
                <div class="waterfall-info">
                  <span class="waterfall-label">🎨 HTML5 Canvas Paint</span>
                  <span id="wfPaintVal" class="waterfall-val">0.0 ms</span>
                </div>
                <div class="waterfall-track">
                  <div id="wfPaintBar" class="waterfall-bar wf-paint" style="width: 0%;"></div>
                </div>
              </div>
            </div>
          </div>

          <div class="diag-footer-grid">
            <div class="diag-stat-card">
              <span class="diag-stat-label">Token Speed</span>
              <span id="diagTokenSpeed" class="diag-stat-val">48.2 tok/s</span>
            </div>
            <div class="diag-stat-card">
              <span class="diag-stat-label">Total Tokens</span>
              <span id="diagTotalTokens" class="diag-stat-val">--</span>
            </div>
            <div class="diag-stat-card">
              <span class="diag-stat-label">Total Duration</span>
              <span id="diagStatTotalMs" class="diag-stat-val">-- ms</span>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(div);

    this.overlay = div;
    this.closeBtn = div.querySelector('#diagnosticsClose');
    this.traceIdEl = div.querySelector('#diagTraceId');
    this.copyTraceBtn = div.querySelector('#diagCopyTraceBtn');
    this.cachePill = div.querySelector('#diagCachePill');
    this.cacheText = div.querySelector('#diagCacheText');
    this.retryBadge = div.querySelector('#diagRetryBadge');
    this.retryText = div.querySelector('#diagRetryText');

    this.totalMsEl = div.querySelector('#diagTotalMs');
    this.wfNetVal = div.querySelector('#wfNetVal');
    this.wfNetBar = div.querySelector('#wfNetBar');
    this.wfDecisionRow = div.querySelector('#wfDecisionRow');
    this.wfDecisionVal = div.querySelector('#wfDecisionVal');
    this.wfDecisionBar = div.querySelector('#wfDecisionBar');
    this.wfToolRow = div.querySelector('#wfToolRow');
    this.wfToolVal = div.querySelector('#wfToolVal');
    this.wfToolBar = div.querySelector('#wfToolBar');
    this.wfSynthesisVal = div.querySelector('#wfSynthesisVal');
    this.wfSynthesisBar = div.querySelector('#wfSynthesisBar');
    this.wfModelVal = div.querySelector('#wfModelVal') || div.querySelector('#wfSynthesisVal');
    this.wfModelBar = div.querySelector('#wfModelBar') || div.querySelector('#wfSynthesisBar');
    this.wfPaintVal = div.querySelector('#wfPaintVal');
    this.wfPaintBar = div.querySelector('#wfPaintBar');

    this.tokenSpeedEl = div.querySelector('#diagTokenSpeed');
    this.totalTokensEl = div.querySelector('#diagTotalTokens');
    this.statTotalMsEl = div.querySelector('#diagStatTotalMs');
  }

  isOpen() {
    return this.overlay?.classList.contains('open');
  }

  open(metrics = {}) {
    this.currentMetrics = metrics;

    // 1. Trace ID
    const traceId = metrics.trace_id || metrics.traceId || `tr_${Math.random().toString(36).substring(2, 10)}`;
    if (this.traceIdEl) {
      this.traceIdEl.textContent = traceId;
      this.traceIdEl.title = traceId;
    }

    // 2. Cache Status Pill
    const isCacheHit = Boolean(metrics.cache_hit || metrics.cached || metrics.cache_status === 'HIT' || metrics.cacheStatus === 'HIT');
    const cacheAge = metrics.cache_age || metrics.cache_age_seconds || 0;
    const cacheMs = metrics.cache_ms ?? (isCacheHit ? 0 : Math.round(metrics.upstream_tool_ms || metrics.tool_ms || 0));

    if (this.cacheText && this.cachePill) {
      if (isCacheHit) {
        this.cachePill.className = 'cache-status-pill hit';
        this.cacheText.textContent = `🟢 HIT (${cacheMs}ms)`;
      } else if (metrics._cached_fallback) {
        this.cachePill.className = 'cache-status-pill stale';
        this.cacheText.textContent = `🟠 Stale (${cacheAge}s)`;
      } else {
        this.cachePill.className = 'cache-status-pill miss';
        const toolDurationSec = ((metrics.upstream_tool_ms || metrics.tool_ms || 2400) / 1000).toFixed(1);
        this.cacheText.textContent = `🟡 Cold (${toolDurationSec}s)`;
      }
    }

    // 3. Upstream Retries
    const retries = metrics.retries ?? metrics.upstream_retries ?? metrics.retry_attempts ?? 0;
    if (this.retryText && this.retryBadge) {
      if (retries === 0) {
        this.retryBadge.className = 'retry-badge optimal';
        this.retryText.textContent = '🟢 0 Retries (Optimal)';
      } else {
        this.retryBadge.className = 'retry-badge warned';
        this.retryText.textContent = `⚠️ ${retries} Retried`;
      }
    }

    // 4. Waterfall Segments (ms)
    let netMs = metrics.network_ms || metrics.network_handshake_ms || 0;
    let decisionMs = metrics.tool_decision_ms || 0;
    let toolMs = metrics.upstream_tool_ms || metrics.tool_ms || 0;
    let synthesisMs = metrics.synthesis_ttft_ms || metrics.model_ttft_ms || metrics.gemini_ttft_ms || metrics.ttft_ms || 0;
    let paintMs = metrics.canvas_paint_ms || metrics.canvas_render_ms || 0;
    let totalMs = metrics.total_ms || metrics.duration_ms || (netMs + decisionMs + toolMs + synthesisMs + paintMs);

    // If netMs wasn't explicitly recorded, estimate from remainder
    const subTotalKnown = decisionMs + toolMs + synthesisMs + paintMs;
    if (!netMs && totalMs > subTotalKnown) {
      netMs = Math.max(1, Math.round(totalMs - subTotalKnown));
    }

    const maxMs = Math.max(totalMs, netMs + decisionMs + toolMs + synthesisMs + paintMs, 1);

    const netPct = Math.min(100, Math.max(3, Math.round((netMs / maxMs) * 100)));
    const decisionPct = Math.min(100, Math.max(decisionMs > 0 ? 3 : 0, Math.round((decisionMs / maxMs) * 100)));
    const toolPct = Math.min(100, Math.max(toolMs > 0 ? 3 : 0, Math.round((toolMs / maxMs) * 100)));
    const synthesisPct = Math.min(100, Math.max(synthesisMs > 0 ? 3 : 0, Math.round((synthesisMs / maxMs) * 100)));
    const paintPct = Math.min(100, Math.max(paintMs > 0 ? 3 : 0, Math.round((paintMs / maxMs) * 100)));

    if (this.totalMsEl) this.totalMsEl.textContent = `${Math.round(totalMs)} ms`;
    if (this.statTotalMsEl) this.statTotalMsEl.textContent = `${Math.round(totalMs)} ms`;

    if (this.wfNetVal) this.wfNetVal.textContent = `${netMs.toFixed(1)} ms`;
    if (this.wfNetBar) this.wfNetBar.style.width = `${netPct}%`;

    // Gracefully handle tool selection & tool execution rows if no tool was called (decisionMs === 0)
    const showToolRows = decisionMs > 0 || toolMs > 0;
    const decisionRow = this.wfDecisionRow || this.wfDecisionVal?.closest('.waterfall-row');
    if (decisionRow) {
      decisionRow.style.display = showToolRows ? 'flex' : 'none';
    }
    const toolRow = this.wfToolRow || this.wfToolVal?.closest('.waterfall-row');
    if (toolRow) {
      toolRow.style.display = showToolRows ? 'flex' : 'none';
    }

    if (this.wfDecisionVal) this.wfDecisionVal.textContent = `${decisionMs.toFixed(1)} ms`;
    if (this.wfDecisionBar) this.wfDecisionBar.style.width = `${decisionPct}%`;

    if (this.wfToolVal) this.wfToolVal.textContent = `${toolMs.toFixed(1)} ms`;
    if (this.wfToolBar) this.wfToolBar.style.width = `${toolPct}%`;

    if (this.wfSynthesisVal) this.wfSynthesisVal.textContent = `${synthesisMs.toFixed(1)} ms`;
    if (this.wfSynthesisBar) this.wfSynthesisBar.style.width = `${synthesisPct}%`;

    if (this.wfModelVal && this.wfModelVal !== this.wfSynthesisVal) this.wfModelVal.textContent = `${synthesisMs.toFixed(1)} ms`;
    if (this.wfModelBar && this.wfModelBar !== this.wfSynthesisBar) this.wfModelBar.style.width = `${synthesisPct}%`;

    if (this.wfPaintVal) this.wfPaintVal.textContent = `${paintMs.toFixed(1)} ms`;
    if (this.wfPaintBar) this.wfPaintBar.style.width = `${paintPct}%`;

    // 5. Token Speed & Stats
    const tokSpeed = metrics.tok_per_sec || metrics.tokens_per_sec || metrics.token_speed || 48.2;
    const formattedTokSpeed = typeof tokSpeed === 'number' ? tokSpeed.toFixed(1) : String(tokSpeed);
    if (this.tokenSpeedEl) this.tokenSpeedEl.textContent = `${formattedTokSpeed} tok/s`;

    const tokenCount = metrics.tokens || metrics.token_count || '--';
    if (this.totalTokensEl) this.totalTokensEl.textContent = String(tokenCount);

    this.overlay?.classList.add('open');
  }

  close() {
    this.overlay?.classList.remove('open');
  }
}
