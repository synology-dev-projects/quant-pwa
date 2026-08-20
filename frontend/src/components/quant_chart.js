/**
 * QuantChart - High Performance HTML5 Canvas Options Exposure Chart
 * Pixel-perfect implementation matching institutional double-sided stacked GEX & DEX charts.
 *
 * Layout:
 * - Dual Panels: GEX (Left) & DEX (Right)
 * - Double-sided X-axis centered at 0:
 *   - CALLS on Left (stacked bars extending LEFT from 0)
 *   - PUTS on Right (stacked bars extending RIGHT from 0)
 * - Stacked by Expiration Date using vivid color palette
 * - Horizontal Key Level Lines across both panels:
 *   - Call Wall (Cyan dashed #00f5d4)
 *   - Spot Price (Blue dashed #3a86ff)
 *   - Put Wall (Magenta dashed #ff006e)
 * - Interactive crosshair and touch/mouse inspection tooltips
 */

const PALETTE = [
  '#d90429', // 0: Crimson Red
  '#ef233c', // 1: Red
  '#f77f00', // 2: Vibrant Orange
  '#fcbf49', // 3: Amber Yellow
  '#e0a96d', // 4: Tan / Sand
  '#1d3557', // 5: Navy Blue
  '#457b9d', // 6: Steel Blue
  '#3a86ff', // 7: Bright Blue
  '#2a9d8f', // 8: Teal
  '#a8dadc'  // 9: Ice Blue
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

    // 1. Top Badges & Title Bar
    const spot = this.data.spot_price || 0;
    const callWall = this.data.call_wall || 0;
    const putWall = this.data.put_wall || 0;
    const cpRatio = this.data.call_put_ratio || 0;
    const ticker = this.data.ticker || 'QUANT';

    const header = document.createElement('div');
    header.className = 'chart-card-header';
    header.innerHTML = `
      <div class="chart-macro-grid">
        <div class="macro-box spot-box">
          <span class="macro-lbl">Spot Price</span>
          <span class="macro-val">$${spot.toFixed(2)}</span>
        </div>
        <div class="macro-center">
          <div class="macro-box cp-box">
            <span class="macro-lbl">Call/Put Ratio</span>
            <span class="macro-val">${cpRatio.toFixed(2)}</span>
          </div>
          <div class="chart-main-title">${ticker} GEX DEX Chart</div>
        </div>
        <div class="macro-box summary-box">
          <div>Spot: <strong>$${spot.toFixed(2)}</strong></div>
          <div style="color:#00f5d4">Call Wall: <strong>$${callWall.toFixed(2)}</strong></div>
          <div style="color:#ff006e">Put Wall: <strong>$${putWall.toFixed(2)}</strong></div>
        </div>
        <button class="expand-btn" title="Expand Fullscreen">🔍</button>
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

    // 3. Expirations Legend
    const expirations = this.data.expirations || [];
    if (expirations.length > 0) {
      const legend = document.createElement('div');
      legend.className = 'chart-legend';
      legend.innerHTML = `<span class="legend-title">Expiries:</span>`;
      expirations.slice(0, 10).forEach((exp, idx) => {
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

    // Instant initial draw on next animation frame after DOM layout
    requestAnimationFrame(() => this.draw());

    // Continuous auto-redraw whenever container geometry changes
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          if (entry.contentRect.width > 0) {
            this.draw();
          }
        }
      });
      this.resizeObserver.observe(this.canvasContainer);
    } else {
      window.addEventListener('resize', () => this.draw());
    }
  }

  destroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
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

    const dpr = window.devicePixelRatio || 1;
    const canvasH = this.canvas.height / dpr;
    const paddingTop = 45;
    const paddingBottom = 40;
    const chartH = canvasH - paddingTop - paddingBottom;

    const ratio = (y - paddingTop) / chartH;
    const clampedRatio = Math.max(0, Math.min(1, ratio));

    const strikeIdx = Math.round(clampedRatio * (this.strikesList.length - 1));
    const strikeData = this.strikesList[this.strikesList.length - 1 - strikeIdx];

    if (!strikeData) return;

    this.hoveredStrike = strikeData.strike;
    this.draw();

    // Render Detailed Tooltip
    const spot = this.data.spot_price || 0;
    const diffPct = spot > 0 ? (((strikeData.strike - spot) / spot) * 100).toFixed(1) : 0;
    const sign = diffPct > 0 ? '+' : '';

    let expRowsHtml = '';
    const expirations = this.data.expirations || [];
    if (strikeData.exp_gex && Object.keys(strikeData.exp_gex).length > 0) {
      expRowsHtml = `<div class="tt-exp-breakdown">`;
      expirations.forEach((exp, idx) => {
        const gexInfo = strikeData.exp_gex[exp];
        if (gexInfo && (gexInfo.call > 0 || gexInfo.put > 0)) {
          const color = PALETTE[idx % PALETTE.length];
          expRowsHtml += `
            <div class="tt-exp-row">
              <span style="color:${color}">■ ${exp}:</span>
              <span>C: $${this.formatCurrency(gexInfo.call)} / P: $${this.formatCurrency(gexInfo.put)}</span>
            </div>
          `;
        }
      });
      expRowsHtml += `</div>`;
    }

    this.tooltip.innerHTML = `
      <div class="tt-header">
        <strong>Strike: $${strikeData.strike.toFixed(2)}</strong>
        <span class="tt-dist">(${sign}${diffPct}%)</span>
      </div>
      <div class="tt-row">
        <span style="color:#ef233c">Call GEX (Left):</span>
        <strong>$${this.formatCurrency(strikeData.call_gex)}</strong>
      </div>
      <div class="tt-row">
        <span style="color:#2a9d8f">Put GEX (Right):</span>
        <strong>$${this.formatCurrency(strikeData.put_gex)}</strong>
      </div>
      <div class="tt-row">
        <span style="color:#f77f00">Call DEX (Left):</span>
        <strong>$${this.formatCurrency(strikeData.call_dex)}</strong>
      </div>
      <div class="tt-row">
        <span style="color:#3a86ff">Put DEX (Right):</span>
        <strong>$${this.formatCurrency(strikeData.put_dex)}</strong>
      </div>
      ${expRowsHtml}
    `;

    this.tooltip.style.display = 'block';
    const maxTop = canvasH - 180;
    this.tooltip.style.top = `${Math.max(10, Math.min(y - 30, maxTop))}px`;
    const maxLeft = (this.canvas.width / dpr) - 220;
    this.tooltip.style.left = `${Math.min(x + 20, maxLeft)}px`;
  }

  formatCurrency(val) {
    const abs = Math.abs(val || 0);
    const sign = val < 0 ? '-' : '';
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`;
    return `${sign}${abs.toFixed(0)}`;
  }

  draw() {
    if (!this.canvas || !this.ctx || !this.data || !this.data.strikes) return;

    const dpr = window.devicePixelRatio || 1;
    const displayW = this.canvasContainer.clientWidth || 380;
    const displayH = Math.max(420, Math.min(560, this.data.strikes.length * 18));

    this.canvas.width = displayW * dpr;
    this.canvas.height = displayH * dpr;
    this.canvas.style.width = `${displayW}px`;
    this.canvas.style.height = `${displayH}px`;

    const ctx = this.ctx;
    ctx.resetTransform();
    ctx.scale(dpr, dpr);

    // Deep Dark Navy Background
    ctx.fillStyle = '#0a0e17';
    ctx.fillRect(0, 0, displayW, displayH);

    // Layout Dimensions
    const paddingLeft = 44;
    const paddingRight = 14;
    const paddingTop = 45;
    const paddingBottom = 40;
    const gap = 38; // Gap between GEX and DEX panels for middle strike labels

    const usableW = displayW - paddingLeft - paddingRight - gap;
    const panelW = usableW / 2;
    const chartH = displayH - paddingTop - paddingBottom;

    const p1_left = paddingLeft;
    const p1_right = p1_left + panelW;
    const p1_center = p1_left + panelW / 2;

    const p2_left = p1_right + gap;
    const p2_right = p2_left + panelW;
    const p2_center = p2_left + panelW / 2;

    // Panel Backgrounds with subtle grid lines
    ctx.fillStyle = '#0f1422';
    ctx.fillRect(p1_left, paddingTop, panelW, chartH);
    ctx.fillRect(p2_left, paddingTop, panelW, chartH);

    // Subtle panel borders
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.strokeRect(p1_left, paddingTop, panelW, chartH);
    ctx.strokeRect(p2_left, paddingTop, panelW, chartH);

    // Subtitles: Gamma Exposure (GEX) & Delta Exposure (DEX) at bottom
    ctx.font = 'bold 11px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#e2e8f0';
    ctx.textAlign = 'center';
    ctx.fillText('Gamma Exposure (GEX)', p1_center, displayH - 12);
    ctx.fillText('Delta Exposure (DEX)', p2_center, displayH - 12);

    // CALLS (Left of 0) & PUTS (Right of 0) headers
    ctx.font = 'bold 10px sans-serif';
    ctx.fillStyle = '#cbd5e1';
    
    // Panel 1 Headers
    ctx.fillText('CALLS', p1_left + panelW * 0.25, paddingTop - 12);
    ctx.fillText('PUTS', p1_left + panelW * 0.75, paddingTop - 12);
    
    // Panel 2 Headers
    ctx.fillText('CALLS', p2_left + panelW * 0.25, paddingTop - 12);
    ctx.fillText('PUTS', p2_left + panelW * 0.75, paddingTop - 12);

    // Strikes Sorting (Top = Highest Strike, Bottom = Lowest Strike)
    this.strikesList = [...this.data.strikes].sort((a, b) => a.strike - b.strike);
    const n = this.strikesList.length;
    if (n === 0) return;

    const expirations = this.data.expirations || [];

    // Calculate maximum magnitude for scaling
    let maxGex = 1;
    let maxDex = 1;
    this.strikesList.forEach(s => {
      maxGex = Math.max(maxGex, Math.abs(s.call_gex || 0), Math.abs(s.put_gex || 0));
      maxDex = Math.max(maxDex, Math.abs(s.call_dex || 0), Math.abs(s.put_dex || 0));
    });

    const maxGexScaled = maxGex * 1.15;
    const maxDexScaled = maxDex * 1.15;

    const rowStep = chartH / n;
    const barHeight = Math.max(3, rowStep * 0.65);

    // Horizontal Grid Lines & Strike Bars
    this.strikesList.forEach((s, idx) => {
      // Top = Highest Strike
      const y = paddingTop + (n - 1 - idx) * rowStep + (rowStep - barHeight) / 2;
      const centerY = y + barHeight / 2;

      // Subtle horizontal dotted grid line
      ctx.save();
      ctx.strokeStyle = '#172033';
      ctx.lineWidth = 0.5;
      ctx.setLineDash([2, 4]);
      ctx.beginPath();
      ctx.moveTo(p1_left, centerY);
      ctx.lineTo(p1_right, centerY);
      ctx.moveTo(p2_left, centerY);
      ctx.lineTo(p2_right, centerY);
      ctx.stroke();
      ctx.restore();

      // Highlight active hovered row
      if (this.hoveredStrike === s.strike) {
        ctx.fillStyle = 'rgba(58, 134, 255, 0.18)';
        ctx.fillRect(0, y - 2, displayW, barHeight + 4);
      }

      // ==========================================
      // PANEL 1: GEX (Stacked by Expiration)
      // ==========================================
      // 1. CALLS (Left of Center) -> Stacks LEFT from p1_center
      if (s.exp_gex && Object.keys(s.exp_gex).length > 0) {
        let curLeft = p1_center;
        expirations.forEach((exp, expIdx) => {
          const rawVal = s.exp_gex[exp]?.call || 0;
          const segVal = Math.abs(rawVal);
          if (segVal > 0) {
            const segW = (segVal / maxGexScaled) * (panelW / 2);
            ctx.fillStyle = PALETTE[expIdx % PALETTE.length];
            ctx.fillRect(curLeft - segW, y, segW, barHeight);
            curLeft -= segW;
          }
        });
      } else if (Math.abs(s.call_gex || 0) > 0) {
        const w = (Math.abs(s.call_gex) / maxGexScaled) * (panelW / 2);
        ctx.fillStyle = '#ef233c';
        ctx.fillRect(p1_center - w, y, w, barHeight);
      }

      // 2. PUTS (Right of Center) -> Stacks RIGHT from p1_center
      if (s.exp_gex && Object.keys(s.exp_gex).length > 0) {
        let curRight = p1_center;
        expirations.forEach((exp, expIdx) => {
          const rawVal = s.exp_gex[exp]?.put || 0;
          const segVal = Math.abs(rawVal);
          if (segVal > 0) {
            const segW = (segVal / maxGexScaled) * (panelW / 2);
            ctx.fillStyle = PALETTE[expIdx % PALETTE.length];
            ctx.fillRect(curRight, y, segW, barHeight);
            curRight += segW;
          }
        });
      } else if (Math.abs(s.put_gex || 0) > 0) {
        const w = (Math.abs(s.put_gex) / maxGexScaled) * (panelW / 2);
        ctx.fillStyle = '#2a9d8f';
        ctx.fillRect(p1_center, y, w, barHeight);
      }

      // ==========================================
      // PANEL 2: DEX (Stacked by Expiration)
      // ==========================================
      // 1. CALLS (Left of Center) -> Stacks LEFT from p2_center
      if (s.exp_dex && Object.keys(s.exp_dex).length > 0) {
        let curLeft = p2_center;
        expirations.forEach((exp, expIdx) => {
          const rawVal = s.exp_dex[exp]?.call || 0;
          const segVal = Math.abs(rawVal);
          if (segVal > 0) {
            const segW = (segVal / maxDexScaled) * (panelW / 2);
            ctx.fillStyle = PALETTE[expIdx % PALETTE.length];
            ctx.fillRect(curLeft - segW, y, segW, barHeight);
            curLeft -= segW;
          }
        });
      } else if (Math.abs(s.call_dex || 0) > 0) {
        const w = (Math.abs(s.call_dex) / maxDexScaled) * (panelW / 2);
        ctx.fillStyle = '#f77f00';
        ctx.fillRect(p2_center - w, y, w, barHeight);
      }

      // 2. PUTS (Right of Center) -> Stacks RIGHT from p2_center
      if (s.exp_dex && Object.keys(s.exp_dex).length > 0) {
        let curRight = p2_center;
        expirations.forEach((exp, expIdx) => {
          const rawVal = s.exp_dex[exp]?.put || 0;
          const segVal = Math.abs(rawVal);
          if (segVal > 0) {
            const segW = (segVal / maxDexScaled) * (panelW / 2);
            ctx.fillStyle = PALETTE[expIdx % PALETTE.length];
            ctx.fillRect(curRight, y, segW, barHeight);
            curRight += segW;
          }
        });
      } else if (Math.abs(s.put_dex || 0) > 0) {
        const w = (Math.abs(s.put_dex) / maxDexScaled) * (panelW / 2);
        ctx.fillStyle = '#3a86ff';
        ctx.fillRect(p2_center, y, w, barHeight);
      }

      // Y-Axis Strike Labels on Left Axis & Middle Gap
      const isTick = idx % Math.max(1, Math.floor(n / 16)) === 0 || this.hoveredStrike === s.strike;
      if (isTick) {
        ctx.fillStyle = this.hoveredStrike === s.strike ? '#ffffff' : '#94a3b8';
        ctx.font = this.hoveredStrike === s.strike ? 'bold 10px monospace' : '9px monospace';
        
        // Left Axis
        ctx.textAlign = 'right';
        ctx.fillText(`$${s.strike.toFixed(0)}`, paddingLeft - 5, y + barHeight - 1);

        // Middle Axis
        ctx.textAlign = 'center';
        ctx.fillText(`$${s.strike.toFixed(0)}`, p1_right + gap / 2, y + barHeight - 1);
      }
    });

    // Zero Axis Center Lines
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(p1_center, paddingTop);
    ctx.lineTo(p1_center, paddingTop + chartH);
    ctx.moveTo(p2_center, paddingTop);
    ctx.lineTo(p2_center, paddingTop + chartH);
    ctx.stroke();

    // X-Axis Symmetric Ticks & Numbers around 0
    ctx.font = '9px monospace';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';

    // Panel 1 Ticks (GEX)
    ctx.fillText(`${this.formatCurrency(maxGex)}`, p1_left + 15, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxGex / 2)}`, p1_left + panelW * 0.25, displayH - 26);
    ctx.fillText('0', p1_center, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxGex / 2)}`, p1_left + panelW * 0.75, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxGex)}`, p1_right - 15, displayH - 26);

    // Panel 2 Ticks (DEX)
    ctx.fillText(`${this.formatCurrency(maxDex)}`, p2_left + 15, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxDex / 2)}`, p2_left + panelW * 0.25, displayH - 26);
    ctx.fillText('0', p2_center, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxDex / 2)}`, p2_left + panelW * 0.75, displayH - 26);
    ctx.fillText(`${this.formatCurrency(maxDex)}`, p2_right - 15, displayH - 26);

    // Helper: Draw horizontal reference lines across BOTH panels
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
      // Draw across Left Panel
      ctx.moveTo(p1_left, y);
      ctx.lineTo(p1_right, y);
      // Draw across Right Panel
      ctx.moveTo(p2_left, y);
      ctx.lineTo(p2_right, y);
      ctx.stroke();

      // Label Tag on Left Panel
      ctx.fillStyle = color;
      ctx.font = 'bold 9px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`${label} $${strikeVal.toFixed(2)}`, p1_left + 4, y - 3);
      ctx.restore();
    };

    if (this.data.call_wall) drawRefLine(this.data.call_wall, '#00f5d4', 'CALL WALL');
    if (this.data.spot_price) drawRefLine(this.data.spot_price, '#3a86ff', 'SPOT');
    if (this.data.put_wall) drawRefLine(this.data.put_wall, '#ff006e', 'PUT WALL');
  }
}
