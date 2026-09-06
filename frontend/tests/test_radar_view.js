import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Confluence Radar (RADAR-01)
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
    for (const im of idMatches) {
      if (el.id !== im.slice(1)) return false;
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
    this.id = '';
    this.value = '';
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

global.localStorage = {
  getItem: () => 'mock-token',
  setItem: () => {},
  removeItem: () => {}
};

global.window = {
  location: { origin: 'http://localhost:8000' },
  quantApp: null
};

global.fetch = async (url) => {
  return {
    ok: true,
    status: 200,
    json: async () => {
      if (String(url).includes('/api/scanner/dates')) return ['2026-09-04'];
      return { scan_date: '2026-09-04', summary: null, rows: [] };
    }
  };
};

global.document = {
  createElement: (tag) => new MockElement(tag),
  querySelector: () => null
};

// ==============================================================================
// Import Component Under Test
// ==============================================================================
import { RadarView } from '../src/tabs/radar_view.js';

async function runTests() {
  console.log('==================================================================');
  console.log('  PROBING CONFLUENCE RADAR TAB 3 VIEW (RADAR-01)');
  console.log('==================================================================\n');

  let passed = 0;
  function pass(msg) {
    console.log(`  ✓ PASS: ${msg}`);
    passed++;
  }

  const container = new MockElement('div');
  container.id = 'tab-radar';
  const radar = new RadarView();

  // Test 1: Initial Render
  console.log('--- TEST 1: Initial Render & DOM Structure ---');
  radar.render(container);
  assert(container.querySelector('#radarSessionTag'), 'Session tag must be mounted');
  pass('Session tag mounted');
  assert(container.querySelector('#radarDateSelect'), 'Date selector must be mounted');
  pass('Date selector mounted');
  assert(container.querySelector('#radarMetricCards'), 'Metric cards container mounted');
  pass('Metric cards container mounted');
  assert(container.querySelector('#radarTable'), 'Leaderboard table mounted');
  pass('Leaderboard table mounted');

  // Test 2: Summary Cards Zero Derivation
  console.log('\n--- TEST 2: Summary Metric Cards (Zero Derivations) ---');
  const mockSummary = {
    scan_date: '2026-09-04',
    session_label: 'Post-Market EOD Scan (2026-09-04)',
    total_scanned_count: 40,
    confirmed_bull_count: 35,
    confirmed_bear_count: 3,
    vol_pin_count: 2,
    divergent_count: 0,
    top_whale_ticker: 'TSM',
    top_whale_premium: 34900000.0,
    formatted_top_whale_premium: '$34.90M',
    market_regime_summary: 'BULLISH FLOW CONFLUENCE'
  };

  radar.currentData = {
    scan_date: '2026-09-04',
    summary: mockSummary,
    rows: []
  };
  radar.renderSummaryCards();

  const sessionText = container.querySelector('#radarSessionText');
  assert.equal(sessionText.textContent, 'Post-Market EOD Scan (2026-09-04)');
  pass('Session label rendered directly: Post-Market EOD Scan (2026-09-04)');

  const valTotal = container.querySelector('#valTotalScanned');
  assert.equal(valTotal.textContent, '40');
  pass('Total scanned count rendered directly: 40');

  const valConfirmed = container.querySelector('#valConfirmedSetups');
  assert.equal(valConfirmed.textContent, '35 Bull / 3 Bear');
  pass('Confirmed setups count rendered directly: 35 Bull / 3 Bear');

  const valWhale = container.querySelector('#valTopWhale');
  assert.equal(valWhale.textContent, 'TSM ($34.90M)');
  pass('Top whale leader rendered directly: TSM ($34.90M)');

  const valRegime = container.querySelector('#valMarketRegime');
  assert.equal(valRegime.textContent, 'BULLISH FLOW CONFLUENCE');
  pass('Market regime summary rendered directly: BULLISH FLOW CONFLUENCE');

  // Test 3: Table Rows Zero Derivation
  console.log('\n--- TEST 3: Table Rows (Zero Derivations) ---');
  const mockRows = [
    {
      ticker: 'TSM',
      formatted_spot_price: '$428.91',
      formatted_flow_premium: '$34.90M',
      call_premium_pct: 100.0,
      flow_bias: 'BULLISH',
      gamma_regime: 'POSITIVE (LONG GAMMA)',
      formatted_net_gex: '+$97.68B',
      wall_spread_range: '$427.50 - $425.00',
      confluence_status: 'CONFIRMED_BULL',
      confluence_score: 90.0,
      whale_prints_count: 1
    },
    {
      ticker: 'TSLA',
      formatted_spot_price: '$354.08',
      formatted_flow_premium: '$28.40M',
      call_premium_pct: 78.5,
      flow_bias: 'BULLISH',
      gamma_regime: 'POSITIVE (LONG GAMMA)',
      formatted_net_gex: '+$45.20B',
      wall_spread_range: '$340.00 - $360.00',
      confluence_status: 'CONFIRMED_BULL',
      confluence_score: 85.0,
      whale_prints_count: 2
    },
    {
      ticker: 'SPY',
      formatted_spot_price: '$769.25',
      formatted_flow_premium: '$120.00M',
      call_premium_pct: 35.0,
      flow_bias: 'BEARISH',
      gamma_regime: 'POSITIVE (LONG GAMMA)',
      formatted_net_gex: '+$850.00B',
      wall_spread_range: '$750.00 - $785.00',
      confluence_status: 'STRUCTURAL_HEDGE',
      confluence_score: 75.0,
      whale_prints_count: 4
    }
  ];

  radar.currentData.rows = mockRows;
  radar.renderTableRows();

  const tbody = container.querySelector('#radarTableBody');
  assert(tbody.innerHTML.includes('TSM'), 'TSM row must be rendered');
  assert(tbody.innerHTML.includes('$428.91'), 'Formatted spot price must be rendered directly');
  assert(tbody.innerHTML.includes('$34.90M'), 'Formatted flow premium must be rendered directly');
  assert(tbody.innerHTML.includes('CONFIRMED_BULL'), 'Confluence status must be rendered');
  pass('Pre-computed table cells verified for TSM');

  // Test 4: Filtering
  console.log('\n--- TEST 4: Client-Side Filter Chips ---');
  radar.activeFilter = 'STRUCTURAL_HEDGE';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('SPY'), 'SPY must be rendered under STRUCTURAL_HEDGE');
  assert(!tbody.innerHTML.includes('TSM'), 'TSM must be hidden under STRUCTURAL_HEDGE');
  pass('Filter chip correctly isolates STRUCTURAL_HEDGE setups');

  radar.activeFilter = 'whales';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('TSM') && tbody.innerHTML.includes('SPY'), 'Whales filter includes items with whale prints');
  pass('Whales filter verified');

  radar.activeFilter = 'all';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('TSM') && tbody.innerHTML.includes('TSLA') && tbody.innerHTML.includes('SPY'), 'All filter restores full list');
  pass('All filter resets properly');

  // Test 5: 1-Click Drill Down to Cockpit
  console.log('\n--- TEST 5: 1-Click Cockpit Drill-Down ---');
  let switchedTab = null;
  let searchedTicker = null;

  global.window = {
    quantApp: {
      tabManager: {
        switchTab: (t) => { switchedTab = t; }
      },
      cockpitView: {
        searchTicker: (sym) => { searchedTicker = sym; }
      }
    }
  };

  radar.drillDownToCockpit('NVDA');
  assert.equal(switchedTab, 'cockpit', 'Tab must switch to cockpit');
  assert.equal(searchedTicker, 'NVDA', 'Cockpit searchTicker must be invoked with NVDA');
  pass('1-click drill-down successfully navigates to Cockpit and loads ticker');

  console.log('\n==================================================================');
  console.log(`  ALL RADAR VIEW TESTS PASSED (${passed} CHECKS VERIFIED)`);
  console.log('==================================================================\n');
}

runTests().catch(err => {
  console.error('Test Failed:', err);
  process.exit(1);
});
