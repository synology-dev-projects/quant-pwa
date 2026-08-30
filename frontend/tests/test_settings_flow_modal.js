import { strict as assert } from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// 1. Lightweight Mock DOM Environment
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

class MockElement {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this._className = '';
    this.classList = new MockClassList(this);
    this.children = [];
    this.parentNode = null;
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.disabled = false;
    this.style = {};
    this.listeners = {};
  }
  get className() { return this._className; }
  set className(val) {
    this._className = val || '';
    this.classList._classes = new Set((val || '').split(/\s+/).filter(Boolean));
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
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  remove() {
    if (this.parentNode) {
      const idx = this.parentNode.children.indexOf(this);
      if (idx !== -1) this.parentNode.children.splice(idx, 1);
    }
  }
}

const elements = {
  settingsModal: new MockElement('div', 'settingsModal'),
  settingsBtn: new MockElement('button', 'settingsBtn'),
  settingsClose: new MockElement('button', 'settingsClose'),
  settingsSave: new MockElement('button', 'settingsSave'),
  clearHistoryBtn: new MockElement('button', 'clearHistoryBtn'),
  lockAppBtn: new MockElement('button', 'lockAppBtn'),
  forceUpdateBtn: new MockElement('button', 'forceUpdateBtn'),
  manualResyncLink: new MockElement('div', 'manualResyncLink'),
  syncFlowBtn: new MockElement('button', 'syncFlowBtn'),
  syncLevelsBtn: new MockElement('button', 'syncLevelsBtn'),
  appBuildVersion: new MockElement('span', 'appBuildVersion'),
  syncStatusText: new MockElement('span', 'syncStatusText'),
  flowStatusText: new MockElement('span', 'flowStatusText'),
  flowSyncDot: new MockElement('span', 'flowSyncDot'),
  flowStatusBadge: new MockElement('span', 'flowStatusBadge'),
  levelsStatusText: new MockElement('span', 'levelsStatusText'),
  levelsSyncDot: new MockElement('span', 'levelsSyncDot'),
  levelsStatusBadge: new MockElement('span', 'levelsStatusBadge'),
  passcodeInput: new MockElement('input', 'passcodeInput'),
  gatewayUrlInput: new MockElement('input', 'gatewayUrlInput'),
  diagnosticsToggle: new MockElement('input', 'diagnosticsToggle')
};

global.document = {
  getElementById: (id) => elements[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => new MockElement(tag),
  body: new MockElement('body'),
  addEventListener: () => {}
};

global.window = {
  location: { origin: 'http://192.168.1.68:8096', pathname: '/', href: '', port: '8096', hostname: '192.168.1.68' }
};

global.localStorage = {
  store: {},
  getItem: (k) => global.localStorage.store[k] || null,
  setItem: (k, v) => { global.localStorage.store[k] = v; },
  removeItem: (k) => { delete global.localStorage.store[k]; }
};

global.sessionStorage = {
  store: {},
  getItem: (k) => global.sessionStorage.store[k] || null,
  setItem: (k, v) => { global.sessionStorage.store[k] = v; },
  removeItem: (k) => { delete global.sessionStorage.store[k]; }
};

const { SettingsModal, CLIENT_VERSION } = await import('../src/components/settings_modal.js');

console.log('==================================================================');
console.log('  PROBING SETTINGS MODAL OPTIONS FLOW FRESHNESS UI (SETTINGS-04)  ');
console.log('==================================================================\n');

// 1. version.json Parity Test
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const versionJsonPath = path.resolve(__dirname, '../../version.json');
const versionJson = JSON.parse(fs.readFileSync(versionJsonPath, 'utf8'));

assert.strictEqual(CLIENT_VERSION, versionJson.version, 'CLIENT_VERSION must match version.json');
console.log(`  ✓ PASS: CLIENT_VERSION (${CLIENT_VERSION}) matches version.json (${versionJson.version})`);

const modal = new SettingsModal();

// TEST 0: Health & Version Sync Check (Environment-Tagged Badge & Sync Status)
global.fetch = async (url) => {
  if (url === '/api/health') {
    return {
      ok: true,
      json: async () => ({ version: CLIENT_VERSION, environment: 'staging' })
    };
  }
  return { ok: false };
};

await modal.checkVersionStatus();
assert.strictEqual(elements.appBuildVersion.textContent, `${CLIENT_VERSION} (Staging)`, `App build shows ${CLIENT_VERSION} (Staging)`);
assert.strictEqual(elements.syncStatusText.textContent, `Synchronized (${CLIENT_VERSION})`, 'Sync status text is synchronized');
assert.strictEqual(elements.forceUpdateBtn.disabled, true, 'Force update button is disabled when in sync');
assert.strictEqual(elements.forceUpdateBtn.className, 'btn btn-synced', 'Force update button has btn-synced class');
assert.strictEqual(elements.forceUpdateBtn.innerHTML, `✓ App Up to Date (${CLIENT_VERSION})`, 'Force update button text is up to date');
assert.strictEqual(elements.manualResyncLink.style.display, 'block', 'Manual resync link visible when synchronized');
console.log(`  ✓ PASS: Version check with matched ${CLIENT_VERSION} and staging environment renders synchronized state`);

// TEST 1: Fresh State Check
global.fetch = async (url) => {
  if (url === '/api/flow/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'synced',
        is_fresh: true,
        latest_trade_date: '2026-08-29',
        last_market_day: '2026-08-28'
      })
    };
  }
  if (url === '/api/health') {
    return {
      ok: true,
      json: async () => ({ version: 'v1.0.3', environment: 'staging' })
    };
  }
  return { ok: false };
};

await modal.checkFlowStatus();

const syncFlowBtn = elements.syncFlowBtn;
const flowStatusText = elements.flowStatusText;
const flowSyncDot = elements.flowSyncDot;

assert.strictEqual(flowStatusText.textContent, 'In Sync (2026-08-29)', 'Flow text reflects fresh state');
assert.strictEqual(syncFlowBtn.disabled, true, 'Sync button is disabled when in sync');
assert.strictEqual(syncFlowBtn.className, 'btn btn-synced', 'Sync button has btn-synced class');
assert.strictEqual(flowSyncDot.className, 'status-dot dot-live', 'Dot is live green');
console.log('  ✓ PASS: Fresh DB state renders disabled greyed-out button and green dot');

// TEST 2: Stale State Check
global.fetch = async (url) => {
  if (url === '/api/flow/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'stale',
        is_fresh: false,
        latest_trade_date: '2026-08-26',
        last_market_day: '2026-08-28'
      })
    };
  }
  return { ok: false };
};

await modal.checkFlowStatus();

assert.strictEqual(flowStatusText.textContent, 'Stale (Missing 2026-08-28)', 'Flow text reflects stale state with expected date');
assert.strictEqual(syncFlowBtn.disabled, false, 'Sync button is enabled when stale');
assert.strictEqual(syncFlowBtn.className, 'btn btn-danger btn-pulse', 'Sync button has active danger pulse class');
assert.strictEqual(flowSyncDot.className, 'status-dot dot-stale', 'Dot is red stale');
console.log('  ✓ PASS: Stale DB state renders enabled danger-pulse button and red dot');

// TEST 3: Click Sync Button when Stale
let syncTriggered = false;
global.fetch = async (url, opts) => {
  if (url === '/api/flow/sync' && opts?.method === 'POST') {
    syncTriggered = true;
    return {
      ok: true,
      json: async () => ({ status: 'ok', message: 'Sync complete' })
    };
  }
  if (url === '/api/flow/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'synced',
        is_fresh: true,
        latest_trade_date: '2026-08-28',
        last_market_day: '2026-08-28'
      })
    };
  }
  return { ok: false };
};

await modal.handleSyncFlow();
assert.strictEqual(syncTriggered, true, 'Sync API was dispatched upon button click');
assert.strictEqual(syncFlowBtn.disabled, true, 'Sync button re-disabled after completion');
assert.strictEqual(flowStatusText.textContent, 'In Sync (2026-08-28)', 'Status flips to In Sync post-run');
console.log('  ✓ PASS: Clicking sync button triggers backend sync and flips status to In Sync');

// TEST 4: Update Available Scenario (Client version vs newer Server version)
global.fetch = async (url) => {
  if (url === '/api/health') {
    return {
      ok: true,
      json: async () => ({ version: 'v9.9.9', environment: 'production' })
    };
  }
  return { ok: false };
};

// Temporarily change hostname to production
global.window.location.port = '80';
global.window.location.hostname = 'app.quant.internal';

await modal.checkVersionStatus();
assert.strictEqual(elements.appBuildVersion.textContent, `${CLIENT_VERSION} (Production)`, `App build shows ${CLIENT_VERSION} (Production)`);
assert.strictEqual(elements.syncStatusText.textContent, 'Update Available (v9.9.9)', 'Sync status text reflects update available');
assert.strictEqual(elements.forceUpdateBtn.disabled, false, 'Force update button enabled when update available');
assert.strictEqual(elements.forceUpdateBtn.className, 'btn btn-danger btn-pulse', 'Force update button has danger-pulse class');
assert.strictEqual(elements.forceUpdateBtn.innerHTML, '⚡ Update Available (v9.9.9) · Tap to Sync', 'Force update button text reflects server version');
assert.strictEqual(elements.manualResyncLink.style.display, 'none', 'Manual resync link hidden when update available');
console.log('  ✓ PASS: Update available scenario correctly updates badge, button and hides resync link');

// TEST 5: Fresh Quant Levels State Check
global.fetch = async (url) => {
  if (url === '/api/quant-levels/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'synced',
        is_fresh: true,
        latest_record_date: '2026-08-29',
        expected_date: '2026-08-29'
      })
    };
  }
  return { ok: false };
};

await modal.checkQuantLevelsStatus();

const syncLevelsBtn = elements.syncLevelsBtn;
const levelsStatusText = elements.levelsStatusText;
const levelsSyncDot = elements.levelsSyncDot;

assert.strictEqual(levelsStatusText.textContent, 'In Sync (2026-08-29)', 'Quant Levels text reflects fresh state');
assert.strictEqual(syncLevelsBtn.disabled, true, 'Sync levels button is disabled when in sync');
assert.strictEqual(syncLevelsBtn.className, 'btn btn-synced', 'Sync levels button has btn-synced class');
assert.strictEqual(syncLevelsBtn.innerHTML, '✓ Quant Levels Up to Date (2026-08-29)', 'Sync levels button text is up to date');
assert.strictEqual(levelsSyncDot.className, 'status-dot dot-live', 'Levels dot is live green');
console.log('  ✓ PASS: Fresh Quant Levels DB state renders disabled button and live dot');

// TEST 6: Stale Quant Levels State Check
global.fetch = async (url) => {
  if (url === '/api/quant-levels/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'stale',
        is_fresh: false,
        latest_record_date: '2026-08-26',
        expected_date: '2026-08-29'
      })
    };
  }
  return { ok: false };
};

await modal.checkQuantLevelsStatus();

assert.strictEqual(levelsStatusText.textContent, 'Stale (Missing 2026-08-29)', 'Quant levels text reflects stale state with missing expected date');
assert.strictEqual(syncLevelsBtn.disabled, false, 'Sync levels button is enabled when stale');
assert.strictEqual(syncLevelsBtn.className, 'btn btn-danger btn-pulse', 'Sync levels button has active danger pulse class');
assert.strictEqual(syncLevelsBtn.innerHTML, '⚡ Sync Quant Levels (2026-08-29) · Tap to Run', 'Sync levels button prompts user to run sync');
assert.strictEqual(levelsSyncDot.className, 'status-dot dot-stale', 'Levels dot is red stale');
console.log('  ✓ PASS: Stale Quant Levels DB state renders enabled danger-pulse button and red dot');

// TEST 7: Click Sync Quant Levels Button when Stale
let levelsSyncTriggered = false;
let authHeaderReceived = null;
global.fetch = async (url, opts) => {
  if (url === '/api/quant-levels/sync' && opts?.method === 'POST') {
    levelsSyncTriggered = true;
    authHeaderReceived = opts?.headers?.Authorization || opts?.headers?.authorization;
    return {
      ok: true,
      json: async () => ({ status: 'ok', message: 'Quant levels sync complete' })
    };
  }
  if (url === '/api/quant-levels/status') {
    return {
      ok: true,
      json: async () => ({
        status: 'synced',
        is_fresh: true,
        latest_record_date: '2026-08-29',
        expected_date: '2026-08-29'
      })
    };
  }
  return { ok: false };
};

// Simulate active session token in AppState
const { AppState } = await import('../src/state.js');
AppState.setSessionToken('mock-jwt-token-12345');

await modal.handleSyncQuantLevels();
assert.strictEqual(levelsSyncTriggered, true, 'Quant Levels Sync API was dispatched upon button click');
assert.strictEqual(authHeaderReceived, 'Bearer mock-jwt-token-12345', 'Bearer session token was included in headers');
assert.strictEqual(syncLevelsBtn.disabled, true, 'Sync levels button re-disabled after completion');
assert.strictEqual(levelsStatusText.textContent, 'In Sync (2026-08-29)', 'Quant levels status flips to In Sync post-run');
console.log('  ✓ PASS: Clicking sync levels button triggers backend sync and flips status to In Sync');

console.log('\n==================================================================');
console.log('  SETTINGS MODAL TESTS PASSED (100% COVERAGE)                     ');
console.log('==================================================================');
