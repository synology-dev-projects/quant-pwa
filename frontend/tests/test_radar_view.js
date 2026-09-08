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

  getBoundingClientRect() {
    return { left: 0, top: 0, width: 400, height: 450, right: 400, bottom: 450 };
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
      measureText: (txt) => ({ width: (txt || '').length * 8 }),
      font: '',
      fillStyle: '',
      strokeStyle: ''
    };
  }
}

global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

global.requestAnimationFrame = (cb) => { setImmediate(cb); };

global.localStorage = {
  getItem: () => 'mock-token',
  setItem: () => {},
  removeItem: () => {}
};

global.window = {
  location: { origin: 'http://localhost:8000' },
  devicePixelRatio: 2,
  requestAnimationFrame: (cb) => { setImmediate(cb); },
  quantApp: null
};

global.fetch = async (url) => {
  return {
    ok: true,
    status: 200,
    json: async () => {
      if (String(url).includes('/api/scanner/dates')) return ['2026-09-04'];
      if (String(url).includes('/api/cockpit/data')) {
        return {
          ticker: 'TSLA',
          spot_price: 354.08,
          gex: {
            spot_price: 354.08,
            zero_gex_level: 350.00,
            call_wall: 360.00,
            put_wall: 340.00,
            strikes: [
              { strike: 340, call_gex: 100, put_gex: 500, net_gex: -400, call_dex: 50, put_dex: 200, net_dex: -150 },
              { strike: 350, call_gex: 300, put_gex: 300, net_gex: 0, call_dex: 150, put_dex: 150, net_dex: 0 },
              { strike: 360, call_gex: 600, put_gex: 100, net_gex: 500, call_dex: 300, put_dex: 50, net_dex: 250 }
            ]
          },
          flow: {
            records: [
              { trade_date: '2026-09-04', strike: 360, expiration: '2026-09-18', put_call: 'CALL', premium: 2500000, action: 'BUY', spot: 354.08, order_type: 'SWEEP' }
            ]
          },
          metrics: {
            confluence_bias: 'BULLISH',
            gamma_regime: 'LONG GAMMA (+GEX)',
            call_pct: 75.0,
            whale_count: 3
          }
        };
      }
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
  assert(container.querySelector('#radarInspectorSection'), 'Inspector section mounted');
  pass('Inspector section mounted');
  assert(container.querySelector('#radarTable'), 'Leaderboard table mounted');
  pass('Leaderboard table mounted');

  // Test 2: Summary Cards Zero Derivation
  console.log('\n--- TEST 2: Summary Metric Cards (Zero Derivations) ---');
  const mockSummary = {
    scan_date: '2026-09-04',
    session_label: 'Post-Market EOD Scan (2026-09-04)',
    total_scanned_count: 4,
    total_watchlist_count: 50,
    qualifying_bull_spring_count: 3,
    qualifying_bear_exhaustion_count: 1,
    top_catalyst_ticker: 'TSLA',
    top_catalyst_expiry: '$360 Call Wall • 12 DTE',
    top_whale_ticker: 'TSLA',
    top_whale_premium: 28400000.0,
    formatted_top_whale_premium: '$28.40M',
    market_regime_summary: 'BULL SPRING CONFLUENCE'
  };

  const mockRows = [
    {
      rank: 1,
      ticker: 'TSLA',
      spot_price: 354.08,
      formatted_spot_price: '$354.08',
      play_type: 'BULL_SPRING',
      exposure_imbalance_pct: 88.4,
      imbalance_type: 'DEX',
      pin_wall_strike: 360.0,
      pin_wall_type: 'CALL_WALL',
      pin_dte: 12,
      pin_dist_pct: 1.7,
      flow_call_put_ratio: 3.4,
      flow_hits_count: 14,
      viability_score: 94.5
    },
    {
      rank: 2,
      ticker: 'NVDA',
      spot_price: 350.00,
      formatted_spot_price: '$350.00',
      play_type: 'BULL_SPRING',
      exposure_imbalance_pct: 85.0,
      imbalance_type: 'GEX',
      pin_wall_strike: 355.0,
      pin_wall_type: 'CALL_WALL',
      pin_dte: 14,
      pin_dist_pct: 1.4,
      flow_call_put_ratio: 5.0,
      flow_hits_count: 16,
      viability_score: 91.0
    },
    {
      rank: 3,
      ticker: 'AMD',
      spot_price: 155.00,
      formatted_spot_price: '$155.00',
      play_type: 'BEAR_EXHAUSTION',
      exposure_imbalance_pct: 82.5,
      imbalance_type: 'GEX',
      pin_wall_strike: 150.0,
      pin_wall_type: 'PUT_WALL',
      pin_dte: 7,
      pin_dist_pct: 3.2,
      flow_call_put_ratio: 2.8,
      flow_hits_count: 8,
      viability_score: 86.5
    }
  ];

  radar.currentData = {
    scan_date: '2026-09-04',
    summary: mockSummary,
    rows: mockRows
  };
  // Test 2: Top Metric Pill Boxes Purged
  console.log('\n--- TEST 2: Purge 4 Top Metric Pill Boxes & Position Top 10 at Top ---');
  const sessionText = container.querySelector('#radarSessionText');
  assert(sessionText, 'Session header must remain present');

  // Verify the 4 old pill boxes are removed from the DOM
  assert.equal(container.querySelector('#valTotalScanned'), null, 'valTotalScanned pill box must be removed');
  assert.equal(container.querySelector('#valConfirmedSetups'), null, 'valConfirmedSetups pill box must be removed');
  assert.equal(container.querySelector('#valTopWhale'), null, 'valTopWhale pill box must be removed');
  assert.equal(container.querySelector('#valMarketRegime'), null, 'valMarketRegime pill box must be removed');
  pass('4 top metric pill boxes successfully purged from view');

  // Test 3: Table Rows Zero Derivation
  console.log('\n--- TEST 3: Table Rows (Zero Derivations) ---');
  radar.renderTableRows();

  const tbody = container.querySelector('#radarTableBody');
  assert(tbody.innerHTML.includes('TSLA'), 'TSLA row must be rendered');
  assert(tbody.innerHTML.includes('#1'), 'Rank #1 badge must be rendered');
  assert(tbody.innerHTML.includes('$354.08'), 'Formatted spot price must be rendered directly');
  assert(tbody.innerHTML.includes('BULL SPRING'), 'BULL SPRING play badge must be rendered');
  assert(tbody.innerHTML.includes('88.4% DEX Above'), 'Exposure imbalance pill must be rendered');
  assert(tbody.innerHTML.includes('$360.00 CALL WALL'), 'Pinning node strike and type must be rendered');
  assert(tbody.innerHTML.includes('12 DTE'), 'Pinning node DTE must be rendered');
  assert(tbody.innerHTML.includes('3.4x C/P'), 'Flow accumulation ratio must be rendered');
  assert(tbody.innerHTML.includes('94.5'), 'Viability score must be rendered');
  pass('Pre-computed asymmetric leaderboard cells verified for TSLA');

  // Test 4: Filtering
  console.log('\n--- TEST 4: Client-Side Filter Chips ---');
  radar.activeFilter = 'BEAR_EXHAUSTION';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('AMD'), 'AMD must be rendered under BEAR_EXHAUSTION');
  assert(!tbody.innerHTML.includes('TSLA'), 'TSLA must be hidden under BEAR_EXHAUSTION');
  pass('Filter chip correctly isolates BEAR_EXHAUSTION setups');

  radar.activeFilter = 'BULL_SPRING';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('TSLA') && tbody.innerHTML.includes('NVDA'), 'BULL_SPRING filter includes TSLA and NVDA');
  assert(!tbody.innerHTML.includes('AMD'), 'AMD must be hidden under BULL_SPRING');
  pass('Filter chip correctly isolates BULL_SPRING setups');

  radar.activeFilter = 'all';
  radar.renderTableRows();
  assert(tbody.innerHTML.includes('TSLA') && tbody.innerHTML.includes('NVDA') && tbody.innerHTML.includes('AMD'), 'All filter restores full Top 10 list');
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

  // Test 6: Active Ticker Selection
  console.log('\n--- TEST 6: Active Ticker Selection & Inspector Trigger ---');
  assert(typeof radar.selectTicker === 'function', 'radar.selectTicker function must exist');
  radar.selectTicker('TSLA');
  assert.equal(radar.selectedTicker, 'TSLA', 'radar.selectedTicker must be set to TSLA');
  pass('selectTicker updates active state to TSLA');

  // Test 7: Explainability Card ("Why it was picked")
  console.log('\n--- TEST 7: Explainability Rationale Box ---');
  const explainBox = container.querySelector('#radarExplainBox');
  assert(explainBox, '#radarExplainBox must exist in inspector section');
  assert(explainBox.innerHTML.includes('TSLA'), 'Explain box must display selected ticker');
  assert(explainBox.innerHTML.includes('BULL SPRING') || explainBox.innerHTML.includes('BULL_SPRING'), 'Explain box must display play type');
  assert(explainBox.innerHTML.includes('88.4%') && explainBox.innerHTML.includes('DEX'), 'Explain box must explain exposure imbalance');
  assert(explainBox.innerHTML.includes('$360') && explainBox.innerHTML.includes('12 DTE'), 'Explain box must explain pinning wall catalyst');
  pass('Explainability rationale renders deterministic quantitative breakdown');

  // Test 8: Interactive Options Exposure Chart Slot
  console.log('\n--- TEST 8: GEX/DEX Exposure Chart Slot in Inspector ---');
  const chartSlot = container.querySelector('#radarChartSlot');
  assert(chartSlot, '#radarChartSlot must exist in inspector section');
  const klSpot = container.querySelector('#radarKlSpot');
  const klFlip = container.querySelector('#radarKlFlip');
  const klCall = container.querySelector('#radarKlCall');
  const klPut = container.querySelector('#radarKlPut');
  assert(klSpot && klFlip && klCall && klPut, 'All 4 Key Level badges must exist in inspector chart header');
  pass('Inspector chart slot and key level badges verified');

  // Test 9: 30-Day Options Flow Hits Table in Inspector
  console.log('\n--- TEST 9: 30-Day Options Flow Table in Inspector ---');
  const flowSlot = container.querySelector('#radarFlowSlot');
  assert(flowSlot, '#radarFlowSlot must exist in inspector section');
  pass('Inspector flow prints slot verified');

  console.log('\n==================================================================');
  console.log(`  ALL RADAR VIEW TESTS PASSED (${passed} CHECKS VERIFIED)`);
  console.log('==================================================================\n');
}

runTests().catch(err => {
  console.error('Test Failed:', err);
  process.exit(1);
});
