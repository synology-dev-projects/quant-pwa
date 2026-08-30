/**
 * Automated Test Probe for Auth Guard, fetchWithAuth 401 Interceptor & Tab Navigation Guard (AUTH-01)
 *
 * Tests:
 * 1. fetchWithAuth injects Authorization: Bearer <token> when session token is present.
 * 2. fetchWithAuth handles 401 Unauthorized:
 *    - Clears AppState session.
 *    - Dispatches global 'quant-session-expired' window CustomEvent.
 *    - Notifies AppState.onSessionExpired callbacks.
 *    - Throws new Error('SessionExpired: 401 Unauthorized').
 * 3. Tab navigation guard in TabManager:
 *    - Allows switching tabs when session is valid.
 *    - Blocks tab switching when AppState.isSessionExpired() is true.
 *    - Fires 'quant-session-expired' event upon blocked tab change attempt.
 * 4. LockScreen auto-displays on 'quant-session-expired' event and AppState.onSessionExpired callback.
 * 5. LockScreen onAuthenticated callback reloads state upon successful unlock.
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
  }

  get textContent() {
    return this._innerHTML;
  }
  set textContent(val) {
    this._innerHTML = String(val);
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
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
    const handlers = (this.listeners[evt?.type || 'click'] || []).slice();
    for (const h of handlers) {
      h(evt);
    }
  }

  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }

  querySelectorAll(sel) {
    const results = [];
    const match = (el) => {
      if (sel.startsWith('#') && el.id === sel.slice(1)) results.push(el);
      else if (sel.startsWith('.') && el.classList.contains(sel.slice(1))) results.push(el);
      else if (el.tagName.toLowerCase() === sel.toLowerCase()) results.push(el);
      for (const ch of el.children) match(ch);
    };
    for (const ch of this.children) match(ch);
    return results;
  }

  focus() {}
}

class MockDocument {
  constructor() {
    this.body = new MockElement('BODY');
    this._elementsById = new Map();
  }
  createElement(tagName) {
    return new MockElement(tagName);
  }
  getElementById(id) {
    return this._elementsById.get(id) || this.body.querySelector(`#${id}`);
  }
  registerElement(id, el) {
    el.id = id;
    this._elementsById.set(id, el);
  }
}

// Global browser env setup
global.document = new MockDocument();
const globalListeners = {};

global.window = {
  document: global.document,
  devicePixelRatio: 2,
  requestAnimationFrame: (cb) => setImmediate(cb),
  addEventListener: (type, cb) => {
    if (!globalListeners[type]) globalListeners[type] = [];
    globalListeners[type].push(cb);
  },
  removeEventListener: (type, cb) => {
    if (globalListeners[type]) {
      globalListeners[type] = globalListeners[type].filter(h => h !== cb);
    }
  },
  dispatchEvent: (evt) => {
    const type = evt?.type || 'custom';
    const handlers = (globalListeners[type] || []).slice();
    for (const h of handlers) {
      h(evt);
    }
  },
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
global.CustomEvent = class {
  constructor(type, detail) {
    this.type = type;
    this.detail = detail;
  }
};

// ============================================================================
// 2. Import Components under Test
// ============================================================================
const { AppState, fetchWithAuth } = await import('../src/state.js');
const { TabManager } = await import('../src/tabs/tab_manager.js');
const { LockScreen } = await import('../src/components/lock_screen.js');

// ============================================================================
// 3. Test Runner
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
console.log('  PROBING AUTH GUARD, 401 INTERCEPTOR & TAB NAVIGATION GUARD (AUTH-01)');
console.log('==================================================================\n');

// ----------------------------------------------------------------------------
// TEST 1: fetchWithAuth Injects Bearer Header
// ----------------------------------------------------------------------------
console.log('--- TEST 1: fetchWithAuth Injects Bearer Header ---');

let interceptedHeaders = null;
global.fetch = async (url, options = {}) => {
  interceptedHeaders = options.headers || {};
  return {
    status: 200,
    ok: true,
    json: async () => ({ status: 'ok' })
  };
};

AppState.setSessionToken('mock-auth-token-12345', Math.floor(Date.now() / 1000) + 3600);
assert(AppState.getSessionToken() === 'mock-auth-token-12345', 'AppState session token set properly');

await fetchWithAuth('http://localhost:8000/api/test', {
  headers: { 'Content-Type': 'application/json' }
});

assert(interceptedHeaders['Authorization'] === 'Bearer mock-auth-token-12345', 'fetchWithAuth injected Authorization Bearer header into request');

// ----------------------------------------------------------------------------
// TEST 2: fetchWithAuth Handles 401 Unauthorized
// ----------------------------------------------------------------------------
console.log('\n--- TEST 2: fetchWithAuth 401 Interceptor & Session Expiry ---');

let eventFired = false;
window.addEventListener('quant-session-expired', () => {
  eventFired = true;
});

let callbackFired = false;
const unsubscribe = AppState.onSessionExpired(() => {
  callbackFired = true;
});

global.fetch = async () => {
  return {
    status: 401,
    ok: false,
    json: async () => ({ detail: 'Token expired' })
  };
};

let threwError = false;
try {
  await fetchWithAuth('http://localhost:8000/api/protected');
} catch (err) {
  threwError = true;
  assert(err.message.includes('SessionExpired') && err.message.includes('401'), `Error thrown with SessionExpired: "${err.message}"`);
}

assert(threwError, 'fetchWithAuth threw an exception on 401');
assert(AppState.getSessionToken() === '', 'AppState session token was cleared on 401');
assert(eventFired, 'Global quant-session-expired CustomEvent was dispatched on window');
assert(callbackFired, 'AppState.onSessionExpired subscriber was notified');

unsubscribe();

// ----------------------------------------------------------------------------
// TEST 3: Tab Navigation Guard
// ----------------------------------------------------------------------------
console.log('\n--- TEST 3: Tab Navigation Guard ---');

const tabBarContainer = new MockElement('DIV');
const contentContainer = new MockElement('DIV');

let currentActiveTabCallback = null;
const tabManager = new TabManager(tabBarContainer, contentContainer, (tabId) => {
  currentActiveTabCallback = tabId;
});

tabManager.registerTab({
  id: 'chat',
  title: 'Chat',
  render: (pane) => { pane.innerHTML = '<div id="chat-content">Chat Pane</div>'; }
});

tabManager.registerTab({
  id: 'cockpit',
  title: 'Cockpit',
  render: (pane) => { pane.innerHTML = '<div id="cockpit-content">Cockpit Pane</div>'; }
});

// Part A: Switch when authenticated
AppState.setSessionToken('valid-session-token', Math.floor(Date.now() / 1000) + 3600);
assert(!AppState.isSessionExpired(), 'Session is currently valid');

tabManager.switchTab('chat');
assert(tabManager.activeTabId === 'chat', 'Initial tab set to chat when authenticated');

tabManager.switchTab('cockpit');
assert(tabManager.activeTabId === 'cockpit', 'Switched to cockpit tab successfully when authenticated');
assert(currentActiveTabCallback === 'cockpit', 'Tab change callback fired with "cockpit"');

// Part B: Attempt switch when session is expired
AppState.clearSession();
assert(AppState.isSessionExpired(), 'Session is now expired');

let guardEventFired = false;
window.addEventListener('quant-session-expired', () => {
  guardEventFired = true;
});

currentActiveTabCallback = null;
tabManager.switchTab('chat');

assert(guardEventFired, 'Navigation guard dispatched quant-session-expired event');
assert(tabManager.activeTabId === 'cockpit', 'Navigation guard blocked tab switch (activeTab remains cockpit)');
assert(currentActiveTabCallback === null, 'Tab change callback was NOT called during blocked switch');

// ----------------------------------------------------------------------------
// TEST 4: LockScreen Reactivity to Session Expiration
// ----------------------------------------------------------------------------
console.log('\n--- TEST 4: LockScreen Reactivity ---');

const lockOverlay = new MockElement('DIV');
lockOverlay.classList.add('hidden');
document.registerElement('lockScreen', lockOverlay);

const lockForm = new MockElement('FORM');
document.registerElement('lockForm', lockForm);

const lockPassInput = new MockElement('INPUT');
document.registerElement('lockPasswordInput', lockPassInput);

const lockSubmitBtn = new MockElement('BUTTON');
document.registerElement('lockSubmitBtn', lockSubmitBtn);

const lockErrorMsg = new MockElement('DIV');
document.registerElement('lockErrorMsg', lockErrorMsg);

const lockCard = new MockElement('DIV');
document.registerElement('lockCard', lockCard);

let authenticatedCalled = false;
const lockScreen = new LockScreen(() => {
  authenticatedCalled = true;
});

assert(lockOverlay.classList.contains('hidden'), 'Lock screen initially hidden');

// Trigger session expired event
window.dispatchEvent(new CustomEvent('quant-session-expired'));

assert(lockOverlay.classList.contains('visible'), 'Lock screen added "visible" class upon quant-session-expired');
assert(!lockOverlay.classList.contains('hidden'), 'Lock screen removed "hidden" class upon quant-session-expired');

// Test successful unlock invokes onAuthenticated
lockScreen.unlock(true);
assert(authenticatedCalled, 'LockScreen.unlock() triggered onAuthenticated callback');
assert(!lockOverlay.classList.contains('visible'), 'Lock screen removed "visible" class upon unlock');
assert(lockOverlay.classList.contains('hidden'), 'Lock screen added "hidden" class upon unlock');

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
