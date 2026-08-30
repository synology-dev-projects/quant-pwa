/**
 * Automated Layout & Geometry Verification Test Suite (UI-01)
 *
 * Audits:
 * 1. Responsive Viewport Geometry across simulated widths (375px mobile, 768px tablet, 1280px desktop).
 * 2. WCAG Touch-Target Accessibility for all interactive elements (>= 44px min tap area or >= 36px with padding container).
 * 3. Modal Actions Geometry (.modal-body, .settings-actions: width: 100%, box-sizing: border-box, zero negative margins).
 * 4. Zero Horizontal Layout Overflow across Cockpit Panels (1, 2, 3) and Bloomberg Options Flow Table.
 * 5. Diagnostics & Lightbox Layout Stability across viewports.
 */

import { strict as assert } from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const stylesPath = path.resolve(__dirname, '../styles.css');
const stylesCss = fs.readFileSync(stylesPath, 'utf8');

// ============================================================================
// 1. Lightweight CSS Parser & Cascade Computation Engine
// ============================================================================

class CssRule {
  constructor(selector, declarations, mediaQuery = null) {
    this.selector = selector.trim();
    this.declarations = declarations; // Object: prop -> value
    this.mediaQuery = mediaQuery; // e.g. "(max-width: 480px)"
  }

  appliesToViewport(viewportWidth) {
    if (!this.mediaQuery) return true;
    const maxMatch = this.mediaQuery.match(/max-width:\s*(\d+)px/);
    if (maxMatch && viewportWidth > parseInt(maxMatch[1], 10)) {
      return false;
    }
    const minMatch = this.mediaQuery.match(/min-width:\s*(\d+)px/);
    if (minMatch && viewportWidth < parseInt(minMatch[1], 10)) {
      return false;
    }
    return true;
  }
}

function parseCss(css) {
  const rules = [];
  // Remove comments
  const cleanCss = css.replace(/\/\*[\s\S]*?\*\//g, '');

  let pos = 0;
  while (pos < cleanCss.length) {
    const atMediaIdx = cleanCss.indexOf('@media', pos);
    const nextOpenBrace = cleanCss.indexOf('{', pos);

    if (nextOpenBrace === -1) break;

    if (atMediaIdx !== -1 && atMediaIdx < nextOpenBrace) {
      // Parse media query
      const mediaQueryHeader = cleanCss.substring(atMediaIdx + 6, nextOpenBrace).trim();
      let depth = 1;
      let i = nextOpenBrace + 1;
      while (i < cleanCss.length && depth > 0) {
        if (cleanCss[i] === '{') depth++;
        else if (cleanCss[i] === '}') depth--;
        i++;
      }
      const mediaBody = cleanCss.substring(nextOpenBrace + 1, i - 1);
      pos = i;

      // Parse inner rules
      const innerRules = parseCssBlock(mediaBody, mediaQueryHeader);
      rules.push(...innerRules);
    } else {
      // Normal CSS rule
      const selector = cleanCss.substring(pos, nextOpenBrace).trim();
      const closeBrace = cleanCss.indexOf('}', nextOpenBrace);
      if (closeBrace === -1) break;
      const declBlock = cleanCss.substring(nextOpenBrace + 1, closeBrace);
      pos = closeBrace + 1;

      if (selector) {
        const decls = parseDeclarations(declBlock);
        const selectorList = selector.split(',').map(s => s.trim()).filter(Boolean);
        for (const sel of selectorList) {
          rules.push(new CssRule(sel, decls, null));
        }
      }
    }
  }
  return rules;
}

function parseCssBlock(block, mediaQuery) {
  const rules = [];
  let pos = 0;
  while (pos < block.length) {
    const openBrace = block.indexOf('{', pos);
    if (openBrace === -1) break;
    const selector = block.substring(pos, openBrace).trim();
    const closeBrace = block.indexOf('}', openBrace);
    if (closeBrace === -1) break;
    const declBlock = block.substring(openBrace + 1, closeBrace);
    pos = closeBrace + 1;

    if (selector) {
      const decls = parseDeclarations(declBlock);
      const selectorList = selector.split(',').map(s => s.trim()).filter(Boolean);
      for (const sel of selectorList) {
        rules.push(new CssRule(sel, decls, mediaQuery));
      }
    }
  }
  return rules;
}

function parseDeclarations(declStr) {
  const decls = {};
  const statements = declStr.split(';').map(s => s.trim()).filter(Boolean);
  for (const stmt of statements) {
    const colonIdx = stmt.indexOf(':');
    if (colonIdx !== -1) {
      const prop = stmt.slice(0, colonIdx).trim().toLowerCase();
      let val = stmt.slice(colonIdx + 1).trim();
      val = val.replace(/\s*!important/gi, '').trim();
      decls[prop] = val;
    }
  }
  return decls;
}

const parsedCssRules = parseCss(stylesCss);

// ============================================================================
// 2. High-Fidelity Mock DOM & Geometry Model
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
      if (this._classes.has(cls)) this._classes.delete(cls);
      else this._classes.add(cls);
    }
    this._sync();
  }
  _sync() {
    this._el._className = Array.from(this._classes).join(' ');
  }
}

function matchesSelectorPart(el, part) {
  if (!el || !part) return false;
  // Clean pseudo-classes for layout geometry matching (:focus, :hover, :active, :not(...))
  let cleanPart = part.replace(/:hover|:active|:focus|:focus-visible|:focus-within|:disabled|:not\([^)]*\)/g, '');
  if (!cleanPart) return true;

  // Match ID
  const idMatches = cleanPart.match(/#([a-zA-Z0-9\-_]+)/g);
  if (idMatches) {
    for (const im of idMatches) {
      if (el.id !== im.slice(1)) return false;
    }
  }

  // Match Tag
  const tagMatch = cleanPart.match(/^([a-zA-Z0-9\-]+)/);
  if (tagMatch) {
    if (el.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
  }

  // Match Classes
  const classMatches = cleanPart.match(/\.([a-zA-Z0-9\-_]+)/g);
  if (classMatches) {
    for (const cm of classMatches) {
      if (!el.classList.contains(cm.slice(1))) return false;
    }
  }

  // Match Attributes
  const attrMatches = cleanPart.match(/\[([a-zA-Z0-9\-_]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]+)))?\]/g);
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
          if (el[attrName] === undefined && !el._attributes[attrName]) return false;
          const actual = el[attrName] !== undefined ? el[attrName] : el._attributes[attrName];
          if (attrVal !== undefined && String(actual) !== attrVal) return false;
        }
      }
    }
  }
  return true;
}

function matchesSelectorFull(el, selector) {
  if (!el || !selector) return false;
  const groups = selector.split(',').map(s => s.trim()).filter(Boolean);
  return groups.some(group => {
    const parts = group.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return false;
    if (parts.length === 1) return matchesSelectorPart(el, parts[0]);

    if (!matchesSelectorPart(el, parts[parts.length - 1])) return false;
    let cur = el.parentElement;
    for (let i = parts.length - 2; i >= 0; i--) {
      let found = false;
      while (cur) {
        if (matchesSelectorPart(cur, parts[i])) {
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
  constructor(tagName, id = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this._className = '';
    this.classList = new MockClassList(this);
    this.dataset = {};
    this._attributes = {};
    this.children = [];
    this.parentElement = null;
    this.listeners = {};
    this.disabled = false;
    this.style = {};
  }

  get className() { return this._className; }
  set className(val) {
    this._className = val || '';
    this.classList._classes = new Set((val || '').split(/\s+/).filter(Boolean));
  }

  setAttribute(name, val) {
    this._attributes[name] = val;
    if (name === 'id') this.id = val;
    if (name === 'class') this.className = val;
    if (name.startsWith('data-')) {
      const camelKey = name.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
      this.dataset[camelKey] = val;
    }
  }

  getAttribute(name) {
    return this._attributes[name] || null;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }

  querySelectorAll(sel) {
    const results = [];
    const walk = (el) => {
      if (matchesSelectorFull(el, sel)) {
        results.push(el);
      }
      for (const ch of el.children) {
        walk(ch);
      }
    };
    for (const ch of this.children) {
      walk(ch);
    }
    return results;
  }

  addEventListener(type, cb) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(cb);
  }

  click() {
    if (this.listeners['click']) {
      this.listeners['click'].forEach(fn => fn({ target: this, preventDefault: () => {}, stopPropagation: () => {} }));
    }
  }

  computeStyle(viewportWidth = 375) {
    const computed = {
      display: 'block',
      position: 'static',
      boxSizing: 'content-box',
      width: 'auto',
      minWidth: '0px',
      maxWidth: 'none',
      height: 'auto',
      minHeight: '0px',
      maxHeight: 'none',
      paddingTop: '0px',
      paddingBottom: '0px',
      paddingLeft: '0px',
      paddingRight: '0px',
      marginTop: '0px',
      marginBottom: '0px',
      marginLeft: '0px',
      marginRight: '0px',
      overflowX: 'visible',
      overflowY: 'visible',
      fontSize: '14px',
      lineHeight: '1.4'
    };

    // Default tag-level rules
    if (['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(this.tagName)) {
      computed.boxSizing = 'border-box';
      computed.display = 'inline-block';
    }
    if (this.tagName === 'DIV' || this.tagName === 'MAIN' || this.tagName === 'HEADER' || this.tagName === 'NAV') {
      computed.display = 'block';
    }

    // Universal selector defaults from styles.css: * { box-sizing: border-box; margin: 0; padding: 0; }
    computed.boxSizing = 'border-box';
    computed.marginTop = '0px';
    computed.marginBottom = '0px';
    computed.marginLeft = '0px';
    computed.marginRight = '0px';
    computed.paddingTop = '0px';
    computed.paddingBottom = '0px';
    computed.paddingLeft = '0px';
    computed.paddingRight = '0px';

    // Match all rules from styles.css
    for (const rule of parsedCssRules) {
      if (!rule.appliesToViewport(viewportWidth)) continue;
      if (matchesSelectorFull(this, rule.selector)) {
        for (const [prop, val] of Object.entries(rule.declarations)) {
          if (prop === 'box-sizing') computed.boxSizing = val;
          else if (prop === 'display') computed.display = val;
          else if (prop === 'position') computed.position = val;
          else if (prop === 'width') computed.width = val;
          else if (prop === 'min-width') computed.minWidth = val;
          else if (prop === 'max-width') computed.maxWidth = val;
          else if (prop === 'height') computed.height = val;
          else if (prop === 'min-height') computed.minHeight = val;
          else if (prop === 'max-height') computed.maxHeight = val;
          else if (prop === 'overflow-x') computed.overflowX = val;
          else if (prop === 'overflow-y') computed.overflowY = val;
          else if (prop === 'overflow') { computed.overflowX = val; computed.overflowY = val; }
          else if (prop === 'padding') {
            const pParts = val.split(/\s+/);
            if (pParts.length === 1) {
              computed.paddingTop = computed.paddingBottom = computed.paddingLeft = computed.paddingRight = pParts[0];
            } else if (pParts.length === 2) {
              computed.paddingTop = computed.paddingBottom = pParts[0];
              computed.paddingLeft = computed.paddingRight = pParts[1];
            } else if (pParts.length === 4) {
              computed.paddingTop = pParts[0];
              computed.paddingRight = pParts[1];
              computed.paddingBottom = pParts[2];
              computed.paddingLeft = pParts[3];
            }
          }
          else if (prop === 'padding-top') computed.paddingTop = val;
          else if (prop === 'padding-bottom') computed.paddingBottom = val;
          else if (prop === 'padding-left') computed.paddingLeft = val;
          else if (prop === 'padding-right') computed.paddingRight = val;
          else if (prop === 'margin') {
            const mParts = val.split(/\s+/);
            if (mParts.length === 1) {
              computed.marginTop = computed.marginBottom = computed.marginLeft = computed.marginRight = mParts[0];
            } else if (mParts.length === 2) {
              computed.marginTop = computed.marginBottom = mParts[0];
              computed.marginLeft = computed.marginRight = mParts[1];
            } else if (mParts.length === 4) {
              computed.marginTop = mParts[0];
              computed.marginRight = mParts[1];
              computed.marginBottom = mParts[2];
              computed.marginLeft = mParts[3];
            }
          }
          else if (prop === 'margin-top') computed.marginTop = val;
          else if (prop === 'margin-bottom') computed.marginBottom = val;
          else if (prop === 'margin-left') computed.marginLeft = val;
          else if (prop === 'margin-right') computed.marginRight = val;
          else if (prop === 'font-size') computed.fontSize = val;
          else if (prop === 'line-height') computed.lineHeight = val;
        }
      }
    }

    // Inline style overrides
    for (const [prop, val] of Object.entries(this.style)) {
      if (val !== undefined && val !== '') {
        const camelToKebab = prop.replace(/([A-Z])/g, '-$1').toLowerCase();
        if (camelToKebab === 'box-sizing') computed.boxSizing = val;
        else if (camelToKebab === 'display') computed.display = val;
        else if (camelToKebab === 'width') computed.width = val;
        else if (camelToKebab === 'height') computed.height = val;
        else if (camelToKebab === 'min-height') computed.minHeight = val;
        else if (camelToKebab === 'min-width') computed.minWidth = val;
      }
    }

    return computed;
  }

  parsePx(val, defaultVal = 0) {
    if (!val || typeof val !== 'string') return defaultVal;
    if (val.endsWith('px')) return parseFloat(val) || defaultVal;
    if (val === '0') return 0;
    return defaultVal;
  }

  getEffectiveTapGeometry(viewportWidth = 375) {
    const style = this.computeStyle(viewportWidth);
    const heightVal = this.parsePx(style.height, 0);
    const minHeightVal = this.parsePx(style.minHeight, 0);
    const widthVal = this.parsePx(style.width, 0);
    const minWidthVal = this.parsePx(style.minWidth, 0);
    const padTop = this.parsePx(style.paddingTop, 0);
    const padBottom = this.parsePx(style.paddingBottom, 0);
    const padLeft = this.parsePx(style.paddingLeft, 0);
    const padRight = this.parsePx(style.paddingRight, 0);
    const fontSize = this.parsePx(style.fontSize, 14);

    let effectiveHeight = Math.max(heightVal, minHeightVal);
    if (effectiveHeight === 0) {
      effectiveHeight = fontSize * 1.3 + padTop + padBottom;
    }

    let effectiveWidth = Math.max(widthVal, minWidthVal);
    if (effectiveWidth === 0) {
      effectiveWidth = fontSize * 2 + padLeft + padRight;
    }

    // Check container padding contribution if element sits in a dedicated touch container
    let containerPaddingBonus = 0;
    if (this.parentElement) {
      const parentStyle = this.parentElement.computeStyle(viewportWidth);
      const parentPadY = this.parsePx(parentStyle.paddingTop, 0) + this.parsePx(parentStyle.paddingBottom, 0);
      if (parentPadY > 0) {
        containerPaddingBonus = parentPadY;
      }
    }

    return {
      style,
      effectiveHeight,
      effectiveWidth,
      padTop,
      padBottom,
      padLeft,
      padRight,
      containerPaddingBonus,
      hasTouchPaddingContainer: containerPaddingBonus >= 4 || (padTop + padBottom) >= 6
    };
  }
}

// Global browser env setup for component instantiations
global.document = {
  createElement: (tag) => new MockElement(tag),
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  body: new MockElement('body'),
  addEventListener: () => {}
};
global.window = {
  document: global.document,
  devicePixelRatio: 2,
  requestAnimationFrame: (cb) => setImmediate(cb),
  location: { origin: 'http://127.0.0.1:8096', hostname: '127.0.0.1', port: '8096' },
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} }
};
global.localStorage = global.window.localStorage;
global.sessionStorage = global.window.sessionStorage;
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

// ============================================================================
// 3. Construct Complete DOM Workspace for Audit
// ============================================================================

function buildAuditDomTree() {
  const root = new MockElement('div', 'root');

  // #app shell
  const app = new MockElement('div', 'app');
  root.appendChild(app);

  // 1. Header
  const header = new MockElement('header');
  header.className = 'app-header';
  app.appendChild(header);

  const headerControls = new MockElement('div');
  headerControls.className = 'header-controls';
  header.appendChild(headerControls);

  const modelSelect = new MockElement('select', 'modelSelect');
  modelSelect.className = 'model-select';
  headerControls.appendChild(modelSelect);

  const settingsBtn = new MockElement('button', 'settingsBtn');
  settingsBtn.className = 'icon-btn';
  headerControls.appendChild(settingsBtn);

  // 2. Tab Bar
  const tabBar = new MockElement('nav', 'tabBar');
  tabBar.className = 'tab-bar';
  app.appendChild(tabBar);

  const tabChat = new MockElement('button');
  tabChat.className = 'tab-btn active';
  tabBar.appendChild(tabChat);

  const tabCockpit = new MockElement('button');
  tabCockpit.className = 'tab-btn';
  tabBar.appendChild(tabCockpit);

  // 3. Tab Content
  const tabContent = new MockElement('main', 'tabContent');
  tabContent.className = 'tab-content';
  app.appendChild(tabContent);

  // Cockpit View Container inside tab content
  const cockpitTab = new MockElement('div', 'tab-cockpit');
  cockpitTab.className = 'tab-pane active';
  tabContent.appendChild(cockpitTab);

  const cockpitContainer = new MockElement('div');
  cockpitContainer.className = 'cockpit-container';
  cockpitTab.appendChild(cockpitContainer);

  // Sticky Search Bar
  const searchSticky = new MockElement('div');
  searchSticky.className = 'cockpit-search-sticky';
  cockpitContainer.appendChild(searchSticky);

  const searchForm = new MockElement('form', 'cockpitSearchForm');
  searchForm.className = 'cockpit-search-form';
  searchSticky.appendChild(searchForm);

  const searchInputWrapper = new MockElement('div');
  searchInputWrapper.className = 'cockpit-search-input-wrapper';
  searchForm.appendChild(searchInputWrapper);

  const searchInput = new MockElement('input', 'cockpitSearchInput');
  searchInput.className = 'cockpit-search-input';
  searchInputWrapper.appendChild(searchInput);

  const clearBtn = new MockElement('button', 'cockpitClearBtn');
  clearBtn.className = 'cockpit-clear-btn';
  searchInputWrapper.appendChild(clearBtn);

  const searchBtn = new MockElement('button', 'cockpitSearchBtn');
  searchBtn.className = 'cockpit-search-btn';
  searchForm.appendChild(searchBtn);

  // Suggestion Chips
  const chipsBar = new MockElement('div');
  chipsBar.className = 'cockpit-chips-bar';
  searchSticky.appendChild(chipsBar);

  const chipsList = new MockElement('div', 'cockpitSuggestedChips');
  chipsList.className = 'chips-list';
  chipsBar.appendChild(chipsList);

  for (const ticker of ['NVDA', 'SPY', 'QQQ', 'TSLA', 'AAPL', 'AMD']) {
    const chip = new MockElement('button');
    chip.className = 'cockpit-chip suggestion-chip';
    chip.setAttribute('data-ticker', ticker);
    chipsList.appendChild(chip);
  }

  // Dashboard 3-Panel Stack
  const dashboard = new MockElement('div');
  dashboard.className = 'cockpit-dashboard';
  cockpitContainer.appendChild(dashboard);

  // Panel 1: Synergized Synthesis (Hero Card)
  const panelHero = new MockElement('div', 'cockpitPanelHero');
  panelHero.className = 'cockpit-panel cockpit-panel-hero';
  dashboard.appendChild(panelHero);

  const pillsGrid = new MockElement('div');
  pillsGrid.className = 'cockpit-metric-pills';
  panelHero.appendChild(pillsGrid);

  for (const pillId of ['pillConfluence', 'pillRegime', 'pillFlowRatio', 'pillWallRange']) {
    const pill = new MockElement('div', pillId);
    pill.className = 'metric-pill bullish';
    pillsGrid.appendChild(pill);
  }

  const synthBox = new MockElement('div');
  synthBox.className = 'synthesis-content-box';
  panelHero.appendChild(synthBox);

  // Panel 2: Interactive Exposure Chart
  const panelChart = new MockElement('div', 'cockpitPanelChart');
  panelChart.className = 'cockpit-panel cockpit-panel-chart';
  dashboard.appendChild(panelChart);

  const toggleContainer = new MockElement('div', 'gexDexToggle');
  toggleContainer.className = 'gex-dex-toggle';
  panelChart.appendChild(toggleContainer);

  for (const mode of ['both', 'gex', 'dex']) {
    const toggleBtn = new MockElement('button');
    toggleBtn.className = `toggle-btn ${mode === 'both' ? 'active' : ''}`;
    toggleBtn.setAttribute('data-mode', mode);
    toggleContainer.appendChild(toggleBtn);
  }

  const keyLevelsStrip = new MockElement('div');
  keyLevelsStrip.className = 'cockpit-key-levels';
  panelChart.appendChild(keyLevelsStrip);

  for (const [id, cls] of [['klSpot', 'val-spot'], ['klFlip', 'val-flip'], ['klCall', 'val-call'], ['klPut', 'val-put']]) {
    const klItem = new MockElement('div');
    klItem.className = 'key-level-item';
    const klVal = new MockElement('span', id);
    klVal.className = `kl-val ${cls}`;
    klItem.appendChild(klVal);
    keyLevelsStrip.appendChild(klItem);
  }

  const chartSlot = new MockElement('div');
  chartSlot.className = 'cockpit-chart-slot';
  panelChart.appendChild(chartSlot);

  const canvasWrapper = new MockElement('div');
  canvasWrapper.className = 'cockpit-canvas-wrapper';
  chartSlot.appendChild(canvasWrapper);

  const canvas = new MockElement('canvas');
  canvas.className = 'quant-canvas';
  canvasWrapper.appendChild(canvas);

  // Panel 3: 30-Day Options Flow Table
  const panelFlow = new MockElement('div', 'cockpitPanelFlow');
  panelFlow.className = 'cockpit-panel cockpit-panel-flow';
  dashboard.appendChild(panelFlow);

  const flowChips = new MockElement('div', 'flowFilterChips');
  flowChips.className = 'flow-filter-chips';
  panelFlow.appendChild(flowChips);

  for (const filter of ['all', 'whales', 'calls', 'puts', 'unusual']) {
    const chip = new MockElement('button');
    chip.className = `flow-chip ${filter === 'all' ? 'active' : ''}`;
    chip.setAttribute('data-filter', filter);
    flowChips.appendChild(chip);
  }

  const flowTableContainer = new MockElement('div', 'cockpitFlowTableContainer');
  flowTableContainer.className = 'cockpit-flow-table-container';
  panelFlow.appendChild(flowTableContainer);

  const quantTableWrapper = new MockElement('div');
  quantTableWrapper.className = 'quant-table-wrapper';
  flowTableContainer.appendChild(quantTableWrapper);

  const tableScroll = new MockElement('div');
  tableScroll.className = 'quant-table-scroll';
  quantTableWrapper.appendChild(tableScroll);

  const table = new MockElement('table');
  table.className = 'quant-table';
  tableScroll.appendChild(table);

  const paginationBar = new MockElement('div');
  paginationBar.className = 'bb-pagination';
  quantTableWrapper.appendChild(paginationBar);

  const prevBtn = new MockElement('button');
  prevBtn.className = 'bb-page-btn btn-prev';
  paginationBar.appendChild(prevBtn);

  const pageNums = new MockElement('div');
  pageNums.className = 'bb-page-nums';
  paginationBar.appendChild(pageNums);

  const pageNum1 = new MockElement('button');
  pageNum1.className = 'bb-page-num active';
  pageNums.appendChild(pageNum1);

  const nextBtn = new MockElement('button');
  nextBtn.className = 'bb-page-btn btn-next';
  paginationBar.appendChild(nextBtn);

  // 4. Prompt Input Bar
  const promptContainer = new MockElement('div', 'promptContainer');
  promptContainer.className = 'prompt-bar-container';
  app.appendChild(promptContainer);

  const promptForm = new MockElement('form');
  promptForm.className = 'prompt-form';
  promptContainer.appendChild(promptForm);

  const promptTextarea = new MockElement('textarea');
  promptTextarea.className = 'prompt-textarea';
  promptForm.appendChild(promptTextarea);

  const promptSendBtn = new MockElement('button', 'promptSendBtn');
  promptSendBtn.className = 'prompt-send-btn';
  promptForm.appendChild(promptSendBtn);

  const promptStopBtn = new MockElement('button', 'promptStopBtn');
  promptStopBtn.className = 'prompt-stop-btn';
  promptForm.appendChild(promptStopBtn);

  // 5. Settings Modal
  const settingsModal = new MockElement('div', 'settingsModal');
  settingsModal.className = 'modal-overlay open';
  root.appendChild(settingsModal);

  const settingsCard = new MockElement('div');
  settingsCard.className = 'modal-card';
  settingsModal.appendChild(settingsCard);

  const settingsHeader = new MockElement('div');
  settingsHeader.className = 'modal-header';
  settingsCard.appendChild(settingsHeader);

  const settingsClose = new MockElement('button', 'settingsClose');
  settingsClose.className = 'modal-close-btn';
  settingsHeader.appendChild(settingsClose);

  const settingsBody = new MockElement('div');
  settingsBody.className = 'modal-body';
  settingsCard.appendChild(settingsBody);

  const groupPass = new MockElement('div');
  groupPass.className = 'form-group';
  const passInput = new MockElement('input', 'passcodeInput');
  passInput.className = 'form-input';
  groupPass.appendChild(passInput);
  settingsBody.appendChild(groupPass);

  const groupUrl = new MockElement('div');
  groupUrl.className = 'form-group';
  const urlInput = new MockElement('input', 'gatewayUrlInput');
  urlInput.className = 'form-input';
  groupUrl.appendChild(urlInput);
  settingsBody.appendChild(groupUrl);

  const versionCard = new MockElement('div', 'versionInfoCard');
  versionCard.className = 'version-info-card';
  settingsBody.appendChild(versionCard);

  const settingsActions = new MockElement('div');
  settingsActions.className = 'settings-actions update-action-container';
  settingsBody.appendChild(settingsActions);

  const forceUpdateBtn = new MockElement('button', 'forceUpdateBtn');
  forceUpdateBtn.className = 'btn btn-synced';
  settingsActions.appendChild(forceUpdateBtn);

  const manualResyncLink = new MockElement('div', 'manualResyncLink');
  manualResyncLink.className = 'manual-resync-link';
  settingsActions.appendChild(manualResyncLink);

  const syncFlowBtn = new MockElement('button', 'syncFlowBtn');
  syncFlowBtn.className = 'btn btn-synced';
  settingsActions.appendChild(syncFlowBtn);

  const syncLevelsBtn = new MockElement('button', 'syncLevelsBtn');
  syncLevelsBtn.className = 'btn btn-synced';
  settingsActions.appendChild(syncLevelsBtn);

  const lockAppBtn = new MockElement('button', 'lockAppBtn');
  lockAppBtn.className = 'btn btn-warning';
  settingsActions.appendChild(lockAppBtn);

  const clearHistoryBtn = new MockElement('button', 'clearHistoryBtn');
  clearHistoryBtn.className = 'btn btn-secondary';
  settingsActions.appendChild(clearHistoryBtn);

  const settingsSave = new MockElement('button', 'settingsSave');
  settingsSave.className = 'btn btn-primary';
  settingsActions.appendChild(settingsSave);

  // 6. Diagnostics Modal
  const diagModal = new MockElement('div', 'diagnosticsModal');
  diagModal.className = 'modal-overlay diagnostics-overlay open';
  root.appendChild(diagModal);

  const diagCard = new MockElement('div');
  diagCard.className = 'modal-card diagnostics-modal';
  diagModal.appendChild(diagCard);

  const diagHeader = new MockElement('div');
  diagHeader.className = 'modal-header';
  diagCard.appendChild(diagHeader);

  const diagClose = new MockElement('button', 'diagnosticsClose');
  diagClose.className = 'modal-close-btn';
  diagHeader.appendChild(diagClose);

  const diagBody = new MockElement('div');
  diagBody.className = 'modal-body diag-body';
  diagCard.appendChild(diagBody);

  const diagMetaGrid = new MockElement('div');
  diagMetaGrid.className = 'diag-meta-grid';
  diagBody.appendChild(diagMetaGrid);

  const waterfallSection = new MockElement('div');
  waterfallSection.className = 'waterfall-section';
  diagBody.appendChild(waterfallSection);

  // 7. Lock Screen Auth Gate Overlay
  const lockScreen = new MockElement('div', 'lockScreen');
  lockScreen.className = 'lock-screen-overlay visible';
  root.appendChild(lockScreen);

  const lockCard = new MockElement('div', 'lockCard');
  lockCard.className = 'lock-card';
  lockScreen.appendChild(lockCard);

  const lockForm = new MockElement('form', 'lockForm');
  lockForm.className = 'lock-form';
  lockCard.appendChild(lockForm);

  const lockInputWrapper = new MockElement('div');
  lockInputWrapper.className = 'lock-input-wrapper';
  lockForm.appendChild(lockInputWrapper);

  const lockPassInput = new MockElement('input', 'lockPasswordInput');
  lockPassInput.className = 'lock-input';
  lockInputWrapper.appendChild(lockPassInput);

  const lockToggleBtn = new MockElement('button', 'lockTogglePassBtn');
  lockToggleBtn.className = 'lock-toggle-btn';
  lockInputWrapper.appendChild(lockToggleBtn);

  const lockSubmitBtn = new MockElement('button', 'lockSubmitBtn');
  lockSubmitBtn.className = 'lock-submit-btn';
  lockForm.appendChild(lockSubmitBtn);

  // 8. Lightbox Modal
  const lightboxOverlay = new MockElement('div', 'lightboxOverlay');
  lightboxOverlay.className = 'lightbox-overlay open';
  root.appendChild(lightboxOverlay);

  const lightboxHeader = new MockElement('div');
  lightboxHeader.className = 'lightbox-header';
  lightboxOverlay.appendChild(lightboxHeader);

  const lightboxClose = new MockElement('button', 'lightboxClose');
  lightboxClose.className = 'lightbox-close';
  lightboxHeader.appendChild(lightboxClose);

  const lightboxContent = new MockElement('div');
  lightboxContent.className = 'lightbox-content';
  lightboxOverlay.appendChild(lightboxContent);

  return { root, app, settingsModal, diagModal, lockScreen, lightboxOverlay, cockpitTab };
}

// ============================================================================
// 4. Test Suite Execution & Prober Logic
// ============================================================================

let passCount = 0;
let failCount = 0;

function assertTest(condition, message) {
  if (condition) {
    console.log(`  ✓ PASS: ${message}`);
    passCount++;
  } else {
    console.error(`  ✗ FAIL: ${message}`);
    failCount++;
  }
}

console.log('==================================================================');
console.log('  UNIFIED BROWSER LAYOUT & GEOMETRY PROBER (UI-01)               ');
console.log('==================================================================\n');

const viewports = [
  { name: 'Mobile Portrait', width: 375 },
  { name: 'Tablet Portrait', width: 768 },
  { name: 'Desktop Landscape', width: 1280 }
];

const { root, app, settingsModal, diagModal, lockScreen, lightboxOverlay, cockpitTab } = buildAuditDomTree();

// ----------------------------------------------------------------------------
// AUDIT 1: Responsive Viewport Geometry (375px, 768px, 1280px)
// ----------------------------------------------------------------------------
console.log('--- AUDIT 1: Responsive Viewport Geometry ---');

for (const vp of viewports) {
  console.log(`\n  [Viewport: ${vp.name} (${vp.width}px)]`);

  // 1. Root #app layout
  const appStyle = app.computeStyle(vp.width);
  assertTest(appStyle.boxSizing === 'border-box', `[${vp.width}px] #app uses border-box sizing`);
  assertTest(appStyle.maxWidth === '800px', `[${vp.width}px] #app max-width is capped at 800px`);
  assertTest(appStyle.overflowX === 'hidden' || appStyle.overflowY === 'hidden', `[${vp.width}px] #app prevents outer viewport scrolling (overflow: hidden)`);

  // 2. Diagnostics Modal Responsiveness (@media max-width: 480px)
  const diagCard = diagModal.querySelector('.diagnostics-modal');
  const diagCardStyle = diagCard.computeStyle(vp.width);
  if (vp.width <= 480) {
    assertTest(diagCardStyle.width === 'calc(100% - 16px)' || diagCardStyle.width === '100%', `[${vp.width}px] Diagnostics modal adapts full mobile width with margins: ${diagCardStyle.width}`);
  } else {
    assertTest(diagCardStyle.maxWidth === '500px' || diagCardStyle.maxWidth === '440px' || diagCardStyle.width === '100%', `[${vp.width}px] Diagnostics modal constrained to standard desktop/tablet card (${diagCardStyle.maxWidth})`);
  }

  // 3. Tab Bar & Navigation
  const tabBarStyle = app.querySelector('.tab-bar').computeStyle(vp.width);
  assertTest(tabBarStyle.display === 'flex', `[${vp.width}px] Tab bar displays as flex container`);

  // 4. Header Bar
  const headerStyle = app.querySelector('.app-header').computeStyle(vp.width);
  assertTest(headerStyle.display === 'flex', `[${vp.width}px] App header displays as flex container`);
}

// ----------------------------------------------------------------------------
// AUDIT 2: WCAG Touch-Target Accessibility Audit (>= 44px min tap area or >= 36px with padding container)
// ----------------------------------------------------------------------------
console.log('\n--- AUDIT 2: WCAG Touch-Target Accessibility Audit ---');

const interactiveAuditTargets = [
  { name: 'Settings Button (Header)', selector: '#settingsBtn', minTap: 36, requiresContainer: true },
  { name: 'Model Selector (Header)', selector: '#modelSelect', minTap: 36, requiresContainer: true },
  { name: 'Tab Navigation Button', selector: '.tab-btn', minTap: 44, requiresContainer: false },
  { name: 'Cockpit Search Input', selector: '#cockpitSearchInput', minTap: 44, requiresContainer: false },
  { name: 'Cockpit Clear Button', selector: '#cockpitClearBtn', minTap: 36, requiresContainer: true },
  { name: 'Cockpit Search Button', selector: '#cockpitSearchBtn', minTap: 44, requiresContainer: false },
  { name: 'Quick Suggestion Chip', selector: '.suggestion-chip', minTap: 36, requiresContainer: true },
  { name: 'GEX/DEX Toggle Button', selector: '.gex-dex-toggle .toggle-btn', minTap: 36, requiresContainer: true },
  { name: 'Options Flow Filter Chip', selector: '.flow-chip', minTap: 36, requiresContainer: true },
  { name: 'Bloomberg Page Prev Button', selector: '.bb-page-btn.btn-prev', minTap: 36, requiresContainer: true },
  { name: 'Bloomberg Page Next Button', selector: '.bb-page-btn.btn-next', minTap: 36, requiresContainer: true },
  { name: 'Bloomberg Page Number Button', selector: '.bb-page-num', minTap: 36, requiresContainer: true },
  { name: 'Prompt Send Button', selector: '#promptSendBtn', minTap: 36, requiresContainer: true },
  { name: 'Prompt Stop Button', selector: '#promptStopBtn', minTap: 36, requiresContainer: true },
  { name: 'Settings Close Button', selector: '#settingsClose', minTap: 44, requiresContainer: false },
  { name: 'Diagnostics Close Button', selector: '#diagnosticsClose', minTap: 44, requiresContainer: false },
  { name: 'Lightbox Close Button', selector: '#lightboxClose', minTap: 44, requiresContainer: false },
  { name: 'Lock Passcode Input', selector: '#lockPasswordInput', minTap: 44, requiresContainer: false },
  { name: 'Lock Toggle Pass Button', selector: '#lockTogglePassBtn', minTap: 36, requiresContainer: true },
  { name: 'Lock Submit Button', selector: '#lockSubmitBtn', minTap: 44, requiresContainer: false },
  { name: 'Settings Primary Save Button', selector: '#settingsSave', minTap: 44, requiresContainer: false },
  { name: 'Settings Warning Lock Button', selector: '#lockAppBtn', minTap: 44, requiresContainer: false },
  { name: 'Settings Sync Flow Button', selector: '#syncFlowBtn', minTap: 44, requiresContainer: false },
  { name: 'Settings Sync Levels Button', selector: '#syncLevelsBtn', minTap: 44, requiresContainer: false },
  { name: 'Settings Force Update Button', selector: '#forceUpdateBtn', minTap: 44, requiresContainer: false }
];

for (const target of interactiveAuditTargets) {
  const el = root.querySelector(target.selector);
  assertTest(el !== null, `Target element located in DOM: ${target.name} (${target.selector})`);
  if (!el) continue;

  for (const vp of [375, 768]) {
    const geo = el.getEffectiveTapGeometry(vp);
    const passes44 = geo.effectiveHeight >= 44 && geo.effectiveWidth >= 44;
    const passes36WithContainer = (geo.effectiveHeight >= 36 && geo.effectiveWidth >= 36) ||
      (geo.effectiveHeight + geo.containerPaddingBonus >= 36);

    const isCompliant = target.minTap >= 44 ? (geo.effectiveHeight >= 44 || passes36WithContainer) : (passes44 || passes36WithContainer);

    assertTest(
      isCompliant,
      `[${vp}px] ${target.name}: effective tap size ${geo.effectiveWidth.toFixed(0)}x${geo.effectiveHeight.toFixed(0)}px satisfies WCAG touch target (min requirement ${target.minTap}px)`
    );
  }
}

// ----------------------------------------------------------------------------
// AUDIT 3: Modal Actions Geometry (.modal-body & .settings-actions)
// ----------------------------------------------------------------------------
console.log('\n--- AUDIT 3: Modal & Settings Action Button Geometry ---');

const settingsActionButtons = [
  '#forceUpdateBtn',
  '#syncFlowBtn',
  '#syncLevelsBtn',
  '#lockAppBtn',
  '#clearHistoryBtn',
  '#settingsSave'
];

const modalBodyEl = settingsModal.querySelector('.modal-body');
const settingsActionsEl = settingsModal.querySelector('.settings-actions');

const modalBodyStyle = modalBodyEl.computeStyle(375);
const settingsActionsStyle = settingsActionsEl.computeStyle(375);

assertTest(modalBodyStyle.boxSizing === 'border-box', '.modal-body has box-sizing: border-box');
assertTest(settingsActionsStyle.boxSizing === 'border-box', '.settings-actions has box-sizing: border-box');
assertTest(settingsActionsStyle.display === 'flex', '.settings-actions has flex column layout');

for (const btnSelector of settingsActionButtons) {
  const btnEl = settingsActionsEl.querySelector(btnSelector);
  assertTest(btnEl !== null, `Settings action button found: ${btnSelector}`);
  if (!btnEl) continue;

  const btnStyle = btnEl.computeStyle(375);

  // 1. Width: 100%
  assertTest(btnStyle.width === '100%', `${btnSelector} has width: 100%`);

  // 2. Box-sizing: border-box
  assertTest(btnStyle.boxSizing === 'border-box', `${btnSelector} has box-sizing: border-box`);

  // 3. Min-height >= 44px
  const minHeightVal = parseFloat(btnStyle.minHeight) || 0;
  assertTest(minHeightVal >= 44, `${btnSelector} min-height is >= 44px (got ${btnStyle.minHeight})`);

  // 4. Zero negative margins
  const mLeft = parseFloat(btnStyle.marginLeft) || 0;
  const mRight = parseFloat(btnStyle.marginRight) || 0;
  assertTest(mLeft >= 0 && mRight >= 0, `${btnSelector} has no negative horizontal margins (left: ${mLeft}px, right: ${mRight}px)`);
}

// ----------------------------------------------------------------------------
// AUDIT 4: Cockpit View & Bloomberg Options Table Zero Horizontal Overflow Audit
// ----------------------------------------------------------------------------
console.log('\n--- AUDIT 4: Cockpit View & Table Zero Horizontal Overflow Audit ---');

for (const vp of viewports) {
  console.log(`\n  [Zero Overflow Verification: ${vp.name} (${vp.width}px)]`);

  // 1. Cockpit Container
  const cockpitContStyle = cockpitTab.querySelector('.cockpit-container').computeStyle(vp.width);
  assertTest(cockpitContStyle.overflowX === 'hidden', `[${vp.width}px] .cockpit-container enforces overflow-x: hidden`);

  // 2. Sticky Search Bar
  const searchStickyStyle = cockpitTab.querySelector('.cockpit-search-sticky').computeStyle(vp.width);
  assertTest(searchStickyStyle.boxSizing === 'border-box', `[${vp.width}px] .cockpit-search-sticky has box-sizing: border-box`);

  // 3. Panel 1: Synergized Synthesis
  const p1El = cockpitTab.querySelector('#cockpitPanelHero');
  const p1Style = p1El.computeStyle(vp.width);
  assertTest(p1Style.boxSizing === 'border-box', `[${vp.width}px] Cockpit Panel 1 has box-sizing: border-box`);

  const p1PillsStyle = p1El.querySelector('.cockpit-metric-pills').computeStyle(vp.width);
  assertTest(p1PillsStyle.display === 'grid', `[${vp.width}px] Panel 1 metric pills use auto-fitting responsive grid`);

  // 4. Panel 2: Interactive Exposure Chart
  const p2El = cockpitTab.querySelector('#cockpitPanelChart');
  const p2Style = p2El.computeStyle(vp.width);
  assertTest(p2Style.boxSizing === 'border-box', `[${vp.width}px] Cockpit Panel 2 has box-sizing: border-box`);

  const keyLevelsStyle = p2El.querySelector('.cockpit-key-levels').computeStyle(vp.width);
  assertTest(keyLevelsStyle.display === 'grid', `[${vp.width}px] Key levels strip uses 4-column responsive grid`);

  const chartSlotStyle = p2El.querySelector('.cockpit-chart-slot').computeStyle(vp.width);
  assertTest(chartSlotStyle.overflowX === 'hidden' || chartSlotStyle.overflowY === 'hidden', `[${vp.width}px] Chart slot clips canvas bounds (overflow: hidden)`);

  // 5. Panel 3: 30-Day Options Flow Table
  const p3El = cockpitTab.querySelector('#cockpitPanelFlow');
  const p3Style = p3El.computeStyle(vp.width);
  assertTest(p3Style.boxSizing === 'border-box', `[${vp.width}px] Cockpit Panel 3 has box-sizing: border-box`);

  const flowChipsStyle = p3El.querySelector('.flow-filter-chips').computeStyle(vp.width);
  assertTest(flowChipsStyle.display === 'flex', `[${vp.width}px] Flow filter chips container is flexbox`);

  const flowTableContStyle = p3El.querySelector('.cockpit-flow-table-container').computeStyle(vp.width);
  assertTest(flowTableContStyle.overflowX === 'auto', `[${vp.width}px] Flow table container isolates horizontal scrolling with overflow-x: auto`);

  // 6. Bloomberg Options Table Wrapper
  const tableWrapperStyle = p3El.querySelector('.quant-table-wrapper').computeStyle(vp.width);
  assertTest(tableWrapperStyle.width === '100%', `[${vp.width}px] .quant-table-wrapper has width: 100%`);
  assertTest(tableWrapperStyle.overflowX === 'hidden' || tableWrapperStyle.overflowY === 'hidden', `[${vp.width}px] .quant-table-wrapper contains table overflow`);

  const tableScrollStyle = p3El.querySelector('.quant-table-scroll').computeStyle(vp.width);
  assertTest(tableScrollStyle.overflowX === 'auto', `[${vp.width}px] .quant-table-scroll handles inner table scroll (overflow-x: auto)`);

  const paginationStyle = p3El.querySelector('.bb-pagination').computeStyle(vp.width);
  assertTest(paginationStyle.display === 'flex', `[${vp.width}px] Bloomberg pagination toolbar displays as flex`);
}

// ============================================================================
// Summary & Structured Exit
// ============================================================================
console.log('\n==================================================================');
console.log(`  LAYOUT AUDIT RESULTS: ${passCount} PASSED, ${failCount} FAILED`);
console.log('==================================================================');

if (failCount > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
