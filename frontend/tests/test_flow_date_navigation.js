import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Flow Tab Date Navigation & Session Stepper
 */

console.log('==================================================================');
console.log('  PROBING FLOW TAB HISTORICAL DATE NAVIGATION & STEPPER           ');
console.log('==================================================================\n');

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
  return true;
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  const parts = selector.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return false;
  if (parts.length === 1) return matchesSingle(el, parts[0]);
  if (!matchesSingle(el, parts[parts.length - 1])) return false;
  return true;
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
    this.disabled = false;
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
    const ownText = this._textParts.join('');
    const childText = this.children.map(c => c.textContent).join('');
    return (ownText + (childText ? ' ' + childText : '')).trim();
  }
  set textContent(val) {
    this._innerHTML = String(val);
    this.children = [];
    this._textParts = [String(val)];
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

  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }

  click() {
    if (this.listeners['click']) {
      this.listeners['click'].forEach(fn => fn({ target: this }));
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
}

// Global browser mocks
global.window = {
  location: { origin: 'http://192.168.1.68:8096' }
};
global.localStorage = {
  getItem: () => 'mock-jwt-token',
  setItem: () => {},
  removeItem: () => {}
};

const fetchedUrls = [];
global.fetch = async (url) => {
  fetchedUrls.push(url);
  if (url.includes('/api/flow/aggregate')) {
    const isHistorical = url.includes('2026-09-30') || url.includes('2026-09-29');
    const targetDate = url.includes('2026-09-29') ? '2026-09-29' : (url.includes('2026-09-30') ? '2026-09-30' : '2026-10-01');
    return {
      ok: true,
      status: 200,
      json: async () => ({
        as_of_date: targetDate,
        latest_market_day: '2026-10-01',
        available_dates: ['2026-10-01', '2026-09-30', '2026-09-29'],
        synthesis_markdown: '### Thesis\nNotable flow found.',
        window_3d: {
          market_dates: isHistorical ? [targetDate, '2026-09-29', '2026-09-28'] : ['2026-10-01', '2026-09-30', '2026-09-29'],
          top_premium_bullish: [{ rank: 1, symbol: 'NVDA', formatted_premium: '$10M', contract_count: 50, active_days: 3 }],
          top_hits_bullish: [],
          top_premium_bearish: [],
          top_hits_bearish: []
        },
        window_1w: {
          market_dates: [],
          top_premium_bullish: [],
          top_hits_bullish: [],
          top_premium_bearish: [],
          top_hits_bearish: []
        }
      })
    };
  }
  if (url.includes('/api/flow/thematic-clusters')) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ok',
        count: 1,
        clusters: [
          { theme: 'Semiconductors', count: 2, total_premium: 5000000, symbols: ['NVDA', 'AMD'] }
        ]
      })
    };
  }
  if (url.includes('/api/flow/synthesis/stream')) {
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => ({ done: true, value: new Uint8Array() })
        })
      }
    };
  }
  return { ok: false, status: 404 };
};

const { FlowView } = await import('../src/tabs/flow_view.js');

const container = new MockElement('div');
const flowView = new FlowView();
flowView.render(container);

// Helper element finders inside container
const stepper = container.querySelector('#flowSessionStepper');
assert(stepper !== null, 'Session stepper container must be rendered');

const prevBtn = container.querySelector('#flowPrevBtn');
assert(prevBtn !== null, 'Prev session button must be rendered');

const nextBtn = container.querySelector('#flowNextBtn');
assert(nextBtn !== null, 'Next session button must be rendered');

const dateSelect = container.querySelector('#flowDateSelect');
assert(dateSelect !== null, 'Date select dropdown must be rendered');

console.log('--- TEST 1: Controls Mounting ---');
console.log('  ✓ PASS: Stepper group (#flowSessionStepper), buttons, and select mounted in DOM');

// TEST 2: Initial Data Load and Available Dates Resolution
console.log('\n--- TEST 2: Initial Data Load & Date State ---');
while (flowView.isLoading) {
  await new Promise(r => setTimeout(r, 10));
}
assert.strictEqual(flowView.selectedDate, '2026-10-01', 'Initial selectedDate should be resolved to latest date');
assert.deepStrictEqual(flowView.availableDates, ['2026-10-01', '2026-09-30', '2026-09-29'], 'Available dates parsed correctly');
assert.strictEqual(nextBtn.disabled, true, 'Next button disabled on latest session');
assert.strictEqual(prevBtn.disabled, false, 'Prev button enabled when older sessions exist');
assert(dateSelect.innerHTML.includes('2026-10-01 (LATEST)'), 'Latest session has LATEST badge in dropdown');
console.log('  ✓ PASS: Initial aggregate populates availableDates and properly disables Next ► at latest date');

// TEST 3: Step to Previous Session
console.log('\n--- TEST 3: Step to Previous Session (Older) ---');
flowView.stepSession(-1);
while (flowView.isLoading) {
  await new Promise(r => setTimeout(r, 10));
}
assert.strictEqual(flowView.selectedDate, '2026-09-30', 'Selected date stepped backward to 2026-09-30');
assert.strictEqual(nextBtn.disabled, false, 'Next button enabled when not at latest session');
assert(fetchedUrls.some(u => u.includes('as_of_date=2026-09-30')), 'API request dispatched with as_of_date=2026-09-30');
console.log('  ✓ PASS: ◄ Prev button advances index, enables Next ►, and triggers historical aggregate fetch');

// TEST 4: Step Forward Back to Latest Session
console.log('\n--- TEST 4: Step Forward to Newer Session ---');
flowView.stepSession(1);
while (flowView.isLoading) {
  await new Promise(r => setTimeout(r, 10));
}
assert.strictEqual(flowView.selectedDate, '2026-10-01', 'Selected date stepped forward back to 2026-10-01');
assert.strictEqual(nextBtn.disabled, true, 'Next button disabled at latest session');
assert(fetchedUrls.some(u => u.includes('as_of_date=2026-10-01')), 'API request dispatched with as_of_date=2026-10-01');
console.log('  ✓ PASS: Next ► button navigates to newer session and re-disables at latest date');

// TEST 5: Select Session from Dropdown
console.log('\n--- TEST 5: Dropdown Selection ---');
flowView.onDateSelectChange('2026-09-29');
while (flowView.isLoading) {
  await new Promise(r => setTimeout(r, 10));
}
assert.strictEqual(flowView.selectedDate, '2026-09-29', 'selectedDate updated from dropdown change');
assert.strictEqual(prevBtn.disabled, true, 'Prev button disabled at oldest session (boundary check)');
assert.strictEqual(nextBtn.disabled, false, 'Next button enabled');
assert(fetchedUrls.some(u => u.includes('as_of_date=2026-09-29')), 'API request dispatched with as_of_date=2026-09-29');
console.log('  ✓ PASS: Dropdown selection updates active date and disables ◄ Prev at oldest session');

// TEST 6: Thematic Clusters Trade Date Synchronization
console.log('\n--- TEST 6: Thematic Clusters Date Propagation ---');
flowView.activeViewMode = 'clusters';
await flowView.loadThematicClusters();
assert(fetchedUrls.some(u => u.includes('/api/flow/thematic-clusters') && u.includes('trade_date=2026-09-29')), 'Thematic clusters endpoint receives trade_date parameter');
console.log('  ✓ PASS: Thematic clusters query propagates active selectedDate parameter');

console.log('\n==================================================================');
console.log('  ALL FLOW DATE NAVIGATION TESTS PASSED (100% GREEN)             ');
console.log('==================================================================');
