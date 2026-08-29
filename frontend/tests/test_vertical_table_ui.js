/**
 * Automated In-Situ Test Probe for Quant Options Flow Interactive Tables (FLOW-08)
 *
 * Tests:
 * 1. Tri-State Column Sorting Engine:
 *    - Click 1: Descending
 *    - Click 2: Ascending
 *    - Click 3: Reset to Default Natural Order
 * 2. Secondary Tie-Breaker:
 *    - On equal values, tie-break by Premium descending (highest premium first)
 * 3. Automatic Page 1 Reset on Sort
 * 4. Pagination (Previous / Next / Page Numbers)
 * 5. Sort indicator classes & Header styling
 */

// ============================================================================
// 1. High-Fidelity In-Memory Mock DOM Environment
// ============================================================================

class MockClassList {
  constructor(el) {
    this._el = el;
    this._classes = new Set();
  }
  add(...classes) {
    classes.forEach(c => c && this._classes.add(c));
    this._sync();
  }
  remove(...classes) {
    classes.forEach(c => this._classes.delete(c));
    this._sync();
  }
  contains(cls) {
    return this._classes.has(cls);
  }
  toggle(cls) {
    if (this._classes.has(cls)) {
      this._classes.delete(cls);
    } else {
      this._classes.add(cls);
    }
    this._sync();
  }
  _sync() {
    this._el._className = Array.from(this._classes).join(' ');
  }
}

function parseAttributes(attrStr, el) {
  if (!attrStr) return;
  const attrRegex = /([a-zA-Z0-9\-_]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  let m;
  while ((m = attrRegex.exec(attrStr)) !== null) {
    const name = m[1];
    const val = m[2] !== undefined ? m[2] : (m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : ''));
    if (name === 'class') {
      el.className = val;
    } else if (name.startsWith('data-')) {
      const camelKey = name.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
      el.dataset[camelKey] = val;
    } else if (name === 'disabled') {
      el.disabled = true;
    } else if (name === 'type') {
      el.type = val;
    } else {
      el[name] = val;
    }
  }
}

function matchesSelector(el, selector) {
  const parts = selector.split(',').map(s => s.trim());
  return parts.some(part => {
    const tagMatch = part.match(/^([a-zA-Z0-9\-]+)/);
    if (tagMatch) {
      if (el.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
    }
    const classMatches = part.match(/\.([a-zA-Z0-9\-_]+)/g);
    if (classMatches) {
      for (const cm of classMatches) {
        const cls = cm.slice(1);
        if (!el.classList.contains(cls)) return false;
      }
    }
    const attrMatches = part.match(/\[([a-zA-Z0-9\-_]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]+)))?\]/g);
    if (attrMatches) {
      for (const am of attrMatches) {
        const amParsed = /\[([a-zA-Z0-9\-_]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]+)))?\]/.exec(am);
        if (amParsed) {
          const attrName = amParsed[1];
          const attrVal = amParsed[2] || amParsed[3] || amParsed[4];
          if (attrName.startsWith('data-')) {
            const dataKey = attrName.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
            if (el.dataset[dataKey] === undefined) return false;
            if (attrVal !== undefined && el.dataset[dataKey] !== attrVal) return false;
          } else {
            if (el[attrName] === undefined) return false;
            if (attrVal !== undefined && String(el[attrName]) !== attrVal) return false;
          }
        }
      }
    }
    return true;
  });
}

class MockElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this._className = '';
    this.classList = new MockClassList(this);
    this.dataset = {};
    this.children = [];
    this._textParts = [];
    this.parentElement = null;
    this.listeners = {};
    this._innerHTML = '';
    this.style = {};
    this.disabled = false;
    this.title = '';
  }

  get className() {
    return this._className;
  }
  set className(val) {
    this._className = val || '';
    this.classList._classes = new Set((val || '').split(/\s+/).filter(Boolean));
  }

  get innerHTML() {
    return this._innerHTML;
  }
  set innerHTML(val) {
    this._innerHTML = val;
    this._parseHTML(val);
  }

  get textContent() {
    return this._getTextContent();
  }
  set textContent(val) {
    this._innerHTML = String(val);
    this.children = [];
    this._textParts = [String(val)];
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  addEventListener(type, cb) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(cb);
  }

  click() {
    const evt = {
      stopPropagation: () => {},
      preventDefault: () => {},
      target: this,
      currentTarget: this
    };
    const handlers = (this.listeners['click'] || []).slice();
    for (const h of handlers) {
      h(evt);
    }
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const results = [];
    const match = (el) => {
      if (matchesSelector(el, selector)) {
        results.push(el);
      }
      for (const ch of el.children) {
        match(ch);
      }
    };
    for (const ch of this.children) {
      match(ch);
    }
    return results;
  }

  _getTextContent() {
    const ownText = this._textParts.join('');
    const childText = this.children.map(c => c.textContent).join('');
    return (ownText + (childText ? ' ' + childText : '')).trim();
  }

  _parseHTML(html) {
    this.children = [];
    this._textParts = [];
    if (!html || typeof html !== 'string') return;

    const tagRegex = /<!--[\s\S]*?-->|<(\/)?([a-zA-Z0-9\-]+)([^>]*)>|([^<]+)/g;
    let match;
    const stack = [{ el: this, tag: 'root' }];

    while ((match = tagRegex.exec(html)) !== null) {
      if (match[0].startsWith('<!--')) continue;

      const isClosing = Boolean(match[1]);
      const tagName = match[2];
      const attrsStr = match[3];
      const text = match[4];

      if (text) {
        const current = stack[stack.length - 1].el;
        if (current) {
          current._textParts.push(text);
        }
        continue;
      }

      if (tagName) {
        const isSelfClosing = attrsStr && attrsStr.trim().endsWith('/');
        const voidTags = ['br', 'hr', 'img', 'input', 'link', 'meta'];
        const isVoid = voidTags.includes(tagName.toLowerCase()) || isSelfClosing;

        if (isClosing) {
          for (let i = stack.length - 1; i > 0; i--) {
            if (stack[i].tag.toLowerCase() === tagName.toLowerCase()) {
              stack.splice(i);
              break;
            }
          }
        } else {
          const newEl = new MockElement(tagName);
          parseAttributes(attrsStr, newEl);
          const currentParent = stack[stack.length - 1].el;
          currentParent.children.push(newEl);
          newEl.parentElement = currentParent;

          if (tagName.toLowerCase() === 'script') {
            const scriptEndIdx = html.indexOf('</script>', tagRegex.lastIndex);
            if (scriptEndIdx !== -1) {
              const scriptContent = html.substring(tagRegex.lastIndex, scriptEndIdx);
              newEl.textContent = scriptContent;
              newEl._innerHTML = scriptContent;
              tagRegex.lastIndex = scriptEndIdx + 9;
            }
          } else if (!isVoid) {
            stack.push({ el: newEl, tag: tagName });
          }
        }
      }
    }
  }
}

class MockDocument {
  createElement(tagName) {
    return new MockElement(tagName);
  }
  querySelectorAll(sel) {
    return [];
  }
}

// Global browser env setup
global.document = new MockDocument();
global.window = {
  document: global.document,
  localStorage: {
    _data: {},
    getItem(k) { return this._data[k] || null; },
    setItem(k, v) { this._data[k] = String(v); },
    removeItem(k) { delete this._data[k]; }
  }
};
global.localStorage = global.window.localStorage;

// ============================================================================
// 2. Import Component under Test
// ============================================================================
const { renderMarkdown, createMessageElement, initInteractiveTables } = await import('../src/components/message_renderer.js');

// ============================================================================
// 3. Test Suite Probe
// ============================================================================

let passCount = 0;
let failCount = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ PASS: ${message}`);
    passCount++;
  } else {
    console.error(`  ✗ FAIL: ${message}`);
    failCount++;
  }
}

console.log('==================================================================');
console.log('  PROBING QUANT PWA INTERACTIVE TABLE & SORTING ENGINE (FLOW-08)');
console.log('==================================================================\n');

// Build sample 30-print dataset
const sampleMarkdown = `
### QUANT OPTIONS FLOW (30 PRINTS)

| EXP | SYMBOL | TYPE | STRIKE | SPOT | %OTM | PREMIUM | SIZE | OI | TAG |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-09-18 | AMD | BUY CALL | $120.00 | $110.00 | +9.1% | $15.50M | 15,000 | 12,000 | [WHALE] |
| 2026-09-18 | SKHY | BUY CALL | $15.00 | $14.20 | +5.6% | $10.90M | 8,500 | 4,200 | [WHALE] |
| 2026-09-18 | COIN | BUY PUT | $240.00 | $250.00 | -4.0% | $9.80M | 4,000 | 2,100 | [WHALE] |
| 2026-09-18 | NVDA | BUY CALL | $130.00 | $125.00 | +4.0% | $8.20M | 6,000 | 5,000 | [WHALE] |
| 2026-09-18 | TSLA | BUY PUT | $210.00 | $220.00 | -4.5% | $7.50M | 5,500 | 3,800 | [WHALE] |
| 2026-09-18 | PLTR | BUY CALL | $35.00 | $32.00 | +9.4% | $6.10M | 12,000 | 8,000 | [WHALE] |
| 2026-09-18 | MSFT | BUY CALL | $450.00 | $440.00 | +2.3% | $4.80M | 2,000 | 1,500 | [LARGE] |
| 2026-09-18 | META | BUY CALL | $520.00 | $505.00 | +3.0% | $4.20M | 1,800 | 1,200 | [LARGE] |
| 2026-09-18 | GOOGL | BUY CALL | $180.00 | $175.00 | +2.9% | $3.90M | 3,200 | 2,400 | [LARGE] |
| 2026-09-18 | AMZN | BUY CALL | $190.00 | $185.00 | +2.7% | $3.50M | 2,800 | 1,900 | [LARGE] |
| 2026-09-18 | INTC | BUY CALL | $25.00 | $22.00 | +13.6% | $2.90M | 14,000 | 9,500 | [LARGE] |
| 2026-09-18 | MU | BUY CALL | $115.00 | $110.00 | +4.5% | $2.60M | 3,000 | 2,100 | [LARGE] |
| 2026-09-18 | AVGO | BUY CALL | $160.00 | $155.00 | +3.2% | $2.30M | 1,500 | 1,100 | [LARGE] |
| 2026-09-18 | QCOM | BUY CALL | $170.00 | $165.00 | +3.0% | $2.10M | 1,700 | 1,300 | [LARGE] |
| 2026-09-18 | ARM | BUY CALL | $140.00 | $132.00 | +6.1% | $1.90M | 2,200 | 1,600 | [LARGE] |
| 2026-09-18 | SMCI | BUY CALL | $45.00 | $40.00 | +12.5% | $1.70M | 4,500 | 3,200 | [LARGE] |
| 2026-09-18 | NFLX | BUY CALL | $680.00 | $665.00 | +2.3% | $1.50M | 800 | 600 | [LARGE] |
| 2026-09-18 | BABA | BUY CALL | $85.00 | $82.00 | +3.7% | $1.30M | 3,500 | 2,700 | [LARGE] |
| 2026-09-18 | UBER | BUY CALL | $75.00 | $72.00 | +4.2% | $1.10M | 2,900 | 2,000 | [LARGE] |
| 2026-09-18 | HOOD | BUY CALL | $22.00 | $20.50 | +7.3% | $1.05M | 6,200 | 4,100 | [LARGE] |
| 2026-09-18 | PYPL | BUY CALL | $65.00 | $63.00 | +3.2% | $950K | 2,100 | 1,500 | - |
| 2026-09-18 | SOFI | BUY CALL | $15.00 | $7.80 | +92.3% | $850K | 12,500 | 8,900 | - |
| 2026-09-18 | RBLX | BUY CALL | $42.00 | $40.00 | +5.0% | $780K | 3,100 | 2,200 | - |
| 2026-09-18 | SNAP | BUY CALL | $12.00 | $10.50 | +14.3% | $720K | 8,400 | 5,600 | - |
| 2026-09-18 | PINS | BUY CALL | $32.00 | $30.00 | +6.7% | $680K | 3,300 | 2,400 | - |
| 2026-09-18 | CRWD | BUY CALL | $280.00 | $270.00 | +3.7% | $640K | 750 | 500 | - |
| 2026-09-18 | PANW | BUY CALL | $340.00 | $330.00 | +3.0% | $590K | 620 | 450 | - |
| 2026-09-18 | ZS | BUY CALL | $190.00 | $182.00 | +4.4% | $550K | 910 | 680 | - |
| 2026-09-18 | SHOP | BUY CALL | $70.00 | $67.50 | +3.7% | $520K | 1,400 | 1,050 | - |
| 2026-09-18 | AAPL | BUY CALL | $230.00 | $225.00 | +2.2% | $500K | 1,200 | 950 | - |
`;

// Render Message Element
const messageBubble = createMessageElement('assistant', sampleMarkdown);
const wrapper = messageBubble.querySelector('.quant-table-wrapper');
const tbody = messageBubble.querySelector('tbody');
const thEls = messageBubble.querySelectorAll('th.sortable, th[data-col]');
const prevBtn = messageBubble.querySelector('.btn-prev');
const nextBtn = messageBubble.querySelector('.btn-next');
const pageInfo = messageBubble.querySelector('.bb-page-info');

// Helpers to read rendered table state
function getVisibleRows() {
  return tbody.querySelectorAll('tr');
}

function getFirstRowCell(colIndex = 1) {
  const rows = getVisibleRows();
  if (rows.length === 0) return '';
  const cells = rows[0].querySelectorAll('td');
  return cells[colIndex] ? cells[colIndex].textContent.trim() : '';
}

function getLastRowCell(colIndex = 1) {
  const rows = getVisibleRows();
  if (rows.length === 0) return '';
  const cells = rows[rows.length - 1].querySelectorAll('td');
  return cells[colIndex] ? cells[colIndex].textContent.trim() : '';
}

function getHeader(colName) {
  for (const th of thEls) {
    if (th.textContent.toUpperCase().includes(colName.toUpperCase())) {
      return th;
    }
  }
  return null;
}

// ----------------------------------------------------------------------------
// TEST 1: Initial State (Premium Descending, Page 1 of 2)
// ----------------------------------------------------------------------------
console.log('--- TEST 1: Initial State ---');
const initialRows = getVisibleRows();
assert(initialRows.length === 20, `Initial render displays 20 rows (got ${initialRows.length})`);
assert(pageInfo.textContent.includes('PAGE 1 OF 2'), `Pagination text indicates Page 1 of 2: "${pageInfo.textContent}"`);
assert(prevBtn.disabled === true, 'PREV button is disabled on page 1');
assert(nextBtn.disabled === false, 'NEXT button is enabled on page 1');

const premHeader = getHeader('PREMIUM') || getHeader('PREM');
assert(premHeader !== null, 'Premium header is present');
assert(premHeader.classList.contains('sort-desc'), 'Premium header has active .sort-desc class');
assert(getFirstRowCell(1) === 'AMD', `Top row is highest premium print (AMD $15.50M): got ${getFirstRowCell(1)}`);
assert(getLastRowCell(1) === 'HOOD', `20th row on page 1 is HOOD ($1.05M): got ${getLastRowCell(1)}`);

// ----------------------------------------------------------------------------
// TEST 2: Click 1 on SYMBOL Header (Sort Descending: Z to A)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 2: Tri-State Click 1 on SYMBOL (Descending) ---');
const symHeader = getHeader('SYMBOL');
assert(symHeader !== null, 'SYMBOL header found');

symHeader.click();

assert(symHeader.classList.contains('sort-desc'), 'SYMBOL header has .sort-desc class');
assert(!premHeader.classList.contains('sort-desc') && !premHeader.classList.contains('sort-asc'), 'Previous sort column cleared classes');
assert(getFirstRowCell(1) === 'ZS', `Top row is ZS (alphabetically highest): got ${getFirstRowCell(1)}`);
assert(pageInfo.textContent.includes('PAGE 1 OF 2'), 'Current page is reset to Page 1 on sort change');

// ----------------------------------------------------------------------------
// TEST 3: Click 2 on SYMBOL Header (Sort Ascending: A to Z)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 3: Tri-State Click 2 on SYMBOL (Ascending) ---');
symHeader.click();

assert(symHeader.classList.contains('sort-asc'), 'SYMBOL header has .sort-asc class');
assert(getFirstRowCell(1) === 'AAPL', `Top row is AAPL (alphabetically first): got ${getFirstRowCell(1)}`);

// ----------------------------------------------------------------------------
// TEST 4: Click 3 on SYMBOL Header (Reset to Default Natural Order)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 4: Tri-State Click 3 on SYMBOL (Reset Natural Order) ---');
symHeader.click();

assert(!symHeader.classList.contains('sort-asc') && !symHeader.classList.contains('sort-desc'), 'SYMBOL header sort classes cleared');
assert(getFirstRowCell(1) === 'AMD', `Top row reset to natural order print 1 (AMD): got ${getFirstRowCell(1)}`);
assert(getLastRowCell(1) === 'HOOD', `20th row reset to natural order print 20 (HOOD): got ${getLastRowCell(1)}`);

// ----------------------------------------------------------------------------
// TEST 5: Secondary Tie-Breaker (Identical Strike, Higher Premium First)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 5: Secondary Tie-Breaker on STRIKE Column ---');
const strikeHeader = getHeader('STRIKE');
assert(strikeHeader !== null, 'STRIKE header found');

// Click STRIKE to sort descending, then click again for ascending
strikeHeader.click(); // Click 1: Descending
strikeHeader.click(); // Click 2: Ascending ($12.00, $15.00, ...)

// Both SKHY and SOFI have Strike $15.00.
// SKHY has $10.90M premium, SOFI has $850K premium.
// SKHY must precede SOFI due to secondary tie-breaker.
const sortedRows = Array.from(tbody.querySelectorAll('tr'));
let skhyIndex = -1;
let sofiIndex = -1;

sortedRows.forEach((row, idx) => {
  const cells = row.querySelectorAll('td');
  const sym = cells[1] ? cells[1].textContent.trim() : '';
  if (sym === 'SKHY') skhyIndex = idx;
  if (sym === 'SOFI') sofiIndex = idx;
});

assert(skhyIndex !== -1, 'SKHY is present in the sorted view');
assert(sofiIndex !== -1, 'SOFI is present in the sorted view');
assert(skhyIndex < sofiIndex, `Secondary tie-breaker verified: SKHY ($10.90M) at index ${skhyIndex} precedes SOFI ($850K) at index ${sofiIndex} for identical $15.00 strike`);

// ----------------------------------------------------------------------------
// TEST 6: Pagination Controls (NEXT ► / PREV ◄ / Auto Reset)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 6: Pagination Controls ---');

// Reset to natural order by clicking strike header once more
strikeHeader.click(); // Click 3: Reset
assert(getFirstRowCell(1) === 'AMD', 'Reset to natural order');

// Click NEXT ►
nextBtn.click();
assert(pageInfo.textContent.includes('PAGE 2 OF 2'), `Page info updated to Page 2 of 2: "${pageInfo.textContent}"`);
const p2Rows = getVisibleRows();
assert(p2Rows.length === 10, `Page 2 shows remaining 10 rows (got ${p2Rows.length})`);
assert(getFirstRowCell(1) === 'PYPL', `Row 21 is PYPL: got ${getFirstRowCell(1)}`);
assert(getLastRowCell(1) === 'AAPL', `Row 30 is AAPL: got ${getLastRowCell(1)}`);
assert(nextBtn.disabled === true, 'NEXT button is disabled on last page');
assert(prevBtn.disabled === false, 'PREV button is enabled on page 2');

// Click sort column while on page 2 -> must reset to page 1
symHeader.click(); // Sort SYMBOL desc
assert(pageInfo.textContent.includes('PAGE 1 OF 2'), 'Changing sort column resets currentPage back to 1');
assert(getFirstRowCell(1) === 'ZS', `Page 1 displays top sorted row (ZS): got ${getFirstRowCell(1)}`);

// ============================================================================
// Summary & Exit
// ============================================================================
console.log('\n==================================================================');
console.log(`  TEST RESULTS: ${passCount} PASSED, ${failCount} FAILED`);
console.log('==================================================================');

if (failCount > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
