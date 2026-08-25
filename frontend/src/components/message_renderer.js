import { QuantChart } from './quant_chart.js';
import { AppState } from '../state.js';

function parseSortValue(rawText) {
  if (!rawText) return -Infinity;
  const clean = String(rawText).replace(/<[^>]+>/g, '').trim();

  // 1. Currency / Dollar amounts (e.g. $25.00M, $780.00K, $1.85B, $500.00)
  const premMatch = clean.match(/^\$?([\d\.,]+)\s*([KMB])?$/i);
  if (premMatch) {
    const num = parseFloat(premMatch[1].replace(/,/g, ''));
    const unit = (premMatch[2] || '').toUpperCase();
    if (!isNaN(num)) {
      if (unit === 'B') return num * 1_000_000_000;
      if (unit === 'M') return num * 1_000_000;
      if (unit === 'K') return num * 1_000;
      return num;
    }
  }

  // 2. Percentage values (e.g. +2.0%, -5.5%)
  const pctMatch = clean.match(/^([+-]?[\d\.]+)\s*%$/);
  if (pctMatch) {
    const p = parseFloat(pctMatch[1]);
    if (!isNaN(p)) return p;
  }

  // 3. Integer with comma / OI (e.g. 15,000, 15,000 ⚠️)
  const oiMatch = clean.match(/^([\d,]+)/);
  if (oiMatch && clean.replace(/[^0-9,]/g, '').length === clean.length) {
    const oi = parseInt(oiMatch[1].replace(/,/g, ''), 10);
    if (!isNaN(oi)) return oi;
  }

  // 4. ISO Date (e.g. 2026-08-21)
  if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) {
    const ts = Date.parse(clean);
    if (!isNaN(ts)) return ts;
  }

  // 5. Raw numeric float
  const f = parseFloat(clean.replace(/,/g, ''));
  if (!isNaN(f) && String(f) === clean.replace(/,/g, '')) {
    return f;
  }

  // Default string comparison
  return clean.toLowerCase();
}

function formatTableCell(content, isHeader) {
  if (isHeader) {
    let hdr = content.trim().toUpperCase();
    if (hdr.includes("TAG") || hdr.includes("SIZE")) {
      return `<th class="th-accent">${content}</th>`;
    }
    return `<th>${content}</th>`;
  }
  
  let trimmed = content.trim();
  
  // 1. Binary Action Formatting (Green = Bullish, Red = Bearish)
  if (/^(?:<strong>)?(?:BUY[_\s]+CALL|CALL)(?:<\/strong>)?$/i.test(trimmed)) {
    return `<td><span class="bb-action bb-action-bull">BUY CALL</span></td>`;
  }
  if (/^(?:<strong>)?(?:SELL[_\s]+PUT)(?:<\/strong>)?$/i.test(trimmed)) {
    return `<td><span class="bb-action bb-action-bull">SELL PUT</span></td>`;
  }
  if (/^(?:<strong>)?(?:BUY[_\s]+PUT|PUT)(?:<\/strong>)?$/i.test(trimmed)) {
    return `<td><span class="bb-action bb-action-bear">BUY PUT</span></td>`;
  }
  if (/^(?:<strong>)?(?:SELL[_\s]+CALL)(?:<\/strong>)?$/i.test(trimmed)) {
    return `<td><span class="bb-action bb-action-bear">SELL CALL</span></td>`;
  }
  
  // 2. Format Ticker Symbols (e.g. **AMD** or AMD)
  if (/^<strong>[A-Z0-9\.\/]{1,6}<\/strong>$/i.test(trimmed) || /^[A-Z0-9\.\/]{1,6}$/.test(trimmed)) {
    const rawSym = trimmed.replace(/<\/?strong>/gi, '');
    return `<td><span class="bb-ticker">${rawSym}</span></td>`;
  }
  
  // 3. Format Premium with Whale / Large Size Indicator
  const premMatch = trimmed.match(/^\$?([\d\.,]+)\s*([KMB])?$/i) || trimmed.match(/^<strong>\$?([\d\.,]+)\s*([KMB])?<\/strong>$/i);
  if (premMatch || trimmed.startsWith("$")) {
    const rawPrem = trimmed.replace(/<\/?strong>/gi, '');
    let tagHtml = '';
    
    // Parse numeric value in millions
    if (premMatch) {
      const num = parseFloat(premMatch[1].replace(/,/g, ''));
      const unit = (premMatch[2] || '').toUpperCase();
      let valInM = 0;
      if (unit === 'B') valInM = num * 1000;
      else if (unit === 'M') valInM = num;
      else if (unit === 'K') valInM = num / 1000;
      else valInM = num / 1000000; // Raw integer dollar amount (e.g. $5,000,000)
      
      if (valInM >= 5.0) {
        tagHtml = ` <span class="bb-tag bb-tag-whale">[WHALE]</span>`;
      } else if (valInM >= 1.0) {
        tagHtml = ` <span class="bb-tag bb-tag-large">[LARGE]</span>`;
      }
    }
    
    return `<td><span class="bb-prem">${rawPrem}</span>${tagHtml}</td>`;
  }
  
  // 4. Format OTM % (e.g. +8.0% or -2.0%)
  if (/^\+[\d\.]+%$/.test(trimmed)) {
    return `<td><span class="bb-otm-pos">${trimmed}</span></td>`;
  }
  if (/^\-[\d\.]+%$/.test(trimmed)) {
    return `<td><span class="bb-otm-neg">${trimmed}</span></td>`;
  }

  return `<td>${content}</td>`;
}

function buildTableHtml(tableRows) {
  if (!tableRows || tableRows.length === 0) return '';
  
  const headerRow = tableRows.find(r => r.isHeader) || tableRows[0];
  const dataRows = tableRows.filter(r => r !== headerRow && !r.isHeader);
  const totalRowsCount = dataRows.length;
  
  const tableId = `bbtbl-${Math.random().toString(36).substring(2, 9)}`;

  // Headers HTML
  const thsHtml = headerRow.cells.map((c, idx) => {
    let hdr = c.trim().toUpperCase();
    let accentClass = (hdr.includes("TAG") || hdr.includes("SIZE") || hdr.includes("PREMIUM")) ? ' th-accent' : '';
    return `<th class="quant-table-th-sortable${accentClass}" data-col-idx="${idx}">
      <div class="th-content">
        <span>${c}</span>
        <span class="th-sort-icon"></span>
      </div>
    </th>`;
  }).join('');

  // Initial first 20 rows HTML for fast SSR/render
  const initialSlice = dataRows.slice(0, 20);
  let tbodyHtml = '';
  initialSlice.forEach(row => {
    const cellsHtml = row.cells.map(c => formatTableCell(c, false)).join('');
    tbodyHtml += `<tr>${cellsHtml}</tr>`;
  });

  const rawDataPayload = JSON.stringify({
    headers: headerRow.cells,
    rows: dataRows.map(r => r.cells)
  }).replace(/</g, '\\u003c');

  return `
    <div class="quant-table-wrapper" id="${tableId}" data-total-rows="${totalRowsCount}">
      <div class="quant-table-toolbar">
        <div class="qt-toolbar-left">
          <span class="qt-brand-tag">BLOOMBERG FLOW</span>
          <span class="qt-total-badge">${totalRowsCount} PRINTS</span>
        </div>
        <div class="qt-pagination-controls">
          <button type="button" class="qt-page-btn qt-prev-btn" title="Previous Page">◄ Prev</button>
          <span class="qt-page-indicator">Page 1 of ${Math.max(1, Math.ceil(totalRowsCount / 20))}</span>
          <button type="button" class="qt-page-btn qt-next-btn" title="Next Page">Next ►</button>
        </div>
      </div>
      <div class="quant-table-scroll">
        <table class="quant-table">
          <thead><tr>${thsHtml}</tr></thead>
          <tbody>${tbodyHtml}</tbody>
        </table>
      </div>
      <script type="application/json" class="tbl-payload">${rawDataPayload}</script>
    </div>
  `;
}

export function initQuantTables(container = document) {
  const wrappers = container.querySelectorAll('.quant-table-wrapper');
  wrappers.forEach(wrapper => {
    if (wrapper.dataset.initialized === 'true') return;
    
    const payloadEl = wrapper.querySelector('.tbl-payload');
    if (!payloadEl) return;

    let tableData;
    try {
      tableData = JSON.parse(payloadEl.textContent);
    } catch (e) {
      return;
    }

    const { headers, rows } = tableData;
    if (!rows || rows.length === 0) return;

    // Find default sort column (prefer PREMIUM or PREM, default descending)
    let sortCol = headers.findIndex(h => /PREMIUM|PREM/i.test(h));
    if (sortCol === -1) sortCol = 0;
    let sortDir = 'desc';

    let currentPage = 1;
    const pageSize = 20;

    // Pre-calculate sort keys for high performance
    const processedRows = rows.map((r, originalIdx) => ({
      cells: r,
      sortKeys: r.map(c => parseSortValue(c)),
      originalIdx
    }));

    const tbody = wrapper.querySelector('tbody');
    const thEls = wrapper.querySelectorAll('.quant-table-th-sortable');
    const prevBtn = wrapper.querySelector('.qt-prev-btn');
    const nextBtn = wrapper.querySelector('.qt-next-btn');
    const pageIndicator = wrapper.querySelector('.qt-page-indicator');

    function applySortAndRender() {
      // Sort rows
      processedRows.sort((a, b) => {
        const valA = a.sortKeys[sortCol];
        const valB = b.sortKeys[sortCol];

        if (typeof valA === 'number' && typeof valB === 'number') {
          return sortDir === 'asc' ? valA - valB : valB - valA;
        }
        if (valA < valB) return sortDir === 'asc' ? -1 : 1;
        if (valA > valB) return sortDir === 'asc' ? 1 : -1;
        return a.originalIdx - b.originalIdx;
      });

      const totalPages = Math.max(1, Math.ceil(processedRows.length / pageSize));
      if (currentPage > totalPages) currentPage = totalPages;
      if (currentPage < 1) currentPage = 1;

      // Slice page
      const startIdx = (currentPage - 1) * pageSize;
      const pageRows = processedRows.slice(startIdx, startIdx + pageSize);

      // Render table rows
      let rowsHtml = '';
      pageRows.forEach(row => {
        const cellsHtml = row.cells.map(c => formatTableCell(c, false)).join('');
        rowsHtml += `<tr>${cellsHtml}</tr>`;
      });
      tbody.innerHTML = rowsHtml;

      // Update Toolbar
      if (pageIndicator) {
        pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
      }
      if (prevBtn) {
        prevBtn.disabled = currentPage <= 1;
      }
      if (nextBtn) {
        nextBtn.disabled = currentPage >= totalPages;
      }

      // Update Sort Icons
      thEls.forEach((th, idx) => {
        const icon = th.querySelector('.th-sort-icon');
        if (idx === sortCol) {
          th.classList.add('sorted');
          if (icon) icon.textContent = sortDir === 'asc' ? ' ▲' : ' ▼';
        } else {
          th.classList.remove('sorted');
          if (icon) icon.textContent = '';
        }
      });
    }

    // Attach Header Click Events (Click to Sort)
    thEls.forEach((th) => {
      th.addEventListener('click', () => {
        const colIdx = parseInt(th.dataset.colIdx, 10);
        if (sortCol === colIdx) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortCol = colIdx;
          sortDir = 'desc';
        }
        currentPage = 1;
        applySortAndRender();
      });
    });

    // Attach Pagination Events
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
          currentPage--;
          applySortAndRender();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        const totalPages = Math.max(1, Math.ceil(processedRows.length / pageSize));
        if (currentPage < totalPages) {
          currentPage++;
          applySortAndRender();
        }
      });
    }

    // Initial render & mark initialized
    applySortAndRender();
    wrapper.dataset.initialized = 'true';
  });
}

if (typeof window !== 'undefined') {
  window.initQuantTables = initQuantTables;
}

function parseMarkdownTables(text) {
  const lines = text.split('\n');
  const result = [];
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      // Check if it's a separator line (e.g. | :--- | :--- |)
      if (/^\|(?:\s*:?-+:?\s*\|)+$/.test(line)) {
        if (tableRows.length > 0) {
          tableRows[tableRows.length - 1].isHeader = true;
        }
        continue;
      }
      
      const cells = line
        .slice(1, -1)
        .split('|')
        .map(c => c.trim());
      
      tableRows.push({ cells, isHeader: false });
      inTable = true;
    } else {
      if (inTable) {
        result.push(buildTableHtml(tableRows));
        tableRows = [];
        inTable = false;
      }
      result.push(lines[i]);
    }
  }

  if (inTable && tableRows.length > 0) {
    result.push(buildTableHtml(tableRows));
  }

  return result.join('\n');
}

export function renderMarkdown(text) {
  if (!text) return '';

  let html = text;

  // Escape raw HTML tags to prevent XSS
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks: ```lang ... ```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.parentElement.querySelector('code').innerText);this.innerText='Copied!';setTimeout(()=>this.innerText='Copy',1500)">Copy</button><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Images: ![alt](url) -> Fallback to interactive card if no Canvas chart was mounted
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, (match, alt, url) => {
    return `
      <div class="chart-card fallback" onclick="window.quantLightbox && window.quantLightbox.open('${url}', '${alt}')">
        <img class="chart-img" src="${url}" alt="${alt}" loading="lazy" />
        <div class="chart-hint">
          <span>${alt || 'OPTIONS EXPOSURE CHART'}</span>
          <span>EXPAND</span>
        </div>
      </div>
    `;
  });

  // Headers: ### Header
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Bullet points
  html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
  html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Parse Markdown Tables before line break processing
  html = parseMarkdownTables(html);

  // Line breaks & paragraphs (protect table blocks from broken <br/> tags)
  const parts = html.split(/(<div class="quant-table-wrapper"[\s\S]*?<\/div>\s*<\/div>)/g);
  html = parts.map(part => {
    if (part.startsWith('<div class="quant-table-wrapper"')) {
      return part;
    }
    return part
      .replace(/\n\n/g, '<p></p>')
      .replace(/\n/g, '<br/>');
  }).join('');

  return html;
}

export function createMessageElement(role, content, metadata = null, toolUiEvents = [], metrics = null) {
  const bubble = document.createElement('div');
  bubble.className = `message-bubble ${role}`;

  const resolvedMetrics = metrics || metadata?.metrics || null;
  if (resolvedMetrics) {
    bubble.dataset.metrics = JSON.stringify(resolvedMetrics);
  }

  let badgeHtml = '';
  if (role === 'assistant' && metadata?.market) {
    const isClosed = metadata.market.status !== 'REGULAR_HOURS';
    badgeHtml = `
      <div class="market-badge ${isClosed ? 'closed' : ''}">
        <span class="dot"></span>
        <span>${metadata.market.status}: ${metadata.market.current_time_ny}</span>
      </div>
    `;
  }

  // 1. If single-flight Tool UI events exist, mount interactive Canvas charts
  if (role === 'assistant' && toolUiEvents && toolUiEvents.length > 0) {
    toolUiEvents.forEach(evt => {
      if (evt.name === 'get_gexdex' && evt.payload) {
        const chartBox = document.createElement('div');
        chartBox.className = 'tool-ui-slot';
        new QuantChart(chartBox, evt.payload);
        bubble.appendChild(chartBox);
      }
    });
  }

  // 2. Strip redundant or static markdown chart images
  let cleanedContent = (content || '')
    .replace(/!\[.*?\]\([^)]*(?:chart|gexdex)[^)]*\)/gi, '')
    .replace(/!\[.*?\]\([^)]*\.(?:png|webp|jpg|jpeg)[^)]*\)/gi, '');
  
  if (toolUiEvents && toolUiEvents.length > 0) {
    cleanedContent = cleanedContent.replace(/!\[.*?\]\(.*?\)/gi, '').trim();
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'markdown-body';
  contentDiv.innerHTML = badgeHtml + renderMarkdown(cleanedContent.trim());

  // Initialize interactive Bloomberg tables
  initQuantTables(contentDiv);

  bubble.appendChild(contentDiv);

  // 3. Render subtle latency badge in assistant message footer if metrics exist
  if (role === 'assistant' && resolvedMetrics) {
    const totalMs = Math.round(resolvedMetrics.total_ms || resolvedMetrics.duration_ms || 0);
    const rawTok = resolvedMetrics.tok_per_sec || resolvedMetrics.tokens_per_sec || 48.2;
    const tokPerSec = typeof rawTok === 'number' ? rawTok.toFixed(1) : String(rawTok);
    const isCacheHit = Boolean(resolvedMetrics.cache_hit || resolvedMetrics.cached || resolvedMetrics.cache_status === 'HIT' || resolvedMetrics.cacheStatus === 'HIT');
    const cacheStatus = isCacheHit ? 'HIT' : 'MISS';

    const tier = resolvedMetrics.tier_used || resolvedMetrics.tier || '';
    const model = resolvedMetrics.model_used || resolvedMetrics.model || '';
    const isStrategic = tier === 'strategic' || (typeof model === 'string' && model.includes('3.7'));
    const tierBadge = isStrategic
      ? `<span class="inst-tag inst-tag-strategic"><span class="status-dot dot-strategic"></span>STRATEGIC · 3.7-FLASH</span>`
      : `<span class="inst-tag inst-tag-fast"><span class="status-dot dot-fast"></span>FAST · 3.5-LITE</span>`;

    const showDiagnostics = AppState.getShowDiagnostics ? AppState.getShowDiagnostics() : (localStorage.getItem('quant_show_diagnostics') !== 'false');

    const footer = document.createElement('div');
    footer.className = 'message-meta-footer';
    if (!showDiagnostics) {
      footer.style.display = 'none';
    }

    const pill = document.createElement('span');
    pill.className = 'latency-pill';
    pill.innerHTML = `${tierBadge} <span class="inst-stats">${totalMs}ms · ${tokPerSec} tok/s</span> <span class="inst-cache">[CACHE: ${cacheStatus}]</span>`;
    pill.title = 'Tap to view performance diagnostics waterfall';

    pill.addEventListener('click', (e) => {
      e.stopPropagation();
      if (window.quantDiagnostics) {
        window.quantDiagnostics.open(resolvedMetrics);
      }
    });

    footer.appendChild(pill);
    bubble.appendChild(footer);
  }

  return bubble;
}
