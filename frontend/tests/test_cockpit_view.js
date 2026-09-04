/**
 * Automated In-Situ Test Probe for Quant Cockpit 3-Panel Dashboard & Search View (COCKPIT-01 & BUG-COCKPIT-01)
 *
 * Tests:
 * 1. Search Execution & Recents Persistence
 * 2. 3-Panel DOM Mounting:
 *    - Panel 1: Synergized Synthesis (Hero Card) with Metric Pills & Stream Area
 *    - Panel 2: Interactive Exposure Chart with GEX/DEX toggle & Key Levels Strip
 *    - Panel 3: 30-Day Options Flow Table with Filter Chips & Bloomberg Table
 * 3. Distinct Real Strike Structures & Spot Prices (SPY vs NVDA)
 * 4. Honest Empty State on Empty Strikes (Purged Fake Gaussian Clones)
 * 5. Filter Chip Clicks ([All], [Whales >$1M], [Calls], [Puts], [Unusual OI ⚠️])
 * 6. GEX/DEX Toggle Switch Interactivity
 * 7. Bloomberg Table Tri-State Column Sorting & Pagination
 * 8. Quick Suggestion Chip Clicks
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

  removeEventListener(type, cb) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter(h => h !== cb);
    }
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
      clearRect: () => {},
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
    port: '8000',
    origin: 'http://localhost:8000'
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
// 2. Mock Server Data Feeds for Distinct Real Tickers & Empty Chains
// ============================================================================

const MOCK_FEEDS = {
  NVDA: {
    ticker: 'NVDA',
    status: 'ok',
    gex: {
      ticker: 'NVDA',
      spot_price: 217.50,
      zero_gex_level: 214.00,
      call_wall: 230.00,
      put_wall: 200.00,
      call_put_ratio: 1.62,
      gamma_regime: 'LONG GAMMA (+GEX)',
      expirations: ['2026-09-18', '2026-10-16'],
      strikes: [
        { strike: 200, call_gex: 4000000, put_gex: 52000000, call_dex: 3000000, put_dex: 41000000 },
        { strike: 210, call_gex: 15000000, put_gex: 28000000, call_dex: 11000000, put_dex: 22000000 },
        { strike: 217.5, call_gex: 35000000, put_gex: 18000000, call_dex: 26000000, put_dex: 14000000 },
        { strike: 230, call_gex: 88000000, put_gex: 3000000, call_dex: 66000000, put_dex: 2400000 }
      ]
    },
    flow: {
      records: [
        { expiration: '2026-09-18', symbol: 'NVDA', order_type: 'BUY CALL', strike: 230, spot: 217.5, otm_pct: 5.7, premium: 12500000, size: 10000, open_interest: 15000, is_unusual_oi: true, tag: '[WHALE]' },
        { expiration: '2026-09-18', symbol: 'NVDA', order_type: 'BUY PUT', strike: 200, spot: 217.5, otm_pct: -8.0, premium: 3500000, size: 4000, open_interest: 6000, is_unusual_oi: false, tag: '[LARGE]' }
      ],
      total_count: 2
    },
    metrics: {
      spot_price: 217.50,
      zero_gamma_flip: 214.00,
      call_wall: 230.00,
      put_wall: 200.00,
      confluence_bias: 'BULLISH CONFLUENCE',
      gamma_regime: 'LONG GAMMA (+GEX)',
      flow_ratio: '78% CALL FLOW',
      call_pct: 78.0,
      put_pct: 22.0,
      call_flow: 12500000,
      put_flow: 3500000,
      whale_count: 1,
      unusual_oi_count: 1
    }
  },

  SPY: {
    ticker: 'SPY',
    status: 'ok',
    gex: {
      ticker: 'SPY',
      spot_price: 769.25,
      zero_gex_level: 762.00,
      call_wall: 785.00,
      put_wall: 750.00,
      call_put_ratio: 1.15,
      gamma_regime: 'LONG GAMMA (+GEX)',
      expirations: ['2026-08-31', '2026-09-18'],
      strikes: [
        { strike: 750, call_gex: 12000000, put_gex: 95000000, call_dex: 9000000, put_dex: 76000000 },
        { strike: 760, call_gex: 35000000, put_gex: 45000000, call_dex: 26000000, put_dex: 36000000 },
        { strike: 770, call_gex: 58000000, put_gex: 22000000, call_dex: 43000000, put_dex: 17000000 },
        { strike: 785, call_gex: 110000000, put_gex: 6000000, call_dex: 82000000, put_dex: 4800000 }
      ]
    },
    flow: {
      records: [
        { expiration: '2026-09-18', symbol: 'SPY', order_type: 'BUY CALL', strike: 785, spot: 769.25, otm_pct: 2.0, premium: 25000000, size: 20000, open_interest: 45000, is_unusual_oi: true, tag: '[WHALE]' }
      ],
      total_count: 1
    },
    metrics: {
      spot_price: 769.25,
      zero_gamma_flip: 762.00,
      call_wall: 785.00,
      put_wall: 750.00,
      confluence_bias: 'BULLISH CONFLUENCE',
      gamma_regime: 'LONG GAMMA (+GEX)',
      flow_ratio: '65% CALL FLOW',
      call_pct: 65.0,
      put_pct: 35.0,
      call_flow: 25000000,
      put_flow: 13000000,
      whale_count: 1,
      unusual_oi_count: 1
    }
  },

  POWL: {
    ticker: 'POWL',
    status: 'ok',
    gex: {
      ticker: 'POWL',
      spot_price: 179.73,
      zero_gex_level: 172.80,
      call_wall: 190.00,
      put_wall: 180.00,
      call_put_ratio: 2.10,
      gamma_regime: 'Positive (Long Gamma / Volatility Dampening)',
      expirations: ['2026-09-18', '2026-10-16'],
      strikes: [
        { strike: 160, call_gex: 1500000, put_gex: 8500000, call_dex: 1200000, put_dex: 6800000 },
        { strike: 170, call_gex: 4500000, put_gex: 9500000, call_dex: 3600000, put_dex: 7600000 },
        { strike: 180, call_gex: 18500000, put_gex: 12500000, call_dex: 14800000, put_dex: 10000000 },
        { strike: 190, call_gex: 22000000, put_gex: 2100000, call_dex: 17600000, put_dex: 1680000 }
      ]
    },
    flow: {
      records: [
        { expiration: '2026-09-18', symbol: 'POWL', order_type: 'BUY CALL', strike: 180, spot: 179.73, otm_pct: 0.15, premium: 12500000, size: 8000, open_interest: 15000, is_unusual_oi: true, tag: '[WHALE]' }
      ],
      total_count: 1
    },
    metrics: {
      spot_price: 179.73,
      zero_gamma_flip: 172.80,
      call_wall: 190.00,
      put_wall: 180.00,
      confluence_bias: 'BULLISH CONFLUENCE',
      gamma_regime: 'Positive (Long Gamma / Volatility Dampening)',
      flow_ratio: '100% CALL FLOW',
      call_pct: 100.0,
      put_pct: 0.0,
      call_flow: 25300000,
      put_flow: 0,
      whale_count: 3,
      unusual_oi_count: 0
    }
  },

  EMPTY_TICKER: {
    ticker: 'XYZ',
    status: 'ok',
    gex: {
      ticker: 'XYZ',
      spot_price: 50.00,
      zero_gex_level: 50.00,
      call_wall: 0,
      put_wall: 0,
      call_put_ratio: 1.0,
      gamma_regime: 'NEUTRAL',
      expirations: [],
      strikes: [] // 0 real strikes
    },
    flow: {
      records: [],
      total_count: 0
    },
    metrics: {
      spot_price: 50.00,
      zero_gamma_flip: 50.00,
      call_wall: 0,
      put_wall: 0,
      confluence_bias: 'NEUTRAL PIN',
      gamma_regime: 'NEUTRAL',
      flow_ratio: '0% FLOW',
      call_pct: 50.0,
      put_pct: 50.0,
      call_flow: 0,
      put_flow: 0,
      whale_count: 0,
      unusual_oi_count: 0
    }
  }
};

global.fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : {};
  const sym = (body.ticker || 'NVDA').toUpperCase();
  const resData = MOCK_FEEDS[sym] || MOCK_FEEDS.EMPTY_TICKER;

  if (url.includes('/synthesis/stream')) {
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => {
          let sent = false;
          return {
            read: async () => {
              if (!sent) {
                sent = true;
                const chunk = `data: {"type": "token", "content": "### Microstructure Snapshot\\n• **Regime & Volatility**: Positive Gamma dampened.\\n• **Key Structural Walls**: Call Wall $230.00, Put Wall $200.00.\\n• **Institutional Flow**: 92% Calls with 1 whale sweep."}\n\n`;
                return { value: new TextEncoder().encode(chunk), done: false };
              }
              return { value: undefined, done: true };
            }
          };
        }
      }
    };
  }

  return {
    ok: true,
    status: 200,
    json: async () => JSON.parse(JSON.stringify(resData))
  };
};

// ============================================================================
// 3. Import Component under Test
// ============================================================================
const { CockpitView } = await import('../src/tabs/cockpit_view.js');

// ============================================================================
// 4. Test Suite Runner
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
// TEST 2: Ticker Search Execution (NVDA) & Real Strikes Structure
// ----------------------------------------------------------------------------
console.log('\n--- TEST 2: Search Execution & Real Strike Structures (NVDA) ---');
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
assert(synthMarkdown !== null && synthMarkdown.innerHTML.includes('Microstructure Snapshot'), 'Synergized synthesis snapshot markdown is rendered');
assert(!synthMarkdown.innerHTML.includes('Tactical Playbook'), 'Zero trade advice enforced in synthesis output');

// Verify NVDA Key Levels & Canvas
const klSpot = rootContainer.querySelector('#klSpot');
const klFlip = rootContainer.querySelector('#klFlip');
const klCall = rootContainer.querySelector('#klCallWall');
const klPut = rootContainer.querySelector('#klPutWall');

assert(klSpot.textContent === '$217.50', `NVDA Spot price correctly rendered: ${klSpot.textContent}`);
assert(klFlip.textContent === '$214.00', `NVDA Zero flip correctly rendered: ${klFlip.textContent}`);
assert(klCall.textContent === '$230.00', `NVDA Call wall correctly rendered: ${klCall.textContent}`);
assert(klPut.textContent === '$200.00', `NVDA Put wall correctly rendered: ${klPut.textContent}`);

const canvas = rootContainer.querySelector('canvas.quant-canvas');
assert(canvas !== null, 'HTML5 Canvas element is mounted inside QuantChart card for real NVDA strikes');
assert(cockpitView.quantChartInstance.data.strikes.length === 4, `NVDA has 4 authentic asymmetrical strikes (got ${cockpitView.quantChartInstance.data.strikes.length})`);
assert(cockpitView.quantChartInstance.data.strikes[0].strike === 200, 'NVDA base strike is $200');

// ----------------------------------------------------------------------------
// TEST 3: Distinct Real Strikes & Spot Prices: SPY vs NVDA
// ----------------------------------------------------------------------------
console.log('\n--- TEST 3: Distinct Real Strike Structures (SPY vs NVDA) ---');
await cockpitView.searchTicker('SPY');

assert(heroBadge.textContent === 'SPY', `Hero badge updated to SPY (got ${heroBadge.textContent})`);
assert(klSpot.textContent === '$769.25', `SPY Spot price ($769.25) distinct from NVDA ($217.50)`);
assert(klCall.textContent === '$785.00', `SPY Call Wall ($785.00) distinct from NVDA ($230.00)`);
assert(klPut.textContent === '$750.00', `SPY Put Wall ($750.00) distinct from NVDA ($200.00)`);

assert(cockpitView.quantChartInstance.data.strikes[0].strike === 750, 'SPY strike structure starts at $750 (distinct from NVDA $200)');
assert(cockpitView.quantChartInstance.data.strikes[3].strike === 785, 'SPY strike structure ends at $785 (distinct from NVDA $230)');
assert(cockpitView.quantChartInstance.data.spot_price === 769.25, 'SPY QuantChart instance receives authentic $769.25 spot price');

// ----------------------------------------------------------------------------
// TEST 4: Honest Empty State on Empty Strikes (BUG-COCKPIT-01)
// ----------------------------------------------------------------------------
console.log('\n--- TEST 4: Honest Empty State on Empty Strikes (No Fake Gaussian Clones) ---');
await cockpitView.searchTicker('XYZ'); // XYZ returns strikes: []

const chartSlot = rootContainer.querySelector('#cockpitChartSlot');
assert(chartSlot !== null, 'Chart slot container located');

const emptyCard = chartSlot.querySelector('.chart-empty-state');
assert(emptyCard !== null, 'Honest empty state element is rendered instead of fake canvas graph');
assert(emptyCard.textContent.includes('No Active Options Chain / Insufficient Gamma Liquidity for XYZ'), 'Empty state displays honest message with ticker');

const retryBtn = chartSlot.querySelector('#cockpitChartRetryBtn');
assert(retryBtn !== null, 'Empty state includes interactive retry button');

const fakeCanvas = chartSlot.querySelector('canvas.quant-canvas');
assert(fakeCanvas === null, 'Fabricated fake Gaussian bell-curve canvas is completely purged');

// ----------------------------------------------------------------------------
// TEST 5: Both | Net GEX | Net DEX Tri-Mode Switcher
// ----------------------------------------------------------------------------
console.log('\n--- TEST 5: Both | Net GEX | Net DEX Tri-Mode Switcher ---');
// Switch back to NVDA to mount real chart
await cockpitView.searchTicker('NVDA');

const toggleBoth = rootContainer.querySelector('#gexDexToggle .toggle-btn[data-mode="both"]');
const toggleGex = rootContainer.querySelector('#gexDexToggle .toggle-btn[data-mode="gex"]');
const toggleDex = rootContainer.querySelector('#gexDexToggle .toggle-btn[data-mode="dex"]');

assert(toggleBoth !== null && toggleGex !== null && toggleDex !== null, 'Both, GEX, and DEX toggle buttons found');
assert(toggleBoth.classList.contains('active'), 'Both button active by default');
assert(cockpitView.chartMode === 'both', 'CockpitView chartMode initialized to both');
assert(cockpitView.quantChartInstance.mode === 'both', 'QuantChart initialized with mode both');

// 1. Click Net GEX
toggleGex.click();
assert(toggleGex.classList.contains('active'), 'Net GEX button is active after click');
assert(!toggleBoth.classList.contains('active'), 'Both button is no longer active');
assert(cockpitView.chartMode === 'gex', 'CockpitView chartMode updated to gex');
assert(cockpitView.quantChartInstance.mode === 'gex', 'QuantChart mode updated to gex');

// 2. Click Net DEX
toggleDex.click();
assert(toggleDex.classList.contains('active'), 'Net DEX button is active after click');
assert(!toggleGex.classList.contains('active'), 'Net GEX button is no longer active');
assert(cockpitView.chartMode === 'dex', 'CockpitView chartMode updated to dex');
assert(cockpitView.quantChartInstance.mode === 'dex', 'QuantChart mode updated to dex');

// 3. Click Both back
toggleBoth.click();
assert(toggleBoth.classList.contains('active'), 'Both button is active after toggle back');
assert(!toggleDex.classList.contains('active'), 'Net DEX button is no longer active');
assert(cockpitView.chartMode === 'both', 'CockpitView chartMode updated back to both');
assert(cockpitView.quantChartInstance.mode === 'both', 'QuantChart mode updated back to both');

// ----------------------------------------------------------------------------
// TEST 6: Panel 3 Options Flow Table & Filter Chips
// ----------------------------------------------------------------------------
console.log('\n--- TEST 6: Panel 3 Options Flow & Filter Chips ---');
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
// TEST 7: Table Tri-State Sorting
// ----------------------------------------------------------------------------
console.log('\n--- TEST 7: Table Tri-State Sorting ---');
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
// TEST 8: Recent Searches Persistence & Quick Suggestion Clicking
// ----------------------------------------------------------------------------
console.log('\n--- TEST 8: Recent Searches & Suggestion Chips ---');
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
assert(updatedRecents[0] === 'TSLA' && updatedRecents.includes('NVDA'), `Recents updated with TSLA as most recent: ${JSON.stringify(updatedRecents)}`);

// ----------------------------------------------------------------------------
// TEST 9: POWL Loading & Force Refresh Retry Bypass
// ----------------------------------------------------------------------------
console.log('\n--- TEST 9: POWL Loading & Force Refresh Retry ---');
await cockpitView.searchTicker('POWL', true);

assert(heroBadge.textContent === 'POWL', `Hero badge displays searched ticker POWL (got ${heroBadge.textContent})`);
assert(klSpot.textContent === '$179.73', `POWL Spot price correctly rendered: ${klSpot.textContent}`);
assert(klCall.textContent === '$190.00', `POWL Call wall correctly rendered: ${klCall.textContent}`);
assert(klPut.textContent === '$180.00', `POWL Put wall correctly rendered: ${klPut.textContent}`);
assert(cockpitView.quantChartInstance !== null, 'QuantChart instance successfully mounted for POWL');
assert(cockpitView.quantChartInstance.data.strikes.length === 4, `POWL has 4 strikes rendered in QuantChart (got ${cockpitView.quantChartInstance.data.strikes.length})`);
assert(cockpitView.quantChartInstance.data.spot_price === 179.73, 'POWL QuantChart receives $179.73 spot price');

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
