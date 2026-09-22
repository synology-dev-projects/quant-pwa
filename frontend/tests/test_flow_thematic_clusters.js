import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Thematic Flow Clusters View (FLOW-02)
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
    return this.contains(cls);
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
    } else if (name === 'style') {
      el._rawStyle = val;
      const declarations = val.split(';').map(s => s.trim()).filter(Boolean);
      for (const decl of declarations) {
        const [k, v] = decl.split(':').map(s => s.trim());
        if (k && v) {
          const camelKey = k.replace(/-([a-z])/g, (_, l) => l.toUpperCase());
          el.style[camelKey] = v;
        }
      }
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
  activeTab: null,
  searchedTicker: null,
  quantApp: {
    tabManager: {
      switchTab: (id) => { global.window.activeTab = id; }
    },
    cockpitView: {
      searchTicker: (sym) => { global.window.searchedTicker = sym; }
    }
  }
};

// ==============================================================================
// Mock Data Fixtures
// ==============================================================================

const MOCK_FLOW_RESPONSE = {
  as_of_date: '2026-09-21',
  latest_market_day: '2026-09-21',
  window_3d: {
    market_dates: ['2026-09-21'],
    top_premium_bullish: [],
    top_hits_bullish: [],
    top_premium_bearish: [],
    top_hits_bearish: []
  },
  synthesis_markdown: '### Flow Synthesis'
};

const MOCK_CLUSTERS_RESPONSE = {
  status: 'ok',
  trade_date: '2026-09-21',
  count: 2,
  clusters: [
    {
      cluster_id: 'cluster-2026-09-21-1',
      trade_date: '2026-09-21',
      theme_name: 'Semiconductors Rotation (NVDA, MU, AVGO)',
      dominant_sector: 'Semiconductors',
      ticker_count: 3,
      combined_premium: 38400000,
      net_sentiment: 'BULLISH',
      call_premium: 29800000,
      put_premium: 8600000,
      avg_cosine_distance: 0.162,
      max_cosine_distance: 0.215,
      avg_similarity: 0.838,
      tickers: [
        { ticker: 'NVDA', company_name: 'NVIDIA Corporation', premium: 18230000, sentiment: 'BULLISH', call_put_ratio: 3.45, trade_count: 82 },
        { ticker: 'MU', company_name: 'Micron Technology Inc', premium: 12500000, sentiment: 'BULLISH', call_put_ratio: 2.80, trade_count: 45 },
        { ticker: 'AVGO', company_name: 'Broadcom Inc', premium: 7670000, sentiment: 'BEARISH', call_put_ratio: 0.85, trade_count: 31 }
      ]
    },
    {
      cluster_id: 'cluster-2026-09-21-2',
      trade_date: '2026-09-21',
      theme_name: 'Enterprise Cloud & Cybersecurity Rotation (CRWD, MSFT)',
      dominant_sector: 'Information Technology',
      ticker_count: 2,
      combined_premium: 14200000,
      net_sentiment: 'BEARISH',
      call_premium: 4100000,
      put_premium: 10100000,
      avg_cosine_distance: 0.185,
      max_cosine_distance: 0.185,
      avg_similarity: 0.815,
      tickers: [
        { ticker: 'CRWD', company_name: 'CrowdStrike Holdings Inc', premium: 8900000, sentiment: 'BEARISH', call_put_ratio: 0.40, trade_count: 28 },
        { ticker: 'MSFT', company_name: 'Microsoft Corporation', premium: 5300000, sentiment: 'BULLISH', call_put_ratio: 1.65, trade_count: 19 }
      ]
    }
  ]
};

// Global Fetch Interceptor
let activeFetchUrl = null;
let customFetchHandler = null;

global.fetch = async (url, opts) => {
  activeFetchUrl = url;
  if (customFetchHandler) {
    return customFetchHandler(url, opts);
  }
  if (url.includes('/api/flow/thematic-clusters')) {
    return {
      ok: true,
      status: 200,
      json: async () => JSON.parse(JSON.stringify(MOCK_CLUSTERS_RESPONSE))
    };
  }
  if (url.includes('/api/flow/aggregate')) {
    return {
      ok: true,
      status: 200,
      json: async () => JSON.parse(JSON.stringify(MOCK_FLOW_RESPONSE))
    };
  }
  return { ok: false, status: 404 };
};

// ==============================================================================
// Import FlowView Module
// ==============================================================================

const { FlowView } = await import('../src/tabs/flow_view.js');

// ==============================================================================
// TEST EXECUTION RUNNER
// ==============================================================================

async function runTests() {
  console.log('==================================================================');
  console.log('  PROBING THEMATIC FLOW CLUSTERS UI (FLOW-02)');
  console.log('==================================================================\n');

  const container = new MockElement('div');
  container.id = 'flowTabContainer';
  rootDocument.appendChild(container);

  const view = new FlowView();
  view.render(container);

  // Allow initial loadFlowData to complete
  await new Promise(r => setTimeout(r, 20));

  // --- TEST 1: Initial Mount & Mode Switcher Presence ---
  console.log('--- TEST 1: Initial Mount & Mode Switcher Presence ---');
  const modeToggle = container.querySelector('#flowModeToggle');
  assert.ok(modeToggle, 'Mode switcher #flowModeToggle must exist');
  const modeBtns = modeToggle.querySelectorAll('.flow-mode-btn');
  assert.strictEqual(modeBtns.length, 2, 'Should have exactly 2 mode buttons: Rankings and Clusters');
  assert.ok(modeBtns[0].classList.contains('active'), 'Rankings button must be active initially');
  assert.strictEqual(view.activeViewMode, 'rankings');

  const rankingsGrid = container.querySelector('#flowSectionsGrid');
  const clustersContainer = container.querySelector('#flowClustersContainer');
  assert.ok(rankingsGrid, '#flowSectionsGrid must exist');
  assert.ok(clustersContainer, '#flowClustersContainer must exist');
  assert.strictEqual(clustersContainer.style.display, 'none', 'Clusters container must be hidden initially');
  console.log('  ✓ PASS: Mode switcher is mounted and Rankings is default view\n');

  // --- TEST 2: Switch to Thematic Clusters Mode ---
  console.log('--- TEST 2: Switch to Thematic Clusters Mode ---');
  const clustersBtn = modeToggle.querySelector('[data-mode="clusters"]');
  assert.ok(clustersBtn, 'Clusters mode button must exist');
  clustersBtn.dispatchEvent({ type: 'click' });

  assert.strictEqual(view.activeViewMode, 'clusters');
  assert.strictEqual(rankingsGrid.style.display, 'none', 'Rankings grid must be hidden in clusters mode');
  assert.strictEqual(clustersContainer.style.display, 'block', 'Clusters container must be displayed');
  const durationToggle = container.querySelector('#flowDurationToggle');
  assert.strictEqual(durationToggle.style.display, 'none', 'Duration toggle should be hidden in clusters mode');

  // Wait for loadThematicClusters fetch to resolve
  await new Promise(r => setTimeout(r, 20));
  assert.ok(activeFetchUrl.includes('/api/flow/thematic-clusters'), 'Fetch must have been called for thematic clusters');
  console.log('  ✓ PASS: Successfully switched to Thematic Clusters mode and fetched API\n');

  // --- TEST 3: Cluster Cards Rendering & Data Integrity ---
  console.log('--- TEST 3: Cluster Cards Rendering & Data Integrity ---');
  const cards = clustersContainer.querySelectorAll('.cluster-card');
  assert.strictEqual(cards.length, 2, 'Should render exactly 2 cluster cards');

  // Card 1: Semiconductors Rotation
  const card1 = cards[0];
  const title1 = card1.querySelector('.cluster-theme-title');
  assert.ok(title1.textContent.includes('Semiconductors Rotation'), 'Card 1 title must reflect dominant sector theme');
  const sector1 = card1.querySelector('.cluster-sector-pill');
  assert.strictEqual(sector1.textContent, 'Semiconductors');
  const premium1 = card1.querySelector('.cluster-premium-val');
  assert.strictEqual(premium1.textContent, '$38.4M', 'Card 1 capital must be formatted as $38.4M');
  const sim1 = card1.querySelector('.cluster-similarity-val');
  assert.strictEqual(sim1.textContent, '84%', 'Card 1 similarity must round to 84%');
  const sent1 = card1.querySelector('.cluster-sentiment-badge');
  assert.ok(sent1.classList.contains('badge-bullish'), 'Card 1 must have badge-bullish');
  assert.strictEqual(sent1.textContent, 'BULLISH');

  // Card 1 Constituent Tickers Table
  const tickerRows1 = card1.querySelectorAll('.cluster-ticker-row');
  assert.strictEqual(tickerRows1.length, 3, 'Card 1 must contain 3 constituent ticker rows');
  const symbols1 = tickerRows1.map(r => r.dataset.ticker);
  assert.deepStrictEqual(symbols1, ['NVDA', 'MU', 'AVGO'], 'Tickers must be sorted descending by premium');

  // Card 2: Enterprise Cloud & Cybersecurity
  const card2 = cards[1];
  const title2 = card2.querySelector('.cluster-theme-title');
  assert.ok(title2.textContent.includes('Enterprise Cloud'), 'Card 2 title must reflect Enterprise Cloud');
  const sent2 = card2.querySelector('.cluster-sentiment-badge');
  assert.ok(sent2.classList.contains('badge-bearish'), 'Card 2 must have badge-bearish');
  assert.strictEqual(sent2.textContent, 'BEARISH');
  const premium2 = card2.querySelector('.cluster-premium-val');
  assert.strictEqual(premium2.textContent, '$14.2M');
  console.log('  ✓ PASS: Cluster cards rendered with authentic titles, badges, and ticker rows\n');

  // --- TEST 4: Accordion Collapse / Expand ---
  console.log('--- TEST 4: Accordion Collapse / Expand ---');
  // Initially top 3 are expanded, so card1 is not collapsed
  assert.strictEqual(card1.classList.contains('collapsed'), false, 'Top card must be expanded by default');
  const body1 = card1.querySelector('.cluster-card-body');
  assert.strictEqual(body1.style.display, 'block');

  // Click card header to collapse
  const header1 = card1.querySelector('.cluster-card-header');
  header1.dispatchEvent({ type: 'click' });
  assert.strictEqual(card1.classList.contains('collapsed'), true, 'Card 1 must be collapsed after header click');
  assert.strictEqual(body1.style.display, 'none', 'Card 1 body must be hidden when collapsed');
  const chevron1 = card1.querySelector('.cluster-chevron');
  assert.strictEqual(chevron1.textContent, '▼', 'Chevron must point down when collapsed');

  // Click again to re-expand
  header1.dispatchEvent({ type: 'click' });
  assert.strictEqual(card1.classList.contains('collapsed'), false, 'Card 1 must be expanded after second click');
  assert.strictEqual(body1.style.display, 'block', 'Card 1 body must be visible when expanded');
  assert.strictEqual(chevron1.textContent, '▲', 'Chevron must point up when expanded');
  console.log('  ✓ PASS: Accordion collapse and expand behaves seamlessly\n');

  // --- TEST 5: Cockpit Drill-Down Navigation ---
  console.log('--- TEST 5: Cockpit Drill-Down Navigation ---');
  global.window.activeTab = null;
  global.window.searchedTicker = null;

  const muBtn = card1.querySelector('.cluster-ticker-btn[data-ticker="MU"]');
  assert.ok(muBtn, 'MU ticker button must exist in card 1');
  muBtn.dispatchEvent({ type: 'click' });

  assert.strictEqual(global.window.activeTab, 'cockpit', 'Clicking ticker must switch tab to cockpit');
  assert.strictEqual(global.window.searchedTicker, 'MU', 'Clicking ticker must pre-populate Cockpit with MU');

  // Test inspect button
  global.window.activeTab = null;
  global.window.searchedTicker = null;
  const avgoInspectBtn = card1.querySelector('.cluster-inspect-btn[data-ticker="AVGO"]');
  assert.ok(avgoInspectBtn, 'AVGO inspect button must exist');
  avgoInspectBtn.dispatchEvent({ type: 'click' });

  assert.strictEqual(global.window.activeTab, 'cockpit');
  assert.strictEqual(global.window.searchedTicker, 'AVGO');
  console.log('  ✓ PASS: Constituent ticker click successfully drills down into CockpitView\n');

  // --- TEST 6: Hurdle Filter Switching ---
  console.log('--- TEST 6: Hurdle Filter Switching ---');
  const hurdleBtns = container.querySelectorAll('#clustersHurdleToggle .clusters-hurdle-btn');
  assert.strictEqual(hurdleBtns.length, 3, 'Must have 3 hurdle buttons: $500K, $1.0M, $2.5M');

  const hurdle1m = container.querySelector('[data-hurdle="1000000"]');
  assert.ok(hurdle1m, '$1.0M hurdle button must exist');
  hurdle1m.dispatchEvent({ type: 'click' });

  assert.strictEqual(view.activeHurdle, 1000000, 'activeHurdle must update to 1,000,000');
  await new Promise(r => setTimeout(r, 20));
  assert.ok(activeFetchUrl.includes('min_premium=1000000'), 'API request must include updated min_premium=1000000');
  console.log('  ✓ PASS: Hurdle filter switching dynamically queries the backend\n');

  // --- TEST 7: Empty State & Network Resilience ---
  console.log('--- TEST 7: Empty State & Network Resilience ---');
  // 7a: Empty state
  customFetchHandler = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ status: 'ok', count: 0, clusters: [] })
  });
  await view.loadThematicClusters();
  const emptyEl = clustersContainer.querySelector('.flow-empty-state');
  assert.ok(emptyEl, 'Empty state element must render when no clusters match');
  assert.ok(emptyEl.textContent.includes('No multi-ticker thematic clusters detected'), 'Empty message must explain capital hurdle');

  // 7b: Network error resilience
  customFetchHandler = async () => ({
    ok: false,
    status: 500
  });
  await view.loadThematicClusters();
  const errorEl = clustersContainer.querySelector('.flow-empty-state.error');
  assert.ok(errorEl, 'Error state element must render gracefully on HTTP 500');
  console.log('  ✓ PASS: Empty and error states handled with zero runtime exceptions\n');

  console.log('==================================================================');
  console.log('  ALL THEMATIC FLOW CLUSTERS TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
}

runTests().catch(err => {
  console.error('\n❌ TEST FAILURE:', err);
  process.exit(1);
});
