/**
 * Reproduction Test: GEX/DEX Spot Line Coordinate Alignment (POWL & Non-Uniform Strike Chains)
 *
 * Verifies that reference lines (Spot Price, Call Wall, Put Wall) are positioned
 * using piecewise strike-interpolated coordinates rather than linear min/max interpolation,
 * preventing visual misalignment where a $179 spot appears next to a $165 strike label.
 */

class MockClassList {
  constructor(el) {
    this._el = el;
    this._classes = new Set();
  }
  add(...classes) { classes.forEach(c => c && this._classes.add(c)); }
  remove(...classes) { classes.forEach(c => this._classes.delete(c)); }
  contains(cls) { return this._classes.has(cls); }
}

class MockElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this._className = '';
    this.classList = new MockClassList(this);
    this.dataset = {};
    this.children = [];
    this.parentElement = null;
    this.listeners = {};
    this._innerHTML = '';
    this.style = {};
    this.clientWidth = 380;
    this.clientHeight = 450;
    this.width = 380;
    this.height = 450;
  }
  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  addEventListener(event, fn) {
    this.listeners[event] = fn;
  }
  querySelector(sel) { return null; }
  querySelectorAll(sel) { return []; }
  getContext(type) {
    return new MockCanvasContext();
  }
}

class MockCanvasContext {
  constructor() {
    this.calls = [];
  }
  resetTransform() {}
  scale() {}
  fillRect() {}
  strokeRect() {}
  fillText() {}
  save() {}
  restore() {}
  beginPath() {}
  moveTo(x, y) { this.calls.push({ type: 'moveTo', x, y }); }
  lineTo(x, y) { this.calls.push({ type: 'lineTo', x, y }); }
  stroke() {}
  setLineDash() {}
}

global.window = {
  devicePixelRatio: 1,
  innerWidth: 390,
  addEventListener(event, fn) {},
  removeEventListener(event, fn) {}
};
global.document = {
  createElement(tag) {
    return new MockElement(tag);
  }
};
global.HTMLElement = MockElement;
global.requestAnimationFrame = (cb) => cb();

import { QuantChart } from '../src/components/quant_chart.js';

const POWL_MOCK_DATA = {
  ticker: 'POWL',
  spot_price: 179.73,
  call_wall: 190.00,
  put_wall: 180.00,
  strikes: [
    { strike: 115.0, call_gex: 1000, put_gex: 0 },
    { strike: 120.0, call_gex: 1000, put_gex: 0 },
    { strike: 125.0, call_gex: 1000, put_gex: 0 },
    { strike: 130.0, call_gex: 1000, put_gex: 0 },
    { strike: 135.0, call_gex: 1000, put_gex: 0 },
    { strike: 140.0, call_gex: 1000, put_gex: 0 },
    { strike: 145.0, call_gex: 1000, put_gex: 0 },
    { strike: 150.0, call_gex: 1000, put_gex: 0 },
    { strike: 155.0, call_gex: 1000, put_gex: 0 },
    { strike: 160.0, call_gex: 1000, put_gex: 0 },
    { strike: 165.0, call_gex: 1000, put_gex: 0 }, // idx 10
    { strike: 170.0, call_gex: 1000, put_gex: 0 }, // idx 11
    { strike: 175.0, call_gex: 1000, put_gex: 0 }, // idx 12
    { strike: 180.0, call_gex: 1000, put_gex: 0 }, // idx 13 (Closest to Spot 179.73)
    { strike: 185.0, call_gex: 1000, put_gex: 0 }, // idx 14
    { strike: 190.0, call_gex: 1000, put_gex: 0 }, // idx 15
    { strike: 195.0, call_gex: 1000, put_gex: 0 }, // idx 16
    { strike: 200.0, call_gex: 1000, put_gex: 0 }, // idx 17
    { strike: 210.0, call_gex: 1000, put_gex: 0 }, // idx 18 ($10 steps begin)
    { strike: 220.0, call_gex: 1000, put_gex: 0 },
    { strike: 230.0, call_gex: 1000, put_gex: 0 },
    { strike: 240.0, call_gex: 1000, put_gex: 0 },
    { strike: 250.0, call_gex: 1000, put_gex: 0 },
    { strike: 260.0, call_gex: 1000, put_gex: 0 },
    { strike: 270.0, call_gex: 1000, put_gex: 0 },
    { strike: 280.0, call_gex: 1000, put_gex: 0 },
    { strike: 290.0, call_gex: 1000, put_gex: 0 },
    { strike: 300.0, call_gex: 1000, put_gex: 0 },
    { strike: 310.0, call_gex: 1000, put_gex: 0 },
    { strike: 320.0, call_gex: 1000, put_gex: 0 },
    { strike: 330.0, call_gex: 1000, put_gex: 0 },
    { strike: 340.0, call_gex: 1000, put_gex: 0 },
    { strike: 350.0, call_gex: 1000, put_gex: 0 }  // idx 32
  ]
};

console.log('🧪 RUNNING IN-SITU REPRODUCTION TEST FOR GEX SPOT LINE ALIGNMENT');

const container = new MockElement('div');
const chart = new QuantChart(container, POWL_MOCK_DATA);
chart.draw();

const n = POWL_MOCK_DATA.strikes.length;
const paddingTop = 45;
const paddingBottom = 40;
const displayH = Math.max(420, Math.min(560, n * 18));
const chartH = displayH - paddingTop - paddingBottom;
const rowStep = chartH / n;

const expectedRow180Y = paddingTop + (n - 1 - 13) * rowStep + rowStep / 2;
const expectedRow165Y = paddingTop + (n - 1 - 10) * rowStep + rowStep / 2;

const spotY = chart.getYForStrike ? chart.getYForStrike(179.73, paddingTop, chartH) : null;

console.log('[Metric] Display Height: ' + displayH + ', Chart Height: ' + chartH + ', Row Step: ' + rowStep.toFixed(2));
console.log('[Metric] Strike $180 Y: ' + expectedRow180Y.toFixed(2) + 'px');
console.log('[Metric] Strike $165 Y: ' + expectedRow165Y.toFixed(2) + 'px');
console.log('[Metric] Spot $179.73 Y: ' + (spotY !== null ? spotY.toFixed(2) + 'px' : 'UNDEFINED'));

if (spotY === null) {
  console.error('❌ RED FAILURE: getYForStrike is not exposed or returned null.');
  process.exit(1);
}

const distTo180 = Math.abs(spotY - expectedRow180Y);
const distTo165 = Math.abs(spotY - expectedRow165Y);

console.log('[Verification] Distance from Spot to Strike $180: ' + distTo180.toFixed(2) + 'px');
console.log('[Verification] Distance from Spot to Strike $165: ' + distTo165.toFixed(2) + 'px');

if (distTo180 > rowStep * 0.75) {
  console.error('❌ RED FAILURE: Spot Line at $179.73 is misaligned! Distance to $180 is ' + distTo180.toFixed(2) + 'px (closer to $165: ' + distTo165.toFixed(2) + 'px).');
  process.exit(1);
}

console.log('✅ GREEN PASS: Spot Line is accurately aligned with the $180 strike row!');
process.exit(0);
