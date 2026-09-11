
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
  const clean = String(rawText).replace(/<[^>]+>/g, '').replace(/\[.*?\]/g, '').trim();
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
  
  // 3. Format Premium
  const premMatch = trimmed.match(/^\$?([\d\.,]+)\s*([KMB])?$/i) || trimmed.match(/^<strong>\$?([\d\.,]+)\s*([KMB])?<\/strong>$/i);
  if (premMatch || trimmed.startsWith("$")) {
    const rawPrem = trimmed.replace(/<\/?strong>/gi, '');
    return `<td><span class="bb-prem">${rawPrem}</span></td>`;
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
    // Explicitly ignore tables that manage their own sorting/data (e.g. Confluence Radar)
    if (wrapper.classList.contains('radar-table-wrapper') || (wrapper.closest && wrapper.closest('.radar-view-container')) || wrapper.id === 'radarTableWrapper') {
      return;
    }
    if (wrapper.dataset.initialized === 'true' && wrapper._tableController) return;

    const tbody = wrapper.querySelector('tbody');
    if (!tbody) return;

    const thEls = Array.from(wrapper.querySelectorAll('th.sortable, th[data-col]'));
    const prevBtn = wrapper.querySelector('.btn-prev');
    const nextBtn = wrapper.querySelector('.btn-next');
    const pageInfo = wrapper.querySelector('.bb-page-info');
    const pageNumsContainer = wrapper.querySelector('.bb-page-nums');

    // Find Premium column index for secondary tie-breaker & default sort
    const premIdx = thEls.findIndex(th => /PREMIUM|PREM/i.test(th.textContent));

    // Extract all table rows from payload or tbody
    let structuredRows = [];
    const payloadEl = wrapper.querySelector('.tbl-payload');
    if (payloadEl) {
      try {
        const parsed = JSON.parse(payloadEl.textContent);
        if (parsed.rows && Array.isArray(parsed.rows)) {
          structuredRows = parsed.rows.map((rowCells, originalIdx) => {
            const sortKeys = rowCells.map((c, colIdx) => parseSortValue(c, thEls[colIdx]?.dataset?.type));
            const rawPremVal = premIdx !== -1 ? sortKeys[premIdx] : parseSortValue(rowCells.find(c => /^\$?[\d\.,]+[KMB]?$/i.test(String(c).trim())) || 0, 'currency');
            const premVal = (typeof rawPremVal === 'number' && rawPremVal !== -Infinity) ? rawPremVal : 0;
            return {
              cells: rowCells,
              formattedHtml: rowCells.map(c => formatTableCell(c, false)).join(''),
              sortKeys,
              originalIdx,
              premVal
            };
          });
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
        const sortKeys = cellTexts.map((c, colIdx) => parseSortValue(c, thEls[colIdx]?.dataset?.type));
        const rawPremVal = premIdx !== -1 ? sortKeys[premIdx] : parseSortValue(cellTexts.find(c => /^\$?[\d\.,]+[KMB]?$/i.test(String(c).trim())) || 0, 'currency');
        const premVal = (typeof rawPremVal === 'number' && rawPremVal !== -Infinity) ? rawPremVal : 0;
        return {
          cells: cellTexts,
          formattedHtml: tr.innerHTML,
          sortKeys,
          originalIdx,
          premVal
        };
      });
    }

    const totalRows = structuredRows.length;
    let currentPage = 1;
    const pageSize = 20;

    // Default sort column: col 6 (Premium) or header matching PREMIUM/PREM
    let sortCol = premIdx !== -1 ? premIdx : (thEls.length > 6 ? 6 : 0);
    let sortDir = 'desc';

    function applySortAndRender() {
      // Sort rows
      if (sortCol === null || sortDir === null) {
        // Reset to Default Natural Order
        structuredRows.sort((a, b) => a.originalIdx - b.originalIdx);
      } else {
        structuredRows.sort((a, b) => {
          const valA = a.sortKeys[sortCol] !== undefined ? a.sortKeys[sortCol] : -Infinity;
          const valB = b.sortKeys[sortCol] !== undefined ? b.sortKeys[sortCol] : -Infinity;

          let diff = 0;
          if (typeof valA === 'number' && typeof valB === 'number') {
            diff = sortDir === 'asc' ? valA - valB : valB - valA;
          } else {
            const strA = String(valA);
            const strB = String(valB);
            if (strA < strB) diff = sortDir === 'asc' ? -1 : 1;
            else if (strA > strB) diff = sortDir === 'asc' ? 1 : -1;
          }

          if (diff !== 0) return diff;

          // Secondary Tie-Breaking: highest premium first (descending)
          const premDiff = (b.premVal || 0) - (a.premVal || 0);
          if (premDiff !== 0) return premDiff;

          return a.originalIdx - b.originalIdx;
        });
      }

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
      }

      // Update Header Sort Icons & Classes
      thEls.forEach((th, idx) => {
        th.classList.remove('sort-asc', 'sort-desc');
        const colIdx = parseInt(th.dataset.col !== undefined ? th.dataset.col : idx, 10);
        if (sortCol !== null && colIdx === sortCol) {
          th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
        }
      });
    }

    // Unified Event Delegation on wrapper
    wrapper.addEventListener('click', (e) => {
      const th = e.target.closest ? e.target.closest('th.sortable, th[data-col]') : null;
      if (th && wrapper.contains(th)) {
        e.preventDefault();
        e.stopPropagation();
        const colIdx = parseInt(th.dataset.col !== undefined ? th.dataset.col : thEls.indexOf(th), 10);
        handleSortClick(colIdx);
        return;
      }

      const prev = e.target.closest ? e.target.closest('.btn-prev') : null;
      if (prev && wrapper.contains(prev)) {
        e.preventDefault();
        e.stopPropagation();
        if (currentPage > 1) {
          currentPage--;
          applySortAndRender();
        }
        return;
      }

      const next = e.target.closest ? e.target.closest('.btn-next') : null;
      if (next && wrapper.contains(next)) {
        e.preventDefault();
        e.stopPropagation();
        const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
        if (currentPage < totalPages) {
          currentPage++;
          applySortAndRender();
        }
        return;
      }

      const pageNumBtn = e.target.closest ? e.target.closest('.bb-page-num') : null;
      if (pageNumBtn && wrapper.contains(pageNumBtn)) {
        e.preventDefault();
        e.stopPropagation();
        const p = parseInt(pageNumBtn.dataset.page, 10);
        if (!isNaN(p) && p !== currentPage) {
          currentPage = p;
          applySortAndRender();
        }
        return;
      }
    });

    function handleSortClick(colIdx) {
      if (sortCol !== colIdx) {
        // Click 1: New Column -> Descending
        sortCol = colIdx;
        sortDir = 'desc';
      } else if (sortDir === 'desc') {
        // Click 2: Same Column -> Ascending
        sortDir = 'asc';
      } else if (sortDir === 'asc') {
        // Click 3: Same Column -> Reset to Default Natural Order
        sortCol = null;
        sortDir = null;
      } else {
        sortCol = colIdx;
        sortDir = 'desc';
      }
      currentPage = 1;
      applySortAndRender();
    }

    // Direct element listeners for non-bubbling / direct dispatch environments
    thEls.forEach((th, idx) => {
      th.addEventListener('click', (e) => {
        if (e && e.stopPropagation) e.stopPropagation();
        const colIdx = parseInt(th.dataset.col !== undefined ? th.dataset.col : idx, 10);
        handleSortClick(colIdx);
      });
    });

    if (prevBtn) {
      prevBtn.addEventListener('click', (e) => {
        if (e && e.stopPropagation) e.stopPropagation();
        if (currentPage > 1) {
          currentPage--;
          applySortAndRender();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', (e) => {
        if (e && e.stopPropagation) e.stopPropagation();
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
    wrapper._tableController = {
      applySortAndRender,
      getSortCol: () => sortCol,
      getSortDir: () => sortDir,
      getCurrentPage: () => currentPage,
      getTotalRows: () => totalRows
    };
  });
}

export const initQuantTables = initInteractiveTables;

if (typeof window !== 'undefined') {
  window.initInteractiveTables = initInteractiveTables;
  window.initQuantTables = initInteractiveTables;
}

// Global auto-init capture listener for dynamic or late-rendered tables
if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
  document.addEventListener('click', (e) => {
    const tableWrapper = e.target && e.target.closest ? e.target.closest('.quant-table-wrapper') : null;
    if (tableWrapper) {
      if (tableWrapper.classList.contains('radar-table-wrapper') || (tableWrapper.closest && tableWrapper.closest('.radar-view-container')) || tableWrapper.id === 'radarTableWrapper') {
        return;
      }
      if (!tableWrapper.dataset.initialized || !tableWrapper._tableController) {
        initInteractiveTables(tableWrapper.parentElement || document);
      }
    }
  }, true);
}

function parseMarkdownTables(text) {
  const lines = text.split('\n');
  const result = [];
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    // Check if line looks like a markdown table row (starts with | or contains at least 2 pipes)
    if (line.startsWith('|') && (line.endsWith('|') || line.split('|').length >= 3)) {
      // Check if it's a separator line (e.g. | :--- | :--- | or |---|---|)
      if (/^\|(?:\s*:?-+:?\s*\|?)+$/.test(line)) {
        if (tableRows.length > 0) {
          tableRows[tableRows.length - 1].isHeader = true;
        }
        continue;
      }
      
      let rawCells = line;
      if (rawCells.startsWith('|')) rawCells = rawCells.slice(1);
      if (rawCells.endsWith('|')) rawCells = rawCells.slice(0, -1);
      const cells = rawCells.split('|').map(c => c.trim());
      
      if (cells.length > 1) {
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

function parseNotableFlow(text, storage) {
  if (!text) return text;

  const nfRegex = /(?:^[•*-]?\s*|\n[•*-]?\s*)\*\*Notable Flow\*\*:\s*(?:\n|$)([\s\S]*?)(?=(?:\n[•*-]\s*\*\*|\n###|$))/i;
  const match = text.match(nfRegex);
  if (!match) return text;

  const content = match[1];

  const tpRegex = /[•*-]?\s*\*\*TOP PREMIUM\*\*:\s*(?:\n|$)([\s\S]*?)(?=[•*-]?\s*\*\*NOTABLE OTM\*\*|$)/i;
  const tpMatch = content.match(tpRegex);
  const tpRawLines = tpMatch ? tpMatch[1].trim().split('\n').map(l => l.trim()).filter(Boolean) : [];

  const otmRegex = /[•*-]?\s*\*\*NOTABLE OTM\*\*:\s*(?:\n|$)([\s\S]*?)$/i;
  const otmMatch = content.match(otmRegex);
  const otmRawLines = otmMatch ? otmMatch[1].trim().split('\n').map(l => l.trim()).filter(Boolean) : [];

  function parseItems(lines, type) {
    if (!lines.length || lines.some(l => l.toUpperCase().includes('NONE FOUND'))) {
      return `<div class="notable-flow-empty"><span class="empty-bullet">○</span> NONE FOUND</div>`;
    }

    return lines.map(line => {
      const clean = line.replace(/^[-*•]\s*/, '').trim();
      if (!clean) return '';

      if (type === 'premium') {
        const m = clean.match(/^([A-Z0-9.\-_]+)\s+(\$[0-9.]+[KMBkmb]?)\s+PREMIUM\s*\(([^)]+)\)/i);
        if (m) {
          const [_, sym, prem, rank] = m;
          return `
            <div class="notable-flow-row" data-ticker="${sym}" title="Click to inspect ${sym} in Cockpit">
              <div class="notable-sym-group">
                <span class="notable-ticker-badge">${sym}</span>
                <span class="notable-rank-pill">${rank}</span>
              </div>
              <div class="notable-metric-group">
                <span class="notable-metric-val val-premium">${prem}</span>
                <span class="notable-metric-label">PREMIUM (${rank})</span>
              </div>
            </div>
          `.trim();
        }
      } else {
        const m = clean.match(/^([A-Z0-9.\-_]+)\s+([+-]?[0-9.]+%?)\s*OTM\s+(.*)$/i);
        if (m) {
          const [_, sym, otm, exp] = m;
          const cleanOtm = otm.endsWith('%') ? otm : `${otm}%`;
          return `
            <div class="notable-flow-row" data-ticker="${sym}" title="Click to inspect ${sym} in Cockpit">
              <div class="notable-sym-group">
                <span class="notable-ticker-badge">${sym}</span>
                <span class="notable-dte-pill">${exp}</span>
              </div>
              <div class="notable-metric-group">
                <span class="notable-metric-val val-otm">${cleanOtm}</span>
                <span class="notable-metric-label">OTM</span>
              </div>
            </div>
          `.trim();
        }
      }
      return `<div class="notable-flow-row raw-line">${clean}</div>`;
    }).filter(Boolean).join('\n');
  }

  const tpHtml = parseItems(tpRawLines, 'premium');
  const otmHtml = parseItems(otmRawLines, 'otm');

  const cardHtml = `
<div class="notable-flow-container">
  <div class="notable-flow-header">
    <span class="notable-flow-header-dot"></span>
    <span class="notable-flow-header-title">Notable Flow</span>
    <span class="notable-flow-header-hint">Tap any ticker to inspect in Cockpit ↗</span>
  </div>
  <div class="notable-flow-grid">
    <div class="notable-flow-card card-premium">
      <div class="notable-flow-card-header">
        <span class="notable-card-icon">💰</span>
        <span class="notable-card-title">TOP PREMIUM</span>
        <span class="notable-card-subtitle">All-Time Highs</span>
      </div>
      <div class="notable-flow-list">
        ${tpHtml}
      </div>
    </div>
    <div class="notable-flow-card card-otm">
      <div class="notable-flow-card-header">
        <span class="notable-card-icon">⚡</span>
        <span class="notable-card-title">NOTABLE OTM</span>
        <span class="notable-card-subtitle">&ge;10% OTM Speculation</span>
      </div>
      <div class="notable-flow-list">
        ${otmHtml}
      </div>
    </div>
  </div>
</div>
  `.trim();

  const id = storage.length;
  storage.push(cardHtml);
  return text.replace(match[0], `<!--___NOTABLE_FLOW_BLOCK_${id}___-->`);
}

export function renderMarkdown(text) {
  if (!text) return '';

  let html = text;

  // 1. Unwrap any Markdown tables enclosed in triple backticks (e.g. ```markdown\n| Symbol | ... \n``` or ``` ... ```)
  html = html.replace(/```(?:markdown|md|table)?\s*\n?(\|[\s\S]*?\|)\s*\n?```/gi, '\n$1\n');
  // Also unwrap streaming unclosed code blocks that start with a table
  html = html.replace(/```(?:markdown|md|table)?\s*\n?(\|[\s\S]*?\|)\s*$/gi, '\n$1\n');

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

  // Parse Notable Flow into structured cards
  const notableFlowBlocks = [];
  html = parseNotableFlow(html, notableFlowBlocks);

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

  // Line breaks & paragraphs (protect table blocks and notable flow blocks from broken <br/> tags)
  const parts = html.split(/(<div class="quant-table-wrapper"[\s\S]*?<\/div>\s*<\/div>)/g);
  html = parts.map(part => {
    if (part.startsWith('<div class="quant-table-wrapper"')) {
      return part;
    }
    return part
      .replace(/\n\n/g, '<p></p>')
      .replace(/\n/g, '<br/>');
  }).join('');

  // Restore protected notable flow blocks
  html = html.replace(/<!--___NOTABLE_FLOW_BLOCK_(\d+)___-->/g, (_, idx) => notableFlowBlocks[parseInt(idx, 10)] || '');

  return html;
}


