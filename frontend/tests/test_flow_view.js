import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Options Flow Aggregate View (FLOW-01)
 */

// ==============================================================================
// High-Fidelity Mock DOM
// ==============================================================================

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
      if (this._classes.has(cls)) this._classes.delete(cls);
      else this._classes.add(cls);
    }
    this._sync();
  }
  _sync() {
    this._el._className = Array.from(this._classes).join(' ');
  }
}

function parseAttributes(attrStr, el) {
  if (!attrStr) return;
  const attrRegex = /([a-zA-Z0-9\-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^>\s]+)))?/g;
  let match;
  while ((match = attrRegex.exec(attrStr)) !== null) {
    const name = match[1];
    const val = match[2] !== undefined ? match[2] : (match[3] !== undefined ? match[3] : (match[4] || ''));
    if (name === 'id') {
      el.id = val;
    } else if (name === 'class') {
      el.className = val;
    } else if (name.startsWith('data-')) {
      const dataKey = name.slice(5).replace(/-([a-z])/g, (_, l) => l.toUpperCase());
      el.dataset[dataKey] = val;
    } else {
      el[name] = val;
    }
  }
}

function matchesSingle(el, part) {
  if (!el || !part) return false;
  if (part.includes('#')) {
    const idMatches = part.match(/#[a-zA-Z0-9\-_]+/g);
    if (idMatches) {
      for (const im of idMatches) {
        if (el.id !== im.slice(1)) return false;
      }
    }
  }
  const tagMatch = part.match(/^([a-zA-Z0-9\-]+)/);
  if (tagMatch) {
    if (el.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
  }
  const classMatches = part.match(/\.([a-zA-Z0-9\-_]+)/g);
  if (classMatches) {
    for (const cm of classMatches) {
      if (!el.classList.contains(cm.slice(1))) return false;
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
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  const groups = selector.split(',').map(s => s.trim()).filter(Boolean);
  return groups.some(group => {
    const parts = group.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return false;
    if (parts.length === 1) return matchesSingle(el, parts[0]);
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
  constructor(tagName = 'div') {
    this.tagName = tagName.toUpperCase();
    this._className = '';
    this.classList = new MockClassList(this);
    this.dataset = {};
    this.children = [];
    this._textParts = [];
    this.parentElement = null;
    this.listeners = {};
    this._innerHTML = '';
    this.id = '';
    this.value = '';
    this.style = {};
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
        if (current) current._textParts.push(text);
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

          if (!isVoid) {
            stack.push({ el: newEl, tag: tagName });
          }
        }
      }
    }
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
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

  closest(selector) {
    let cur = this;
    while (cur) {
      if (matchesSelector(cur, selector)) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  addEventListener(type, cb) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(cb);
  }

  dispatchEvent(evt) {
    let stopped = false;
    const eventObj = evt || {
      type: 'click',
      stopPropagation: () => { stopped = true; },
      preventDefault: () => {},
      target: this,
      currentTarget: this
    };
    if (!eventObj.target) eventObj.target = this;
    if (!eventObj.currentTarget) eventObj.currentTarget = this;

    const handlers = (this.listeners[eventObj.type || 'click'] || []).slice();
    for (const h of handlers) {
      h(eventObj);
      if (stopped) return;
    }

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
}

// Global Browser Mock
const rootDocument = new MockElement('body');
global.document = {
  createElement: (tag) => new MockElement(tag),
  querySelector: (sel) => rootDocument.querySelector(sel),
  querySelectorAll: (sel) => rootDocument.querySelectorAll(sel)
};

global.localStorage = {
  getItem: () => 'mock-jwt-token',
  setItem: () => {},
  removeItem: () => {}
};

global.window = {
  location: { origin: 'http://localhost:8000' },
  quantApp: {
    tabManager: {
      switchTab: (id) => { global.window.activeTab = id; }
    },
    cockpitView: {
      searchTicker: (sym) => { global.window.searchedTicker = sym; }
    }
  }
};

const MOCK_FLOW_RESPONSE = {
  as_of_date: '2026-09-04',
  latest_market_day: '2026-09-04',
  window_3d: {
    market_dates: ['2026-09-04', '2026-09-03', '2026-09-02'],
    top_premium_bullish: [
      { rank: 1, symbol: 'SMH', total_premium: 24467000, formatted_premium: '$24.5M', contract_count: 2, active_days: 1 },
      { rank: 2, symbol: 'AMD', total_premium: 23763000, formatted_premium: '$23.8M', contract_count: 5, active_days: 3 },
      { rank: 3, symbol: 'NVDA', total_premium: 23067000, formatted_premium: '$23.1M', contract_count: 8, active_days: 3 },
      { rank: 4, symbol: 'VIX', total_premium: 12700000, formatted_premium: '$12.7M', contract_count: 1, active_days: 1 },
      { rank: 5, symbol: 'MSTR', total_premium: 9383000, formatted_premium: '$9.4M', contract_count: 2, active_days: 2 }
    ],
    top_hits_bullish: [
      { rank: 1, symbol: 'NVDA', contract_count: 8, formatted_premium: '$23.1M', active_days: 3 },
      { rank: 2, symbol: 'AMD', contract_count: 5, formatted_premium: '$23.8M', active_days: 3 },
      { rank: 3, symbol: 'SKHY', contract_count: 5, formatted_premium: '$7.9M', active_days: 1 },
      { rank: 4, symbol: 'SOXX', contract_count: 4, formatted_premium: '$4.5M', active_days: 2 },
      { rank: 5, symbol: 'ORCL', contract_count: 4, formatted_premium: '$3.7M', active_days: 2 }
    ],
    top_premium_bearish: [
      { rank: 1, symbol: 'SPCX', total_premium: 8350000, formatted_premium: '$8.4M', contract_count: 4, active_days: 2 },
      { rank: 2, symbol: 'PCG', total_premium: 4700000, formatted_premium: '$4.7M', contract_count: 1, active_days: 1 },
      { rank: 3, symbol: 'MDB', total_premium: 3800000, formatted_premium: '$3.8M', contract_count: 1, active_days: 1 },
      { rank: 4, symbol: 'LITE', total_premium: 3800000, formatted_premium: '$3.8M', contract_count: 1, active_days: 1 },
      { rank: 5, symbol: 'XBI', total_premium: 3500000, formatted_premium: '$3.5M', contract_count: 1, active_days: 1 }
    ],
    top_hits_bearish: [
      { rank: 1, symbol: 'SPCX', contract_count: 2, formatted_premium: '$1.3M', active_days: 1 },
      { rank: 2, symbol: 'PCG', contract_count: 1, formatted_premium: '$4.7M', active_days: 1 },
      { rank: 3, symbol: 'MDB', contract_count: 1, formatted_premium: '$3.8M', active_days: 1 },
      { rank: 4, symbol: 'LITE', contract_count: 1, formatted_premium: '$3.8M', active_days: 1 },
      { rank: 5, symbol: 'XBI', contract_count: 1, formatted_premium: '$3.5M', active_days: 1 }
    ]
  },
  window_1w: {
    market_dates: ['2026-09-04', '2026-09-03', '2026-09-02', '2026-09-01', '2026-08-31'],
    top_premium_bullish: [
      { rank: 1, symbol: 'SMH', total_premium: 27027000, formatted_premium: '$27.0M', contract_count: 6, active_days: 3 },
      { rank: 2, symbol: 'NVDA', total_premium: 26767000, formatted_premium: '$26.8M', contract_count: 9, active_days: 4 },
      { rank: 3, symbol: 'VIX', total_premium: 26000000, formatted_premium: '$26.0M', contract_count: 2, active_days: 2 },
      { rank: 4, symbol: 'AMD', total_premium: 25263000, formatted_premium: '$25.3M', contract_count: 6, active_days: 4 },
      { rank: 5, symbol: 'MU', total_premium: 19923000, formatted_premium: '$19.9M', contract_count: 6, active_days: 5 }
    ],
    top_hits_bullish: [
      { rank: 1, symbol: 'SQQQ', contract_count: 10, formatted_premium: '$4.7M', active_days: 5 },
      { rank: 2, symbol: 'NVDA', contract_count: 9, formatted_premium: '$26.8M', active_days: 4 },
      { rank: 3, symbol: 'SOXL', contract_count: 8, formatted_premium: '$13.5M', active_days: 3 },
      { rank: 4, symbol: 'SOXX', contract_count: 7, formatted_premium: '$8.1M', active_days: 4 },
      { rank: 5, symbol: 'IREN', contract_count: 7, formatted_premium: '$4.9M', active_days: 5 }
    ],
    top_premium_bearish: [
      { rank: 1, symbol: 'SPCX', total_premium: 10500000, formatted_premium: '$10.5M', contract_count: 5, active_days: 3 },
      { rank: 2, symbol: 'IREN', total_premium: 4900000, formatted_premium: '$4.9M', contract_count: 3, active_days: 2 },
      { rank: 3, symbol: 'PCG', total_premium: 4700000, formatted_premium: '$4.7M', contract_count: 1, active_days: 1 },
      { rank: 4, symbol: 'MDB', total_premium: 3800000, formatted_premium: '$3.8M', contract_count: 1, active_days: 1 },
      { rank: 5, symbol: 'AAPL', total_premium: 3200000, formatted_premium: '$3.2M', contract_count: 2, active_days: 2 }
    ],
    top_hits_bearish: [
      { rank: 1, symbol: 'IREN', contract_count: 3, formatted_premium: '$4.9M', active_days: 2 },
      { rank: 2, symbol: 'SPCX', contract_count: 3, formatted_premium: '$3.5M', active_days: 2 },
      { rank: 3, symbol: 'AAPL', contract_count: 2, formatted_premium: '$3.2M', active_days: 2 },
      { rank: 4, symbol: 'GH', contract_count: 2, formatted_premium: '$2.6M', active_days: 1 },
      { rank: 5, symbol: 'CRM', contract_count: 2, formatted_premium: '$2.2M', active_days: 2 }
    ]
  },
  window_7d: {
    market_dates: ['2026-09-04', '2026-09-03', '2026-09-02', '2026-09-01', '2026-08-31'],
    top_premium_bullish: [],
    top_hits_bullish: [],
    top_premium_bearish: [],
    top_hits_bearish: []
  }
};

global.fetch = async (url) => {
  return {
    ok: true,
    status: 200,
    json: async () => MOCK_FLOW_RESPONSE
  };
};

// Import FlowView
import { FlowView } from '../src/tabs/flow_view.js';

// ==============================================================================
// TEST EXECUTION
// ==============================================================================
async function runTests() {
  console.log('==================================================================');
  console.log('  PROBING QUANT PWA OPTIONS FLOW AGGREGATE VIEW (FLOW-01)');
  console.log('==================================================================\n');

  const container = new MockElement('div');
  const view = new FlowView();

  // Test 1: Render DOM Structure
  console.log('--- TEST 1: Initial Render & Structure ---');
  view.render(container);

  assert(container.querySelector('.flow-view-container'), 'flow-view-container is rendered');
  assert(container.querySelector('.flow-title'), 'flow-title is rendered');
  assert(container.querySelector('#flowSessionTag'), 'flowSessionTag is rendered');
  assert(container.querySelector('#flowDurationToggle'), 'flowDurationToggle is rendered');
  assert(container.querySelector('#cardTopPremium'), 'cardTopPremium card is mounted');
  assert(container.querySelector('#cardTopBullish'), 'cardTopBullish card is mounted');
  assert(container.querySelector('#cardTopBearishPremium'), 'cardTopBearishPremium card is mounted');
  assert(container.querySelector('#cardTopBearish'), 'cardTopBearish card is mounted');
  console.log('  ✓ PASS: All 4 primary section cards and controls are mounted in DOM');

  // Test 2: Populate Mock Data & Verify 3D Tables
  console.log('\n--- TEST 2: Populate 3D Data & Verify Table Contents ---');
  view.currentData = MOCK_FLOW_RESPONSE;

  view.renderSessionHeader();
  view.renderActiveTables();

  const sessionText = container.querySelector('#flowSessionText');
  assert(sessionText.textContent.includes('2026-09-04'), 'Header reflects correct as-of date');

  const rowsPrem = container.querySelectorAll('#flowBodyPremium tr[data-ticker]');
  assert.equal(rowsPrem.length, 5, 'Top Premium has 5 rows in 3D');
  assert.equal(rowsPrem[0].dataset.ticker, 'SMH', 'Top Premium rank 1 is SMH');

  const rowsBull = container.querySelectorAll('#flowBodyBullish tr[data-ticker]');
  assert.equal(rowsBull.length, 5, 'Top Bullish Hits has 5 rows in 3D');
  assert.equal(rowsBull[0].dataset.ticker, 'NVDA', 'Top Bullish Hits rank 1 is NVDA');

  const rowsBearPrem = container.querySelectorAll('#flowBodyBearishPremium tr[data-ticker]');
  assert.equal(rowsBearPrem.length, 5, 'Top Bearish Premium has 5 rows in 3D');
  assert.equal(rowsBearPrem[0].dataset.ticker, 'SPCX', 'Top Bearish Premium rank 1 is SPCX');

  const rowsBear = container.querySelectorAll('#flowBodyBearish tr[data-ticker]');
  assert.equal(rowsBear.length, 5, 'Top Bearish Hits has 5 rows in 3D');
  assert.equal(rowsBear[0].dataset.ticker, 'SPCX', 'Top Bearish Hits rank 1 is SPCX');
  console.log('  ✓ PASS: 3D window renders exactly 5 rows per section with correct top tickers');

  // Test 3: Switch to 1W Duration
  console.log('\n--- TEST 3: Switch to 1W Duration & Verify Re-render ---');
  const btn1w = container.querySelector('button[data-duration="1w"]');
  assert(btn1w, '1W duration button found');
  btn1w.dispatchEvent({ type: 'click' });

  assert.equal(view.activeDuration, '1w', 'Active duration switched to 1w');
  const rowsBull1w = container.querySelectorAll('#flowBodyBullish tr[data-ticker]');
  assert.equal(rowsBull1w.length, 5, 'Top Bullish Hits has 5 rows in 1W');
  assert.equal(rowsBull1w[0].dataset.ticker, 'SQQQ', 'Top Bullish Hits rank 1 in 1W is SQQQ');

  const rowsBearPrem1w = container.querySelectorAll('#flowBodyBearishPremium tr[data-ticker]');
  assert.equal(rowsBearPrem1w.length, 5, 'Top Bearish Premium has 5 rows in 1W');
  assert.equal(rowsBearPrem1w[0].dataset.ticker, 'SPCX', 'Top Bearish Premium rank 1 in 1W is SPCX');
  console.log('  ✓ PASS: 1W duration toggle switches and updates tables instantaneously');

  // Test 4: Cockpit Drill-Down
  console.log('\n--- TEST 4: Cockpit Drill-Down on Row Click ---');
  view.drillDownToCockpit('NVDA');
  assert.equal(global.window.activeTab, 'cockpit', 'Active tab switched to cockpit');
  assert.equal(global.window.searchedTicker, 'NVDA', 'Cockpit searchTicker triggered for NVDA');
  console.log('  ✓ PASS: Clicking a ticker seamlessly switches to Cockpit and searches ticker');

  console.log('\n==================================================================');
  console.log('  ALL FLOW VIEW DOM INTEGRATION TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
