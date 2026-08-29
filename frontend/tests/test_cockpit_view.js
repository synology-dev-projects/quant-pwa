/**
 * Automated In-Situ Test Probe for Quant Cockpit 3-Panel Dashboard & Search View (COCKPIT-01)
 *
 * Tests:
 * 1. Search Execution & Recents Persistence
 * 2. 3-Panel DOM Mounting:
 *    - Panel 1: Synergized Synthesis (Hero Card) with Metric Pills & Stream Area
 *    - Panel 2: Interactive Exposure Chart with GEX/DEX toggle & Key Levels Strip
 *    - Panel 3: 30-Day Options Flow Table with Filter Chips & Bloomberg Table
 * 3. Filter Chip Clicks ([All], [Whales >$1M], [Calls], [Puts], [Unusual OI ⚠️])
 * 4. GEX/DEX Toggle Switch Interactivity
 * 5. Bloomberg Table Tri-State Column Sorting & Pagination
 * 6. Quick Suggestion Chip Clicks
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
  toggle(cls, force) {
    if (force !== undefined) {
      if (force) this._classes.add(cls);
      else this._classes.delete(cls);
    } else {
      if (this._classes.has(cls)) {
        this._classes.delete(cls);
      } else {
        this._classes.add(cls);
      }
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
    } else if (name === 'style') {
      if (typeof val === 'string') {
        const declarations = val.split(';').filter(Boolean);
        for (const d of declarations) {
          const colonIdx = d.indexOf(':');
          if (colonIdx !== -1) {
            const prop = d.slice(0, colonIdx).trim().replace(/-([a-z])/g, (_, g) => g.toUpperCase());
            const propVal = d.slice(colonIdx + 1).trim();
            if (prop) el.style[prop] = propVal;
          }
        }
      }
    } else if (name.startsWith('data-')) {
      const camelKey = name.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
      el.dataset[camelKey] = val;
    } else if (name === 'disabled') {
      el.disabled = true;
    } else if (name === 'type') {
      el.type = val;
    } else if (name === 'id') {
      el.id = val;
    } else if (name === 'value') {
      el.value = val;
    } else {
      el[name] = val;
    }
  }
}

function matchesSingle(el, part) {
  if (!el || !part) return false;

  // Match ID
  const idMatches = part.match(/#([a-zA-Z0-9\-_]+)/g);
  if (idMatches) {
    for (const im of idMatches) {
      if (el.id !== im.slice(1)) return false;
    }
  }

  // Match Tag
  const tagMatch = part.match(/^([a-zA-Z0-9\-]+)/);
  if (tagMatch) {
    if (el.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
  }

  // Match Classes
  const classMatches = part.match(/\.([a-zA-Z0-9\-_]+)/g);
  if (classMatches) {
    for (const cm of classMatches) {
      if (!el.classList.contains(cm.slice(1))) return false;
    }
  }

  // Match Attributes
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
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  const groups = selector.split(',').map(s => s.trim()).filter(Boolean);
  return groups.some(group => {
    const parts = group.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return false;
    if (parts.length === 1) return matchesSingle(el, parts[0]);

    // Multiple descendant parts (e.g. "#gexDexToggle .toggle-btn")
    if (!matchesSingle(el, parts[parts.length - 1])) return false;
    let cur = el.parentElement;
    for (let i = parts.length - 2; i >= 0; i--) {
      let found = false;
      while (cur) {
        if (matchesSingle(cur, parts[i])) {
          found = true;
          cur = cur.parentElement;
          break;
        }
        cur = cur.parentElement;
      }
      if (!found) return false;
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
    this.id = '';
    this.value = '';
    this.width = 380;
    this.height = 450;
    this.clientWidth = 380;
    this.clientHeight = 450;
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

  insertBefore(newChild, refChild) {
    newChild.parentElement = this;
    const idx = this.children.indexOf(refChild);
    if (idx === -1) {
      this.children.push(newChild);
    } else {
      this.children.splice(idx, 0, newChild);
    }
    return newChild;
  }

  remove() {
    if (this.parentElement) {
      const idx = this.parentElement.children.indexOf(this);
      if (idx !== -1) {
        this.parentElement.children.splice(idx, 1);
      }
      this.parentElement = null;
    }
  }

  addEventListener(type, cb) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(cb);
  }

  dispatchEvent(evt) {
    let stopped = false;
    const eventObj = evt || {
      type: 'custom',
      stopPropagation: () => { stopped = true; },
      preventDefault: () => {},
      target: this,
      currentTarget: this
    };
    eventObj.stopPropagation = () => { stopped = true; };
    if (!eventObj.target) eventObj.target = this;
    if (!eventObj.currentTarget) eventObj.currentTarget = this;
    if (!eventObj.preventDefault) eventObj.preventDefault = () => {};

    // 1. Direct listeners on element
    const handlers = (this.listeners[eventObj.type || 'click'] || []).slice();
    for (const h of handlers) {
      h(eventObj);
      if (stopped) return;
    }

    // 2. Bubble up parent chain
    let cur = this.parentElement;
    while (cur && !stopped) {
      const parentHandlers = (cur.listeners[eventObj.type || 'click'] || []).slice();
      for (const ph of parentHandlers) {
        ph(eventObj);
        if (stopped) return;
      }
      cur = cur.parentElement;
    }
  }

  click() {
    const evt = {
      type: 'click',
      stopPropagation: () => {},
      preventDefault: () => {},
      target: this,
      currentTarget: this
    };
    this.dispatchEvent(evt);
  }

  submit() {
    const evt = {
      type: 'submit',
      stopPropagation: () => {},
      preventDefault: () => {},
      target: this,
      currentTarget: this
    };
    this.dispatchEvent(evt);
  }

  focus() {}

  contains(child) {
    if (!child) return false;
    let cur = child;
    while (cur) {
      if (cur === this) return true;
      cur = cur.parentElement;
    }
    return false;
  }

  closest(selector) {
    let cur = this;
    while (cur) {
      if (matchesSelector(cur, selector)) return cur;
      cur = cur.parentElement;
    }
    return null;
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

  getBoundingClientRect() {
    return { left: 0, top: 0, width: 380, height: 450, right: 380, bottom: 450 };
  }

  getContext(type) {
    return {
      resetTransform: () => {},
      scale: () => {},
      fillRect: () => {},
      strokeRect: () => {},
      fillText: () => {},
      stroke: () => {},
      beginPath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      save: () => {},
      restore: () => {},
      setLineDash: () => {},
      font: '',
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      textAlign: 'center'
    };
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
  constructor() {
    this.body = new MockElement('BODY');
  }
  createElement(tagName) {
    return new MockElement(tagName);
  }
  getElementById(id) {
    return this.body.querySelector(`#${id}`);
  }
  querySelector(sel) {
    return this.body.querySelector(sel);
  }
  querySelectorAll(sel) {
    return this.body.querySelectorAll(sel);
  }
  addEventListener(type, cb) {}
}

// Global browser env setup
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

global.document = new MockDocument();
global.window = {
  document: global.document,
  devicePixelRatio: 2,
  requestAnimationFrame: (cb) => { setImmediate(cb); },
  addEventListener: () => {},
  removeEventListener: () => {},
  location: {
    hostname: 'localhost',
    port: '8000'
  },
  localStorage: {
    _data: {},
    getItem(k) { return this._data[k] || null; },
    setItem(k, v) { this._data[k] = String(v); },
    removeItem(k) { delete this._data[k]; },
    clear() { this._data = {}; }
  }
};
global.localStorage = global.window.localStorage;
global.requestAnimationFrame = global.window.requestAnimationFrame;

// ============================================================================
// 2. Import Component under Test
// ============================================================================
const { CockpitView } = await import('../src/tabs/cockpit_view.js');

// ============================================================================
// 3. Test Suite Runner
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
console.log('  PROBING QUANT COCKPIT 3-PANEL DASHBOARD VIEW (COCKPIT-01)');
console.log('==================================================================\n');

// ----------------------------------------------------------------------------
// TEST 1: Initial Render & DOM Structure Mounting
// ----------------------------------------------------------------------------
console.log('--- TEST 1: Initial Render & Structure ---');
const rootContainer = new MockElement('DIV');
rootContainer.id = 'tab-cockpit';
document.body.appendChild(rootContainer);

const cockpitView = new CockpitView();
cockpitView.render(rootContainer);

// Check Search sticky bar
const searchInput = rootContainer.querySelector('#cockpitSearchInput');
const searchForm = rootContainer.querySelector('#cockpitSearchForm');
const searchBtn = rootContainer.querySelector('#cockpitSearchBtn');
const suggestedChips = rootContainer.querySelector('#cockpitSuggestedChips');
const recentGroup = rootContainer.querySelector('#cockpitRecentGroup');

assert(searchInput !== null, 'Search input field is rendered');
assert(searchInput.placeholder.includes('Search Ticker'), `Search input placeholder is correct: "${searchInput.placeholder}"`);
assert(searchForm !== null, 'Search form is rendered');
assert(searchBtn !== null, 'Search button is rendered');
assert(suggestedChips !== null, 'Suggested chips container is rendered');

const suggestionButtons = suggestedChips.querySelectorAll('.suggestion-chip');
assert(suggestionButtons.length === 6, `6 quick suggestion chips mounted (got ${suggestionButtons.length})`);
const chipSymbols = suggestionButtons.map(b => b.dataset.ticker);
assert(chipSymbols.includes('NVDA') && chipSymbols.includes('SPY') && chipSymbols.includes('TSLA'), 'Suggestions include NVDA, SPY, TSLA');

// Check 3 Panels
const panelHero = rootContainer.querySelector('#cockpitPanelHero');
const panelChart = rootContainer.querySelector('#cockpitPanelChart');
const panelFlow = rootContainer.querySelector('#cockpitPanelFlow');

assert(panelHero !== null, 'Panel 1: Synergized Synthesis (Hero Card) is mounted');
assert(panelChart !== null, 'Panel 2: Interactive Exposure Chart is mounted');
assert(panelFlow !== null, 'Panel 3: 30-Day Options Flow Table is mounted');

// ----------------------------------------------------------------------------
// TEST 2: Ticker Search Execution (NVDA)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 2: Search Execution (NVDA) ---');
searchInput.value = 'NVDA';
await cockpitView.searchTicker('NVDA');

// Verify Panel 1 Hero Updates
const heroBadge = rootContainer.querySelector('#heroTickerBadge');
assert(heroBadge.textContent === 'NVDA', `Hero badge displays searched ticker NVDA (got ${heroBadge.textContent})`);

const pillConfluence = rootContainer.querySelector('#pillConfluence');
const pillRegime = rootContainer.querySelector('#pillRegime');
const pillFlow = rootContainer.querySelector('#pillFlowRatio');
const pillWall = rootContainer.querySelector('#pillWallRange');

assert(pillConfluence !== null && pillConfluence.textContent.includes('CONFLUENCE'), 'Confluence Bias pill rendered');
assert(pillConfluence.classList.contains('bullish') || pillConfluence.classList.contains('neutral') || pillConfluence.classList.contains('bearish'), 'Confluence Bias pill has sentiment modifier class');
assert(pillRegime !== null && pillRegime.textContent.includes('GAMMA'), 'Gamma regime pill rendered');
assert(pillFlow !== null && pillFlow.textContent.includes('FLOW'), '30D Flow Ratio pill rendered');
assert(pillWall !== null && pillWall.textContent.includes('WALL'), 'Wall Range pill rendered');

const synthMarkdown = rootContainer.querySelector('#synthesisMarkdown');
assert(synthMarkdown !== null && synthMarkdown.innerHTML.includes('Institutional Quant Thesis'), 'Synergized synthesis markdown is rendered');

// ----------------------------------------------------------------------------
// TEST 3: Panel 2 Key Levels Strip & Canvas Mount
// ----------------------------------------------------------------------------
console.log('\n--- TEST 3: Panel 2 Key Levels Strip & Chart ---');
const klSpot = rootContainer.querySelector('#klSpot');
const klFlip = rootContainer.querySelector('#klFlip');
const klCall = rootContainer.querySelector('#klCallWall');
const klPut = rootContainer.querySelector('#klPutWall');

assert(klSpot.textContent.startsWith('$'), `Spot price rendered in key levels strip: ${klSpot.textContent}`);
assert(klFlip.textContent.startsWith('$'), `Zero flip rendered in key levels strip: ${klFlip.textContent}`);
assert(klCall.textContent.startsWith('$'), `Call wall rendered in key levels strip: ${klCall.textContent}`);
assert(klPut.textContent.startsWith('$'), `Put wall rendered in key levels strip: ${klPut.textContent}`);

const canvas = rootContainer.querySelector('canvas.quant-canvas');
assert(canvas !== null, 'HTML5 Canvas element is mounted inside QuantChart card');

// ----------------------------------------------------------------------------
// TEST 4: Net GEX | Net DEX Toggle Switch
// ----------------------------------------------------------------------------
console.log('\n--- TEST 4: Net GEX | Net DEX Toggle ---');
const toggleGex = rootContainer.querySelector('#gexDexToggle .toggle-btn[data-mode="gex"]');
const toggleDex = rootContainer.querySelector('#gexDexToggle .toggle-btn[data-mode="dex"]');

assert(toggleGex !== null && toggleDex !== null, 'GEX and DEX toggle buttons found');
assert(toggleGex.classList.contains('active'), 'Net GEX button active by default');

// Click Net DEX
toggleDex.click();
assert(toggleDex.classList.contains('active'), 'Net DEX button is active after click');
assert(!toggleGex.classList.contains('active'), 'Net GEX button is no longer active');
assert(cockpitView.chartMode === 'dex', 'CockpitView chartMode updated to dex');

// Click Net GEX back
toggleGex.click();
assert(toggleGex.classList.contains('active'), 'Net GEX button is active after toggle back');
assert(cockpitView.chartMode === 'gex', 'CockpitView chartMode updated back to gex');

// ----------------------------------------------------------------------------
// TEST 5: Panel 3 Options Flow Table & Bloomberg Interactivity
// ----------------------------------------------------------------------------
console.log('\n--- TEST 5: Panel 3 Options Flow & Filter Chips ---');
const flowTableWrapper = rootContainer.querySelector('.quant-table-wrapper');
assert(flowTableWrapper !== null, 'Quant interactive table wrapper mounted in flow panel');

const flowCountBadge = rootContainer.querySelector('#flowCountBadge');
assert(flowCountBadge !== null && flowCountBadge.textContent.includes('PRINTS'), `Flow count badge displays prints count: ${flowCountBadge.textContent}`);

// Filter Chip: Whales >$1M
const chipWhales = rootContainer.querySelector('#flowFilterChips .flow-chip[data-filter="whales"]');
assert(chipWhales !== null, 'Whales >$1M filter chip found');

chipWhales.click();
assert(chipWhales.classList.contains('active'), 'Whales filter chip is active');
assert(cockpitView.activeFilter === 'whales', 'Active filter state is "whales"');

const whaleRows = rootContainer.querySelectorAll('#cockpitFlowTableContainer tbody tr');
assert(whaleRows.length > 0, `Whales filter shows matching whale rows (got ${whaleRows.length})`);

// Filter Chip: Calls
const chipCalls = rootContainer.querySelector('#flowFilterChips .flow-chip[data-filter="calls"]');
chipCalls.click();
assert(cockpitView.activeFilter === 'calls', 'Active filter state is "calls"');
const callRows = rootContainer.querySelectorAll('#cockpitFlowTableContainer tbody tr');
assert(callRows.length > 0, `Calls filter shows matching call rows (got ${callRows.length})`);

// Filter Chip: Puts
const chipPuts = rootContainer.querySelector('#flowFilterChips .flow-chip[data-filter="puts"]');
chipPuts.click();
assert(cockpitView.activeFilter === 'puts', 'Active filter state is "puts"');

// Filter Chip: Unusual OI ⚠️
const chipUnusual = rootContainer.querySelector('#flowFilterChips .flow-chip[data-filter="unusual"]');
chipUnusual.click();
assert(cockpitView.activeFilter === 'unusual', 'Active filter state is "unusual"');

// Reset to All
const chipAll = rootContainer.querySelector('#flowFilterChips .flow-chip[data-filter="all"]');
chipAll.click();
assert(cockpitView.activeFilter === 'all', 'Active filter state reset to "all"');

// ----------------------------------------------------------------------------
// TEST 6: Table Tri-State Sorting & Pagination
// ----------------------------------------------------------------------------
console.log('\n--- TEST 6: Table Tri-State Sorting ---');
const thPremium = Array.from(rootContainer.querySelectorAll('th.sortable')).find(th => /PREMIUM|PREM/i.test(th.textContent));
assert(thPremium !== undefined, 'Premium table header found');

// Click Strike header for sorting
const thStrike = Array.from(rootContainer.querySelectorAll('th.sortable')).find(th => /STRIKE/i.test(th.textContent));
assert(thStrike !== undefined, 'Strike table header found');

thStrike.click(); // Click 1: Descending
assert(thStrike.classList.contains('sort-desc'), 'Strike header has sort-desc class after click 1');

thStrike.click(); // Click 2: Ascending
assert(thStrike.classList.contains('sort-asc'), 'Strike header has sort-asc class after click 2');

thStrike.click(); // Click 3: Reset
assert(!thStrike.classList.contains('sort-asc') && !thStrike.classList.contains('sort-desc'), 'Strike header classes reset after click 3');

// ----------------------------------------------------------------------------
// TEST 7: Recent Searches Persistence & Quick Suggestion Clicking
// ----------------------------------------------------------------------------
console.log('\n--- TEST 7: Recent Searches & Suggestion Chips ---');
const savedRecents = cockpitView.getRecentSearches();
assert(savedRecents.includes('NVDA'), `Searched NVDA stored in localStorage (${JSON.stringify(savedRecents)})`);

// Click quick suggestion chip (TSLA)
const tslaChip = Array.from(rootContainer.querySelectorAll('.suggestion-chip')).find(c => c.dataset.ticker === 'TSLA');
assert(tslaChip !== undefined, 'TSLA suggestion chip found');

tslaChip.click();
// Give promise time to settle
await new Promise(r => setImmediate(r));

assert(heroBadge.textContent === 'TSLA', `Clicking TSLA suggestion chip loaded TSLA (got ${heroBadge.textContent})`);
const updatedRecents = cockpitView.getRecentSearches();
assert(updatedRecents[0] === 'TSLA' && updatedRecents[1] === 'NVDA', `Recents updated with TSLA as most recent: ${JSON.stringify(updatedRecents)}`);

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
