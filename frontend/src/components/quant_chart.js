/**
 * QuantChart - High Performance HTML5 Canvas Options Exposure Chart
 * Renders bi-directional dual-panel GEX & DEX horizontal bar distributions
 * with interactive touch/mouse tooltips, spot/wall markers, and vector scaling.
 */

const PALETTE = [
  '#d90429', '#ef233c', '#f77f00', '#fcbf49', '#e0a96d',
  '#1d3557', '#457b9d', '#3a86ff', '#2a9d8f', '#495057', '#6c757d'
];

export class QuantChart {
  constructor(container, data) {
    this.container = container;
    this.data = data;
    this.canvas = null;
    this.ctx = null;
    this.hoveredStrike = null;
    this.init();
  }

  init() {
    if (!this.data || !this.data.strikes || this.data.strikes.length === 0) {
      this.renderFallback();
      return;
    }

    this.wrapper = document.createElement('div');
    this.wrapper.className = 'quant-chart-card';

    // 1. Header with Macro Badges
    const header = document.createElement('div');
    header.className = 'chart-card-header';

    const spot = this.data.spot_price || 0;
    const callWall = this.data.call_wall || 0;
    const putWall = this.data.put_wall || 0;
    const cpRatio = this.data.call_put_ratio || 0;
    const regime = this.data.gamma_regime || 'Neutral';
    const isPos = regime.toLowerCase().includes('positive') || regime.toLowerCase().includes('long');

    header.innerHTML = `
      <div class="chart-title-row">
        <div class="chart-ticker-badge">📊 ${this.data.ticker} GEX / DEX Chart</div>
        <div class="chart-regime-pill ${isPos ? 'long' : 'short'}">${isPos ? '🟢 Long Gamma' : '🔴 Short Gamma'}</div>
        <button class="expand-btn" title="Expand Fullscreen">🔍</button>
      </div>
      <div class="chart-metrics-bar">
        <div class="metric-pill">Spot: <strong>$${spot.toFixed(2)}</strong></div>
        <div class="metric-pill call-wall">Call Wall: <strong>$${callWall.toFixed(2)}</strong></div>
        <div class="metric-pill put-wall">Put Wall: <strong>$${putWall.toFixed(2)}</strong></div>
        <div class="metric-pill">C/P: <strong>${cpRatio.toFixed(2)}</strong></div>
      </div>
    `;

    this.wrapper.appendChild(header);

    // 2. Canvas Container
    this.canvasContainer = document.createElement('div');
    this.canvasContainer.className = 'chart-canvas-container';

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'quant-canvas';
    this.canvasContainer.appendChild(this.canvas);

    // Floating Tooltip
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'chart-tooltip';
    this.tooltip.style.display = 'none';
    this.canvasContainer.appendChild(this.tooltip);

    this.wrapper.appendChild(this.canvasContainer);

    // 3. Expiration Legend Pills
    if (this.data.expirations && this.data.expirations.length > 0) {
      const legend = document.createElement('div');
      legend.className = 'chart-legend';
      this.data.expirations.slice(0, 11).forEach((exp, idx) => {
        const color = PALETTE[idx % PALETTE.length];
        const item = document.createElement('span');
        item.className = 'legend-item';
        item.innerHTML = `<span class="legend-dot" style="background:${color}"></span>${exp}`;
        legend.appendChild(item);
      });
      this.wrapper.appendChild(legend);
    }

    this.container.appendChild(this.wrapper);
    this.ctx = this.canvas.getContext('2d');

    this.bindEvents();
    this.draw();

    // Auto resize
    window.addEventListener('resize', () => this.draw());
  }

  renderFallback() {
    this.container.innerHTML = `
      <div class="quant-chart-card empty">
        <div class="chart-ticker-badge">📊 ${this.data?.ticker || 'Options'} Exposure</div>
        <p>No active options chain liquidity available for this ticker.</p>
      </div>
    `;
  }

  bindEvents() {
    const expandBtn = this.wrapper.querySelector('.expand-btn');
    if (expandBtn) {
      expandBtn.addEventListener('click', () => this.toggleFullscreen());
    }

    const onMove = (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      this.handleHover(x, y);
    };

    const onLeave = () => {
      this.hoveredStrike = null;
      this.tooltip.style.display = 'none';
      this.draw();
    };

    this.canvas.addEventListener('mousemove', onMove);
    this.canvas.addEventListener('mouseleave', onLeave);
    this.canvas.addEventListener('touchstart', onMove, { passive: true });
    this.canvas.addEventListener('touchend', onLeave);
  }

  toggleFullscreen() {
    if (window.quantLightbox) {
      const modalContent = document.createElement('div');
      modalContent.className = 'modal-chart-wrapper';
      new QuantChart(modalContent, this.data);
      window.quantLightbox.openCustom(modalContent);
    }
  }

  handleHover(x, y) {
    if (!this.strikesList || this.strikesList.length === 0) return;

    const canvasH = this.canvas.height / (window.devicePixelRatio || 1);
    const padding = 20;
    const chartH = canvasH - padding * 2;

    const ratio = (y - padding) / chartH;
    const clampedRatio = Math.max(0, Math.min(1, ratio));

    const strikeIdx = Math.round(clampedRatio * (this.strikesList.length - 1));
    const strikeData = this.strikesList[this.strikesList.length - 1 - strikeIdx];

    if (!strikeData) return;

    this.hoveredStrike = strikeData.strike;
    this.draw();

    // Render Tooltip
    const spot = this.data.spot_price || 0;
    const diffPct = spot > 0 ? (((strikeData.strike - spot) / spot) * 100).toFixed(1) : 0;
    const sign = diffPct > 0 ? '+' : '';

    this.tooltip.innerHTML = `
      <div class="tt-header">
        <strong>Strike: $${strikeData.strike.toFixed(2)}</strong>
        <span class="tt-dist">(${sign}${diffPct}%)</span>
      </div>
      <div class="tt-row">
        <span style="color:#ef233c">Call GEX:</span>
        <span>$${this.formatCurrency(strikeData.call_gex)}</span>
      </div>
      <div class="tt-row">
        <span style="color:#2a9d8f">Put GEX:</span>
        <span>$${this.formatCurrency(strikeData.put_gex)}</span>
      </div>
      <div class="tt-row net">
        <span>Net GEX:</span>
        <strong style="color:${strikeData.net_gex >= 0 ? '#00f5d4' : '#ff006e'}">$${this.formatCurrency(strikeData.net_gex)}</strong>
      </div>
    `;

    this.tooltip.style.display = 'block';
    this.tooltip.style.top = `${Math.min(y, canvasH - 120)}px`;
    this.tooltip.style.left = `${Math.min(x + 15, this.canvas.width / (window.devicePixelRatio || 1) - 180)}px`;
  }

  formatCurrency(val) {
    const abs = Math.abs(val);
    const sign = val < 0 ? '-' : '';
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`;
    return `${sign}${abs.toFixed(0)}`;
  }

  draw() {
    if (!this.canvas || !this.ctx || !this.data || !this.data.strikes) return;

    const dpr = window.devicePixelRatio || 1;
    const displayW = this.canvasContainer.clientWidth || 360;
    const displayH = Math.max(380, Math.min(520, this.data.strikes.length * 16));

    this.canvas.width = displayW * dpr;
    this.canvas.height = displayH * dpr;
    this.canvas.style.width = `${displayW}px`;
    this.canvas.style.height = `${displayH}px`;

    const ctx = this.ctx;
    ctx.resetTransform();
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = '#0f141d';
    ctx.fillRect(0, 0, displayW, displayH);

    // Grid Layout: 2 Sub-panels (GEX & DEX)
    const paddingLeft = 45;
    const paddingRight = 15;
    const paddingTop = 30;
    const paddingBottom = 25;
    const gap = 16;

    const usableW = displayW - paddingLeft - paddingRight - gap;
    const panelW = usableW / 2;
    const chartH = displayH - paddingTop - paddingBottom;

    const p1_left = paddingLeft;
    const p1_right = p1_left + panelW;
    const p1_center = p1_left + panelW / 2;

    const p2_left = p1_right + gap;
    const p2_right = p2_left + panelW;
    const p2_center = p2_left + panelW / 2;

    // Background Panels
    ctx.fillStyle = '#151a24';
    ctx.fillRect(p1_left, paddingTop, panelW, chartH);
    ctx.fillRect(p2_left, paddingTop, panelW, chartH);

    // Subtitles
    ctx.font = 'bold 11px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#a0aec0';
    ctx.textAlign = 'center';
    ctx.fillText('Gamma Exposure (GEX)', p1_center, paddingTop - 10);
    ctx.fillText('Delta Exposure (DEX)', p2_center, paddingTop - 10);

    // CALLS / PUTS headers
    ctx.font = '9px system-ui, sans-serif';
    ctx.fillStyle = '#718096';
    ctx.fillText('CALLS', p1_left + panelW * 0.25, paddingTop + 12);
    ctx.fillText('PUTS', p1_left + panelW * 0.75, paddingTop + 12);
    ctx.fillText('CALLS', p2_left + panelW * 0.25, paddingTop + 12);
    ctx.fillText('PUTS', p2_left + panelW * 0.75, paddingTop + 12);

    // Strikes Sorting (Top = Highest Strike, Bottom = Lowest Strike)
    this.strikesList = [...this.data.strikes].sort((a, b) => a.strike - b.strike);
    const n = this.strikesList.length;
    if (n === 0) return;

    // Calculate maximum magnitude for scaling
    let maxGex = 1;
    let maxDex = 1;
    this.strikesList.forEach(s => {
      maxGex = Math.max(maxGex, s.call_gex || 0, s.put_gex || 0);
      maxDex = Math.max(maxDex, s.call_dex || 0, s.put_dex || 0);
    });

    const maxGexScaled = maxGex * 1.1;
    const maxDexScaled = maxDex * 1.1;

    const barHeight = Math.max(2, (chartH / n) * 0.75);
    const rowStep = chartH / n;

    // Draw Strike Bars
    this.strikesList.forEach((s, idx) => {
      // Top = Highest Strike (reverse index)
      const y = paddingTop + (n - 1 - idx) * rowStep + (rowStep - barHeight) / 2;

      // Highlight row if hovered
      if (this.hoveredStrike === s.strike) {
        ctx.fillStyle = 'rgba(58, 134, 255, 0.15)';
        ctx.fillRect(paddingLeft - 40, y - 2, displayW, barHeight + 4);
      }

      // Panel 1: GEX
      const callGexW = ((s.call_gex || 0) / maxGexScaled) * (panelW / 2);
      const putGexW = ((s.put_gex || 0) / maxGexScaled) * (panelW / 2);

      ctx.fillStyle = '#ef233c'; // Call Red
      ctx.fillRect(p1_center - callGexW, y, callGexW, barHeight);

      ctx.fillStyle = '#2a9d8f'; // Put Teal
      ctx.fillRect(p1_center, y, putGexW, barHeight);

      // Panel 2: DEX
      const callDexW = ((s.call_dex || 0) / maxDexScaled) * (panelW / 2);
      const putDexW = ((s.put_dex || 0) / maxDexScaled) * (panelW / 2);

      ctx.fillStyle = '#f77f00'; // Call Amber
      ctx.fillRect(p2_center - callDexW, y, callDexW, barHeight);

      ctx.fillStyle = '#3a86ff'; // Put Blue
      ctx.fillRect(p2_center, y, putDexW, barHeight);

      // Y-Axis Strike Label
      if (idx % Math.max(1, Math.floor(n / 18)) === 0 || this.hoveredStrike === s.strike) {
        ctx.fillStyle = this.hoveredStrike === s.strike ? '#ffffff' : '#718096';
        ctx.font = this.hoveredStrike === s.strike ? 'bold 10px monospace' : '9px monospace';
        ctx.textAlign = 'right';
        ctx.fillText(`$${s.strike.toFixed(0)}`, paddingLeft - 6, y + barHeight - 1);
      }
    });

    // Zero Centers
    ctx.strokeStyle = '#2d3748';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(p1_center, paddingTop);
    ctx.lineTo(p1_center, paddingTop + chartH);
    ctx.moveTo(p2_center, paddingTop);
    ctx.lineTo(p2_center, paddingTop + chartH);
    ctx.stroke();

    // Helper: Draw horizontal reference lines (Spot, Call Wall, Put Wall)
    const minStrike = this.strikesList[0].strike;
    const maxStrike = this.strikesList[n - 1].strike;

    const getYForStrike = (strikeVal) => {
      if (strikeVal < minStrike || strikeVal > maxStrike) return null;
      const ratio = (strikeVal - minStrike) / (maxStrike - minStrike);
      return paddingTop + (1 - ratio) * chartH;
    };

    const drawRefLine = (strikeVal, color, label) => {
      const y = getYForStrike(strikeVal);
      if (y === null) return;

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);

      ctx.beginPath();
      ctx.moveTo(p1_left, y);
      ctx.lineTo(p2_right, y);
      ctx.stroke();

      // Label Tag
      ctx.fillStyle = color;
      ctx.font = 'bold 9px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`${label} $${strikeVal.toFixed(0)}`, p1_left + 4, y - 3);
      ctx.restore();
    };

    if (this.data.spot_price) drawRefLine(this.data.spot_price, '#3a86ff', 'SPOT');
    if (this.data.call_wall) drawRefLine(this.data.call_wall, '#00f5d4', 'CALL WALL');
    if (this.data.put_wall) drawRefLine(this.data.put_wall, '#ff006e', 'PUT WALL');
  }
}
