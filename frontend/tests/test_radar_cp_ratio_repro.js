/**
 * test_radar_cp_ratio_repro.js
 * Reproduction test for Confluence Radar GEX/DEX chart Call/Put Ratio = 0.00 defect
 */
import assert from 'node:assert';
import { QuantChart } from '../src/components/quant_chart.js';
import { RadarView } from '../src/tabs/radar_view.js';

// Setup Mock DOM
class MockClassList {
  constructor(el) { this.el = el; this.classes = new Set(); }
  add(...cls) { cls.forEach(c => this.classes.add(c)); this._sync(); }
  remove(...cls) { cls.forEach(c => this.classes.delete(c)); this._sync(); }
  contains(c) { return this.classes.has(c); }
  _sync() { this.el._className = Array.from(this.classes).join(' '); }
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
    this.id = '';
    this.value = '';
    this.style = {};
    this.clientWidth = 400;
    this.clientHeight = 500;
  }

  get className() { return this._className; }
  set className(val) {
    this._className = val || '';
    this.classList.classes = new Set((val || '').split(/\s+/).filter(Boolean));
  }

  get innerHTML() { 
    if (this._innerHTML) return this._innerHTML;
    return this.children.map(c => c.innerHTML).join('');
  }
  set innerHTML(val) { this._innerHTML = val; }

  get textContent() {
    return this._innerHTML.replace(/<[^>]*>/g, '').trim();
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  querySelector(sel) {
    if (sel.startsWith('#')) {
      const id = sel.slice(1);
      const find = (el) => {
        if (el.id === id) return el;
        for (const ch of el.children) {
          const res = find(ch);
          if (res) return res;
        }
        return null;
      };
      return find(this);
    }
    return null;
  }

  querySelectorAll() { return []; }
  addEventListener() {}
  removeEventListener() {}
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 400, height: 500, right: 400, bottom: 500 };
  }

  getContext() {
    return global.__mockContext;
  }
}

global.document = {
  createElement: (tag) => new MockElement(tag)
};

global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

global.requestAnimationFrame = (cb) => { setImmediate(cb); };
global.window = {
  devicePixelRatio: 2,
  requestAnimationFrame: (cb) => { setImmediate(cb); }
};

global.__mockContext = {
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
  measureText: () => ({ width: 40 }),
  set fillStyle(val) {},
  get fillStyle() { return '#fff'; },
  set strokeStyle(val) {},
  get strokeStyle() { return '#fff'; },
  set lineWidth(val) {},
  get lineWidth() { return 1; },
  set font(val) {},
  set textAlign(val) {},
  set textBaseline(val) {}
};

async function runReproTests() {
  console.log('==================================================================');
  console.log('  REPRODUCING DEFECT: RADAR GEX/DEX CHART CALL/PUT RATIO = 0.00');
  console.log('==================================================================');

  // Test Case 1: RadarView.renderExposureChart passes call_put_ratio to QuantChart
  console.log('\n[1/2] Verifying RadarView propagates call_put_ratio to QuantChart...');
  const radarView = new RadarView();
  const mockContainer = new MockElement('div');
  mockContainer.id = 'tab-radar';
  const chartSlot = new MockElement('div');
  chartSlot.id = 'radarChartSlot';
  mockContainer.appendChild(chartSlot);
  radarView.container = mockContainer;

  const mockCockpitPayload = {
    ticker: 'BURL',
    spot_price: 265.33,
    gex: {
      ticker: 'BURL',
      spot_price: 265.33,
      call_wall: 270.0,
      put_wall: 270.0,
      zero_gex_level: 259.20,
      call_put_ratio: 0.07,
      strikes: [
        { strike: 260.0, call_gex: 10000.0, put_gex: -50000.0 },
        { strike: 270.0, call_gex: 50000.0, put_gex: -10000.0 }
      ]
    }
  };

  radarView.renderExposureChart(mockCockpitPayload);
  const chartInstance = radarView.quantChartInstance;

  assert.ok(chartInstance, 'QuantChart instance should be created');
  console.log(`  -> Chart data call_put_ratio: ${chartInstance.data.call_put_ratio}`);
  assert.strictEqual(
    chartInstance.data.call_put_ratio,
    0.07,
    `Expected chartData.call_put_ratio to be 0.07, but got ${chartInstance.data.call_put_ratio}`
  );

  const cpHeaderMatch = chartInstance.wrapper.innerHTML.match(/<div class="macro-box cp-box">[\s\S]*?<span class="macro-val">(.*?)<\/span>/);
  const renderedCpVal = cpHeaderMatch ? cpHeaderMatch[1].trim() : null;
  console.log(`  -> Rendered header Call/Put ratio: "${renderedCpVal}"`);
  assert.strictEqual(
    renderedCpVal,
    '0.07',
    `Expected header to render "0.07", but got "${renderedCpVal}"`
  );

  // Test Case 2: QuantChart fallback derivation from strikes when call_put_ratio omitted
  console.log('\n[2/2] Verifying QuantChart derives call_put_ratio from strikes when omitted...');
  const slot2 = new MockElement('div');
  const chart2 = new QuantChart(slot2, {
    ticker: 'TSLA',
    spot_price: 200.0,
    strikes: [
      { strike: 195.0, call_gex: 3000.0, put_gex: -1000.0 },
      { strike: 205.0, call_gex: 3000.0, put_gex: -1000.0 }
    ]
  });

  const cpHeaderMatch2 = chart2.wrapper.innerHTML.match(/<div class="macro-box cp-box">[\s\S]*?<span class="macro-val">(.*?)<\/span>/);
  const renderedCpVal2 = cpHeaderMatch2 ? cpHeaderMatch2[1].trim() : null;
  console.log(`  -> Rendered fallback Call/Put ratio: "${renderedCpVal2}"`);
  assert.strictEqual(
    renderedCpVal2,
    '3.00',
    `Expected fallback header to render "3.00" (6000 / 2000), but got "${renderedCpVal2}"`
  );

  console.log('\n[PASS] All Call/Put Ratio checks passed successfully.');
}

runReproTests().catch((err) => {
  console.error('\n[DEFECT CONFIRMED] Test failed as expected:', err.message);
  process.exit(1);
});
