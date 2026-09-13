/**
 * CandlestickChart - High Performance HTML5 Canvas Candlestick Chart for SPX
 * Renders 5-minute regular trading hours (09:30 - 16:15 ET) session candles
 * with active Quant Levels (BUY, SELL, PIVOT), range corridors, immediate support/resistance
 * glowing lines, spot marker, and interactive crosshair inspection.
 * Zero external charting libraries.
 */

export class CandlestickChart {
  constructor(container, options = {}) {
    this.container = container;
    this.options = options;
    this.candles = options.candles || [];
    this.levels = options.levels || [];
    this.spotPrice = options.spot_price != null ? Number(options.spot_price) : null;
    this.asOfDate = options.as_of_date || '';
    this.ticker = options.ticker || 'SPX';
    this.isLightbox = !!options.isLightbox;

    this.wrapper = null;
    this.canvas = null;
    this.ctx = null;
    this.tooltip = null;
    this.hoveredIndex = null;
    this.resizeObserver = null;

    this._onMove = null;
    this._onLeave = null;
    this._onExpandClick = null;

    this.init();
  }

  updateData(newOptions = {}) {
    if (newOptions.candles !== undefined) this.candles = newOptions.candles || [];
    if (newOptions.levels !== undefined) this.levels = newOptions.levels || [];
    if (newOptions.spot_price !== undefined) this.spotPrice = newOptions.spot_price != null ? Number(newOptions.spot_price) : null;
    if (newOptions.as_of_date !== undefined) this.asOfDate = newOptions.as_of_date || '';
    if (newOptions.ticker !== undefined) this.ticker = newOptions.ticker || 'SPX';

    this.renderMetrics();
    requestAnimationFrame(() => this.draw());
  }

  init() {
    this.wrapper = document.createElement('div');
    this.wrapper.className = `candlestick-card ${this.isLightbox ? 'lightbox-mode' : ''}`;

    // 1. Header Bar
    const header = document.createElement('div');
    header.className = 'candlestick-card-header';

    const headerLeft = document.createElement('div');
    headerLeft.className = 'candlestick-header-left';
    headerLeft.innerHTML = `
      <span class="candlestick-badge">${this.ticker} 5M</span>
      <div>
        <div class="candlestick-title">${this.ticker} Session Candlesticks &amp; Structure</div>
        <div class="candlestick-subtitle">Regular Trading Hours (09:30 &ndash; 16:15 ET) &bull; Session: ${this.asOfDate || 'Latest'}</div>
      </div>
    `;
    header.appendChild(headerLeft);

    const headerRight = document.createElement('div');
    headerRight.className = 'candlestick-header-right';

    this.metricsMount = document.createElement('div');
    this.metricsMount.className = 'candlestick-session-metrics';
    this.metricsMount.id = 'candlestickMetricsMount';
    headerRight.appendChild(this.metricsMount);

    if (!this.isLightbox) {
      this.expandBtn = document.createElement('button');
      this.expandBtn.className = 'expand-btn candlestick-expand-btn';
      this.expandBtn.title = 'Expand Fullscreen';
      this.expandBtn.setAttribute?.('aria-label', 'Expand Fullscreen');
      this.expandBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 3 21 3 21 9"></polyline>
          <polyline points="9 21 3 21 3 15"></polyline>
          <line x1="21" y1="3" x2="14" y2="10"></line>
          <line x1="3" y1="21" x2="10" y2="14"></line>
        </svg>
      `;
      headerRight.appendChild(this.expandBtn);
    }
    header.appendChild(headerRight);
    this.wrapper.appendChild(header);

    // 2. Canvas Container
    this.canvasContainer = document.createElement('div');
    this.canvasContainer.className = 'candlestick-canvas-container';

    if (!this.candles || this.candles.length === 0) {
      this.canvasContainer.innerHTML = `
        <div class="candlestick-empty-overlay">
          <div class="candlestick-empty-icon">&#128200;</div>
          <div class="candlestick-empty-title">No Intraday Candles Available</div>
          <div class="candlestick-empty-desc">Trading session data for ${this.asOfDate || 'selected date'} is closed or pending ingestion.</div>
        </div>
      `;
    }

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'candlestick-canvas';
    this.canvasContainer.appendChild(this.canvas);

    // Floating Tooltip
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'candlestick-tooltip';
    this.tooltip.style.display = 'none';
    this.canvasContainer.appendChild(this.tooltip);

    this.wrapper.appendChild(this.canvasContainer);

    // 3. Legend Bar
    const legend = document.createElement('div');
    legend.className = 'candlestick-legend';
    legend.innerHTML = `
      <div class="legend-item"><span class="legend-dot dot-buy"></span><span>BUY Level</span></div>
      <div class="legend-item"><span class="legend-dot dot-sell"></span><span>SELL Level</span></div>
      <div class="legend-item"><span class="legend-dot dot-pivot"></span><span>PIVOT Level</span></div>
      <div class="legend-item"><span class="legend-line line-imm-res"></span><span>IMM Resistance</span></div>
      <div class="legend-item"><span class="legend-line line-imm-sup"></span><span>IMM Support</span></div>
      <div class="legend-item"><span class="legend-line line-spot"></span><span>Live Spot</span></div>
      <div class="legend-item"><span class="legend-box box-bull"></span><span>Bullish (5m)</span></div>
      <div class="legend-item"><span class="legend-box box-bear"></span><span>Bearish (5m)</span></div>
    `;
    this.wrapper.appendChild(legend);

    this.container.appendChild(this.wrapper);

    this.ctx = this.canvas.getContext('2d');
    this.renderMetrics();
    this.bindEvents();

    // Auto-resize observer
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => {
        requestAnimationFrame(() => this.draw());
      });
      this.resizeObserver.observe(this.canvasContainer);
    } else {
      window.addEventListener('resize', () => this.draw());
    }

    requestAnimationFrame(() => this.draw());
  }

  renderMetrics() {
    const mount = this.metricsMount || this.wrapper?.querySelector('#candlestickMetricsMount');
    if (!mount) return;

    if (!this.candles || this.candles.length === 0) {
      mount.innerHTML = '';
      return;
    }

    let sessionHigh = -Infinity;
    let sessionLow = Infinity;
    for (const c of this.candles) {
      if (c.high > sessionHigh) sessionHigh = c.high;
      if (c.low < sessionLow) sessionLow = c.low;
    }
    const openBar = this.candles[0];
    const lastBar = this.candles[this.candles.length - 1];
    const sessionChange = lastBar.close - openBar.open;
    const sessionChangePct = openBar.open > 0 ? (sessionChange / openBar.open) * 100 : 0;
    const sign = sessionChange >= 0 ? '+' : '';
    const colorClass = sessionChange >= 0 ? 'text-emerald' : 'text-rose';

    mount.innerHTML = `
      <div class="metric-chip">
        <span class="chip-label">OPEN</span>
        <span class="chip-val">$${openBar.open.toFixed(2)}</span>
      </div>
      <div class="metric-chip">
        <span class="chip-label">HIGH</span>
        <span class="chip-val chip-high">$${sessionHigh.toFixed(2)}</span>
      </div>
      <div class="metric-chip">
        <span class="chip-label">LOW</span>
        <span class="chip-val chip-low">$${sessionLow.toFixed(2)}</span>
      </div>
      <div class="metric-chip">
        <span class="chip-label">LAST</span>
        <span class="chip-val chip-last ${colorClass}">$${lastBar.close.toFixed(2)}</span>
      </div>
      <div class="metric-chip">
        <span class="chip-label">SESSION</span>
        <span class="chip-val ${colorClass}">${sign}${sessionChange.toFixed(2)} (${sign}${sessionChangePct.toFixed(2)}%)</span>
      </div>
    `;
  }

  bindEvents() {
    this._onExpandClick = () => this.toggleFullscreen();
    const expandBtn = this.expandBtn || this.wrapper?.querySelector('.candlestick-expand-btn');
    if (expandBtn) {
      expandBtn.addEventListener('click', this._onExpandClick);
    }

    this._onMove = (e) => {
      if (!this.canvas || !this.candles || this.candles.length === 0) return;
      const rect = this.canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      this.handleHover(x, y);
    };

    this._onLeave = () => {
      this.hoveredIndex = null;
      if (this.tooltip) this.tooltip.style.display = 'none';
      this.draw();
    };

    if (this.canvas) {
      this.canvas.addEventListener('mousemove', this._onMove);
      this.canvas.addEventListener('mouseleave', this._onLeave);
      this.canvas.addEventListener('touchstart', this._onMove, { passive: true });
      this.canvas.addEventListener('touchmove', this._onMove, { passive: true });
      this.canvas.addEventListener('touchend', this._onLeave);
    }
  }

  toggleFullscreen() {
    if (window.quantLightbox) {
      const modalContent = document.createElement('div');
      modalContent.className = 'modal-chart-wrapper modal-candlestick-wrapper';
      new CandlestickChart(modalContent, {
        candles: this.candles,
        levels: this.levels,
        spot_price: this.spotPrice,
        as_of_date: this.asOfDate,
        ticker: this.ticker,
        isLightbox: true
      });
      window.quantLightbox.openCustom(modalContent);
    }
  }

  handleHover(x, y) {
    if (!this.candles || this.candles.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const canvasW = this.canvas.width / dpr;
    const canvasH = this.canvas.height / dpr;
    const paddingLeft = 15;
    const paddingRight = 90;
    const plotW = canvasW - paddingLeft - paddingRight;

    if (x < paddingLeft || x > canvasW - paddingRight) {
      this.hoveredIndex = null;
      if (this.tooltip) this.tooltip.style.display = 'none';
      this.draw();
      return;
    }

    const relX = x - paddingLeft;
    const stepX = plotW / this.candles.length;
    let idx = Math.floor(relX / stepX);
    idx = Math.max(0, Math.min(this.candles.length - 1, idx));

    this.hoveredIndex = idx;
    this.draw();

    // Render Floating Tooltip
    const bar = this.candles[idx];
    if (!bar) return;

    const change = bar.close - bar.open;
    const changePct = bar.open > 0 ? (change / bar.open) * 100 : 0;
    const sign = change >= 0 ? '+' : '';
    const colorStyle = change >= 0 ? '#22c55e' : '#ef4444';

    // Find nearest quant level
    let nearestLevel = null;
    let minDistance = Infinity;
    for (const lvl of this.levels) {
      const p = lvl.end_price ? (lvl.start_price + lvl.end_price) / 2 : lvl.start_price;
      const dist = Math.abs(bar.close - p);
      if (dist < minDistance) {
        minDistance = dist;
        nearestLevel = lvl;
      }
    }

    let nearestHtml = '';
    if (nearestLevel) {
      const targetP = nearestLevel.end_price ? (nearestLevel.start_price + nearestLevel.end_price) / 2 : nearestLevel.start_price;
      const deltaPts = bar.close - targetP;
      const deltaSign = deltaPts >= 0 ? '+' : '';
      const typeColor = nearestLevel.type === 'BUY' ? '#22c55e' : nearestLevel.type === 'SELL' ? '#ef4444' : '#38bdf8';
      nearestHtml = `
        <div class="tooltip-divider"></div>
        <div class="tooltip-subheading">Nearest Quant Level:</div>
        <div class="tooltip-nearest-row">
          <span class="tooltip-tag" style="background:${typeColor}22; color:${typeColor}; border:1px solid ${typeColor}55;">
            ${nearestLevel.type}
          </span>
          <span class="tooltip-level-price">$${targetP.toFixed(2)}</span>
          <span class="tooltip-level-delta">(${deltaSign}${deltaPts.toFixed(2)} pts)</span>
        </div>
      `;
    }

    this.tooltip.innerHTML = `
      <div class="tooltip-time-badge">${bar.datetime} ET</div>
      <div class="tooltip-ohlc-grid">
        <div class="ohlc-row"><span class="ohlc-lbl">Open:</span><span class="ohlc-val">$${bar.open.toFixed(2)}</span></div>
        <div class="ohlc-row"><span class="ohlc-lbl">High:</span><span class="ohlc-val text-emerald">$${bar.high.toFixed(2)}</span></div>
        <div class="ohlc-row"><span class="ohlc-lbl">Low:</span><span class="ohlc-val text-rose">$${bar.low.toFixed(2)}</span></div>
        <div class="ohlc-row"><span class="ohlc-lbl">Close:</span><span class="ohlc-val" style="color:${colorStyle};">$${bar.close.toFixed(2)}</span></div>
        <div class="ohlc-row"><span class="ohlc-lbl">Change:</span><span class="ohlc-val" style="color:${colorStyle};">${sign}${change.toFixed(2)} (${sign}${changePct.toFixed(2)}%)</span></div>
        ${bar.volume > 0 ? `<div class="ohlc-row"><span class="ohlc-lbl">Volume:</span><span class="ohlc-val">${bar.volume.toLocaleString()}</span></div>` : ''}
      </div>
      ${nearestHtml}
    `;

    // Position tooltip securely without clipping
    this.tooltip.style.display = 'block';
    const tooltipRect = this.tooltip.getBoundingClientRect();
    let leftPos = x + 15;
    if (leftPos + tooltipRect.width > canvasW - 10) {
      leftPos = x - tooltipRect.width - 15;
    }
    leftPos = Math.max(10, leftPos);

    let topPos = y - tooltipRect.height / 2;
    topPos = Math.max(10, Math.min(canvasH - tooltipRect.height - 10, topPos));

    this.tooltip.style.left = `${leftPos}px`;
    this.tooltip.style.top = `${topPos}px`;
  }

  draw() {
    if (!this.canvas || !this.ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvasContainer.getBoundingClientRect();
    const width = rect.width || (this.isLightbox ? 900 : 700);
    const height = this.isLightbox ? 520 : (window.innerWidth < 768 ? 350 : 440);

    if (this.canvas.width !== width * dpr || this.canvas.height !== height * dpr) {
      this.canvas.width = width * dpr;
      this.canvas.height = height * dpr;
      this.canvas.style.width = `${width}px`;
      this.canvas.style.height = `${height}px`;
    }

    const ctx = this.ctx;
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    // Background fill
    ctx.fillStyle = '#080d1a';
    ctx.fillRect(0, 0, width, height);

    const paddingTop = 25;
    const paddingBottom = 30;
    const paddingLeft = 15;
    const paddingRight = 92; // Space for right badges and Y-axis scale
    const plotW = width - paddingLeft - paddingRight;
    const plotH = height - paddingTop - paddingBottom;

    if (plotW <= 0 || plotH <= 0) {
      ctx.restore();
      return;
    }

    // 1. Calculate Strict Fit Y-Axis Bounds (Session Candle Action + Relevant Corridors)
    let minY = Infinity;
    let maxY = -Infinity;

    if (this.candles && this.candles.length > 0) {
      for (const c of this.candles) {
        if (c.low < minY) minY = c.low;
        if (c.high > maxY) maxY = c.high;
      }
    }

    if (this.spotPrice != null && this.spotPrice > 0) {
      if (this.spotPrice < minY) minY = this.spotPrice;
      if (this.spotPrice > maxY) maxY = this.spotPrice;
    }

    if (minY === Infinity || maxY === -Infinity || maxY <= minY) {
      minY = (this.spotPrice || 5600) - 50;
      maxY = (this.spotPrice || 5600) + 50;
    }

    // Anchor session center to prevent far-away outlier artifacts (e.g. SPY ~700 pt levels)
    // from expanding the Y-axis and squashing the candlestick series into a 1px flat line.
    const sessionCenter = (minY + maxY) / 2;
    const maxDeltaPct = 0.035; // Relevant levels within ±3.5% of session price action (~266 pts for SPX 7600)

    if (this.levels && this.levels.length > 0) {
      for (const lvl of this.levels) {
        const p1 = lvl.start_price;
        const p2 = lvl.end_price;
        if (p1 != null && Math.abs(p1 - sessionCenter) / sessionCenter <= maxDeltaPct) {
          if (p1 < minY) minY = p1;
          if (p1 > maxY) maxY = p1;
        }
        if (p2 != null && Math.abs(p2 - sessionCenter) / sessionCenter <= maxDeltaPct) {
          if (p2 < minY) minY = p2;
          if (p2 > maxY) maxY = p2;
        }
      }
    }

    // Margin padding
    const ySpan = maxY - minY;
    const yMargin = ySpan * 0.04;
    const yMinBound = minY - yMargin;
    const yMaxBound = maxY + yMargin;

    const getY = (price) => {
      const ratio = (price - yMinBound) / (yMaxBound - yMinBound);
      return paddingTop + (1 - ratio) * plotH;
    };

    // 2. Draw Horizontal Grid & Price Ticks
    const numGridLines = 6;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';

    for (let i = 0; i <= numGridLines; i++) {
      const p = yMinBound + (yMaxBound - yMinBound) * (i / numGridLines);
      const y = getY(p);

      ctx.beginPath();
      ctx.moveTo(paddingLeft, y);
      ctx.lineTo(width - paddingRight, y);
      ctx.stroke();

      // Right-axis label
      ctx.fillText(`$${p.toFixed(2)}`, width - paddingRight + 6, y);
    }

    // 3. Draw Vertical Time Grid & Labels (09:30 to 16:15)
    if (this.candles && this.candles.length > 0) {
      const stepX = plotW / this.candles.length;
      const getX = (idx) => paddingLeft + (idx + 0.5) * stepX;

      // Draw time labels at regular intervals (approx every 12 bars = 1 hour)
      const labelInterval = Math.max(6, Math.floor(this.candles.length / 7));
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';

      for (let i = 0; i < this.candles.length; i += labelInterval) {
        const bar = this.candles[i];
        const x = getX(i);

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
        ctx.beginPath();
        ctx.moveTo(x, paddingTop);
        ctx.lineTo(x, height - paddingBottom);
        ctx.stroke();

        ctx.fillText(bar.datetime, x, height - paddingBottom + 8);
      }
      // Draw last bar time if not overlapping
      const lastIdx = this.candles.length - 1;
      const lastX = getX(lastIdx);
      ctx.fillText(this.candles[lastIdx].datetime, lastX, height - paddingBottom + 8);

      // 4. Draw Quant Level Range Corridors
      if (this.levels && this.levels.length > 0) {
        for (const lvl of this.levels) {
          if (lvl.start_price != null && lvl.end_price != null && Math.abs(lvl.end_price - lvl.start_price) > 0.01) {
            // Skip corridor if completely outside visible bounds
            const topPrice = Math.max(lvl.start_price, lvl.end_price);
            const bottomPrice = Math.min(lvl.start_price, lvl.end_price);
            if (bottomPrice > yMaxBound || topPrice < yMinBound) continue;

            const y1 = getY(lvl.start_price);
            const y2 = getY(lvl.end_price);
            const topY = Math.max(paddingTop, Math.min(y1, y2));
            const bottomY = Math.min(height - paddingBottom, Math.max(y1, y2));
            const h = bottomY - topY;
            if (h <= 0) continue;

            let corridorColor = 'rgba(56, 189, 248, 0.08)'; // Cyan PIVOT
            if (lvl.type === 'BUY') corridorColor = 'rgba(34, 197, 94, 0.09)'; // Green BUY
            else if (lvl.type === 'SELL') corridorColor = 'rgba(239, 68, 68, 0.09)'; // Red SELL

            ctx.fillStyle = corridorColor;
            ctx.fillRect(paddingLeft, topY, plotW, h);
          }
        }
      }

      // 5. Draw Quant Level Horizontal Lines & Right Badges
      if (this.levels && this.levels.length > 0) {
        for (const lvl of this.levels) {
          // Skip if level price is outside visible chart bounds
          if (lvl.start_price < yMinBound || lvl.start_price > yMaxBound) continue;

          const startY = getY(lvl.start_price);
          if (startY < paddingTop - 4 || startY > height - paddingBottom + 4) continue;
          const isImmRes = !!lvl.is_immediate_resistance;
          const isImmSup = !!lvl.is_immediate_support;

          let lineColor = '#38bdf8'; // Cyan default
          if (lvl.type === 'BUY') lineColor = '#22c55e';
          else if (lvl.type === 'SELL') lineColor = '#ef4444';

          ctx.save();
          if (isImmRes || isImmSup) {
            ctx.strokeStyle = lineColor;
            ctx.lineWidth = 2.0;
            ctx.shadowColor = lineColor;
            ctx.shadowBlur = 8;
            ctx.setLineDash([]);
          } else {
            ctx.strokeStyle = lineColor;
            ctx.lineWidth = 1.0;
            ctx.setLineDash([4, 3]);
          }

          ctx.beginPath();
          ctx.moveTo(paddingLeft, startY);
          ctx.lineTo(width - paddingRight, startY);
          ctx.stroke();
          ctx.restore();

          // Right Price Pill Badge
          this.drawLevelBadge(ctx, lvl, startY, width - paddingRight + 4, lineColor, isImmRes, isImmSup);

          // If end_price exists, draw secondary dashed boundary line
          if (lvl.end_price != null && Math.abs(lvl.end_price - lvl.start_price) > 0.01) {
            const endY = getY(lvl.end_price);
            ctx.save();
            ctx.strokeStyle = lineColor;
            ctx.lineWidth = 0.8;
            ctx.setLineDash([2, 2]);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, endY);
            ctx.lineTo(width - paddingRight, endY);
            ctx.stroke();
            ctx.restore();
          }
        }
      }

      // 6. Draw Spot Price Line
      if (this.spotPrice != null && this.spotPrice > 0) {
        const spotY = getY(this.spotPrice);
        ctx.save();
        ctx.strokeStyle = '#eab308'; // Amber
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 3]);
        ctx.beginPath();
        ctx.moveTo(paddingLeft, spotY);
        ctx.lineTo(width - paddingRight, spotY);
        ctx.stroke();
        ctx.restore();

        // Spot badge
        this.drawSpotBadge(ctx, this.spotPrice, spotY, width - paddingRight + 4);
      }

      // 7. Draw Candlesticks
      const candleWidth = Math.max(2, Math.min(12, stepX * 0.68));

      for (let i = 0; i < this.candles.length; i++) {
        const bar = this.candles[i];
        const x = getX(i);
        const yOpen = getY(bar.open);
        const yClose = getY(bar.close);
        const yHigh = getY(bar.high);
        const yLow = getY(bar.low);

        const isBull = bar.close >= bar.open;
        const color = isBull ? '#22c55e' : '#ef4444';

        // Draw Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, yHigh);
        ctx.lineTo(x, yLow);
        ctx.stroke();

        // Draw Candle Body
        ctx.fillStyle = color;
        const bodyTop = Math.min(yOpen, yClose);
        const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyH);
      }

      // 8. Crosshair Lines
      if (this.hoveredIndex !== null && this.candles[this.hoveredIndex]) {
        const hBar = this.candles[this.hoveredIndex];
        const hX = getX(this.hoveredIndex);
        const hY = getY(hBar.close);

        ctx.save();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);

        // Vertical
        ctx.beginPath();
        ctx.moveTo(hX, paddingTop);
        ctx.lineTo(hX, height - paddingBottom);
        ctx.stroke();

        // Horizontal
        ctx.beginPath();
        ctx.moveTo(paddingLeft, hY);
        ctx.lineTo(width - paddingRight, hY);
        ctx.stroke();

        // Crosshair intersection dot
        ctx.fillStyle = '#f8fafc';
        ctx.beginPath();
        ctx.arc(hX, hY, 3, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
      }
    }

    ctx.restore();
  }

  drawLevelBadge(ctx, lvl, y, x, color, isImmRes, isImmSup) {
    ctx.save();
    const label = isImmRes ? `RES ${lvl.start_price.toFixed(0)}` :
                  isImmSup ? `SUP ${lvl.start_price.toFixed(0)}` :
                  `${lvl.type} ${lvl.start_price.toFixed(0)}`;

    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    const textWidth = ctx.measureText(label).width;
    const badgeW = Math.max(textWidth + 10, 56);
    const badgeH = 16;
    const badgeY = y - badgeH / 2;

    // Background pill
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, badgeY, badgeW, badgeH, 3);
    ctx.fill();

    // White text
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + badgeW / 2, y + 0.5);

    ctx.restore();
  }

  drawSpotBadge(ctx, spot, y, x) {
    ctx.save();
    const label = `SPOT ${spot.toFixed(1)}`;
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    const textWidth = ctx.measureText(label).width;
    const badgeW = textWidth + 10;
    const badgeH = 16;
    const badgeY = y - badgeH / 2;

    ctx.fillStyle = '#eab308';
    ctx.beginPath();
    ctx.roundRect(x, badgeY, badgeW, badgeH, 3);
    ctx.fill();

    ctx.fillStyle = '#0f172a'; // dark text on bright yellow
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + badgeW / 2, y + 0.5);

    ctx.restore();
  }

  destroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    if (this.canvas) {
      if (this._onMove) {
        this.canvas.removeEventListener('mousemove', this._onMove);
        this.canvas.removeEventListener('touchstart', this._onMove);
        this.canvas.removeEventListener('touchmove', this._onMove);
      }
      if (this._onLeave) {
        this.canvas.removeEventListener('mouseleave', this._onLeave);
        this.canvas.removeEventListener('touchend', this._onLeave);
      }
    }
    const expandBtn = this.expandBtn || this.wrapper?.querySelector('.candlestick-expand-btn');
    if (expandBtn && this._onExpandClick) {
      expandBtn.removeEventListener('click', this._onExpandClick);
    }
    this.canvas = null;
    this.ctx = null;
    if (this.wrapper && this.wrapper.parentElement) {
      this.wrapper.parentElement.removeChild(this.wrapper);
    }
  }
}
