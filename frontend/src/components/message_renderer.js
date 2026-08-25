import { QuantChart } from './quant_chart.js';
import { AppState } from '../state.js';

function detectColType(headerText, sampleCellText = '') {
  const hdr = String(headerText).trim().toUpperCase();
  const sample = String(sampleCellText).replace(/<[^>]+>/g, '').trim();

  if (hdr.includes('PREM') || hdr.includes('PRICE') || hdr.includes('VALUE') || sample.startsWith('$')) {
    return 'currency';
  }
  if (hdr.includes('%') || hdr.includes('OTM') || hdr.includes('PCT') || /^[+-]?[\d\.]+%/i.test(sample)) {
    return 'percentage';
  }
  if (hdr.includes('DATE') || hdr.includes('EXP') || hdr.includes('TIME') || /^\d{4}-\d{2}-\d{2}/.test(sample)) {
    return 'date';
  }
  if (hdr.includes('STRIKE') || hdr.includes('SIZE') || hdr.includes('OI') || hdr.includes('VOL') || hdr.includes('QTY') || /^-?[\d,]+(\.\d+)?$/.test(sample)) {
    return 'numeric';
  }
  return 'string';
}

function parseSortValue(rawText, colType = null) {
  if (rawText === null || rawText === undefined) return -Infinity;
  const clean = String(rawText).replace(/<[^>]+>/g, '').trim();
  if (!clean || clean === '-' || clean === 'N/A') return -Infinity;

  // 1. Currency / Dollar amounts (e.g. $15.50M, $10.90M, $500K, $1.85B, $500.00)
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

  // 2. Percentage values (e.g. +8.0%, -2.0%)
  const pctMatch = clean.match(/^([+-]?[\d\.]+)\s*%$/);
  if (pctMatch) {
    const p = parseFloat(pctMatch[1]);
    if (!isNaN(p)) return p;
  }

  // 3. Integer with comma / OI / Volume (e.g. 15,000, 15,000 ⚠️)
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

function renderPageNums(currentPage, totalPages) {
  if (totalPages <= 1) {
    return `<button type="button" class="bb-page-num active" data-page="1">1</button>`;
  }
  const buttons = [];
  const maxButtons = 5;
  let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage + 1 < maxButtons) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }
  for (let p = startPage; p <= endPage; p++) {
    buttons.push(`<button type="button" class="bb-page-num ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`);
  }
  return buttons.join('');
}

function buildTableHtml(tableRows) {
  if (!tableRows || tableRows.length === 0) return '';
  
  const headerRow = tableRows.find(r => r.isHeader) || tableRows[0];
  const dataRows = tableRows.filter(r => r !== headerRow && !r.isHeader);
  const totalRowsCount = dataRows.length;
  const totalPagesCount = Math.max(1, Math.ceil(totalRowsCount / 20));
  
  const tableId = `bbtbl-${Math.random().toString(36).substring(2, 9)}`;

  // Headers HTML with sortable indicators
  const thsHtml = headerRow.cells.map((c, idx) => {
    let hdr = c.trim().toUpperCase();
    let colType = detectColType(c, dataRows[0]?.cells[idx] || '');
    let accentClass = (hdr.includes("TAG") || hdr.includes("SIZE") || hdr.includes("PREMIUM") || hdr.includes("PREM")) ? ' th-accent' : '';
    return `<th class="sortable${accentClass}" data-col="${idx}" data-type="${colType}">${c} <span class="sort-icon"></span></th>`;
  }).join('');

  // Initial render: first 20 rows
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
    <div class="quant-table-wrapper" data-table-id="${tableId}" data-total-rows="${totalRowsCount}">
      <div class="quant-table-scroll">
        <table class="quant-table">
          <thead><tr>${thsHtml}</tr></thead>
          <tbody>${tbodyHtml}</tbody>
        </table>
      </div>
      <div class="bb-pagination">
        <button type="button" class="bb-page-btn btn-prev" disabled>◄ PREV</button>
        <span class="bb-page-info">PAGE 1 OF ${totalPagesCount} (${totalRowsCount} PRINTS)</span>
        <div class="bb-page-nums">${renderPageNums(1, totalPagesCount)}</div>
        <button type="button" class="bb-page-btn btn-next" ${totalPagesCount <= 1 ? 'disabled' : ''}>NEXT ►</button>
      </div>
      <script type="application/json" class="tbl-payload">${rawDataPayload}</script>
    </div>
  `;
}

export function initInteractiveTables(container = document) {
  const wrappers = container.querySelectorAll ? container.querySelectorAll('.quant-table-wrapper') : [];
  wrappers.forEach(wrapper => {
    if (wrapper.dataset.initialized === 'true') return;

    const tbody = wrapper.querySelector('tbody');
    if (!tbody) return;

    const thEls = Array.from(wrapper.querySelectorAll('th.sortable, th[data-col]'));
    const prevBtn = wrapper.querySelector('.btn-prev');
    const nextBtn = wrapper.querySelector('.btn-next');
    const pageInfo = wrapper.querySelector('.bb-page-info');
    const pageNumsContainer = wrapper.querySelector('.bb-page-nums');

    // Extract all table rows from payload or tbody
    let structuredRows = [];
    const payloadEl = wrapper.querySelector('.tbl-payload');
    if (payloadEl) {
      try {
        const parsed = JSON.parse(payloadEl.textContent);
        if (parsed.rows && Array.isArray(parsed.rows)) {
          structuredRows = parsed.rows.map((rowCells, originalIdx) => ({
            cells: rowCells,
            formattedHtml: rowCells.map(c => formatTableCell(c, false)).join(''),
            sortKeys: rowCells.map((c, colIdx) => parseSortValue(c, thEls[colIdx]?.dataset?.type)),
            originalIdx
          }));
        }
      } catch (e) {
        // Fallback to DOM extraction
      }
    }

    // Fallback if payload not present or empty
    if (structuredRows.length === 0) {
      const allTrs = Array.from(tbody.querySelectorAll('tr'));
      if (allTrs.length === 0) return;
      structuredRows = allTrs.map((tr, originalIdx) => {
        const cellEls = Array.from(tr.querySelectorAll('td'));
        const cellTexts = cellEls.map(td => td.textContent.trim());
        return {
          cells: cellTexts,
          formattedHtml: tr.innerHTML,
          sortKeys: cellTexts.map((c, colIdx) => parseSortValue(c, thEls[colIdx]?.dataset?.type)),
          originalIdx
        };
      });
    }

    const totalRows = structuredRows.length;
    let currentPage = 1;
    const pageSize = 20;

    // Default sort column: col 6 (Premium) or header matching PREMIUM/PREM
    let sortCol = 6;
    const premIdx = thEls.findIndex(th => /PREMIUM|PREM/i.test(th.textContent));
    if (premIdx !== -1) {
      sortCol = premIdx;
    } else if (sortCol >= thEls.length && thEls.length > 0) {
      sortCol = 0;
    }
    let sortDir = 'desc';

    function applySortAndRender() {
      // Sort rows
      structuredRows.sort((a, b) => {
        const valA = a.sortKeys[sortCol] !== undefined ? a.sortKeys[sortCol] : -Infinity;
        const valB = b.sortKeys[sortCol] !== undefined ? b.sortKeys[sortCol] : -Infinity;

        if (typeof valA === 'number' && typeof valB === 'number') {
          return sortDir === 'asc' ? valA - valB : valB - valA;
        }
        if (valA < valB) return sortDir === 'asc' ? -1 : 1;
        if (valA > valB) return sortDir === 'asc' ? 1 : -1;
        return a.originalIdx - b.originalIdx;
      });

      const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
      if (currentPage > totalPages) currentPage = totalPages;
      if (currentPage < 1) currentPage = 1;

      // Slice current page
      const startIdx = (currentPage - 1) * pageSize;
      const pageSlice = structuredRows.slice(startIdx, startIdx + pageSize);

      // Render 20 rows in tbody
      let rowsHtml = '';
      pageSlice.forEach(row => {
        rowsHtml += `<tr>${row.formattedHtml}</tr>`;
      });
      tbody.innerHTML = rowsHtml;

      // Update Pagination Toolbar
      if (pageInfo) {
        pageInfo.textContent = `PAGE ${currentPage} OF ${totalPages} (${totalRows} PRINTS)`;
      }
      if (prevBtn) {
        prevBtn.disabled = currentPage === 1;
      }
      if (nextBtn) {
        nextBtn.disabled = currentPage === totalPages;
      }
      if (pageNumsContainer) {
        pageNumsContainer.innerHTML = renderPageNums(currentPage, totalPages);
        pageNumsContainer.querySelectorAll('.bb-page-num').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const p = parseInt(btn.dataset.page, 10);
            if (!isNaN(p) && p !== currentPage) {
              currentPage = p;
              applySortAndRender();
            }
          });
        });
      }

      // Update Header Sort Icons & Classes
      thEls.forEach((th, idx) => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (idx === sortCol) {
          th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
        }
      });
    }

    // Attach Header Click Event Listeners
    thEls.forEach((th, idx) => {
      th.addEventListener('click', () => {
        const colIdx = parseInt(th.dataset.col !== undefined ? th.dataset.col : idx, 10);
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

    // Attach Pagination Controls
    if (prevBtn) {
      prevBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (currentPage > 1) {
          currentPage--;
          applySortAndRender();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
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

export const initQuantTables = initInteractiveTables;

if (typeof window !== 'undefined') {
  window.initInteractiveTables = initInteractiveTables;
  window.initQuantTables = initInteractiveTables;
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

  bubble.appendChild(contentDiv);

  // Initialize interactive Bloomberg tables on message bubble
  initInteractiveTables(bubble);

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
