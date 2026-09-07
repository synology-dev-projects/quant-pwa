/**
 * test_radar_vix_repro.js
 * Reproduction test for VIX empty graph bug & scanner qualification anomalies
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
    this._textParts = [];
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

  get innerHTML() { return this._innerHTML; }
  set innerHTML(val) { this._innerHTML = val; }

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

  getContext(type) {
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

async function runReproTests() {
  console.log('==================================================================');
  console.log('  REPRODUCING DEFECT: VIX GRAPH EMPTY & SCORING QUALIFICATION');
  console.log('==================================================================');

  // Track bar drawing calls
  const barFills = [];
  global.__mockContext = {
    resetTransform: () => {},
    scale: () => {},
    fillRect: (x, y, w, h) => {
      // Exclude full canvas (w=400, h=420) and panel backgrounds (w ~ 152, h ~ 335)
      if (w > 0 && w < 100 && h > 0) {
        barFills.push({ x, y, w, h });
      }
    },
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
    font: '',
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1
  };

  // 1. PROBE 1: QuantChart with strikes having exp_gex, but data.expirations omitted
  console.log('\n--- PROBE 1: QuantChart Missing Expirations Fallback ---');
  const chartContainer = new MockElement('div');
  const mockVixDataWithoutExpirations = {
    ticker: 'VIX',
    spot_price: 14.53,
    zero_flip: 13.92,
    call_wall: 14.5,
    put_wall: 14.5,
    // Note: data.expirations is deliberately omitted!
    strikes: [
      {
        strike: 14.0,
        call_gex: 4910138.0,
        put_gex: 330835539.0,
        call_dex: 3618520.0,
        put_dex: 6329007.0,
        net_gex: -325925401.0,
        net_dex: -2710487.0,
        exp_gex: {
          '2026-09-16': { call: 3607068.0, put: 289623943.0 },
          '2026-10-21': { call: 1303069.0, put: 41211595.0 }
        },
        exp_dex: {
          '2026-09-16': { call: 2003027.0, put: 4867900.0 },
          '2026-10-21': { call: 1615492.0, put: 1461107.0 }
        }
      },
      {
        strike: 14.5,
        call_gex: 4313337.0,
        put_gex: 926669453.0,
        call_dex: 2572904.0,
        put_dex: 19512717.0,
        net_gex: -922356116.0,
        net_dex: -16939812.0,
        exp_gex: {
          '2026-09-16': { call: 3306881.0, put: 797154601.0 },
          '2026-10-21': { call: 1006455.0, put: 129514852.0 }
        },
        exp_dex: {
          '2026-09-16': { call: 1492916.0, put: 15140280.0 },
          '2026-10-21': { call: 1079988.0, put: 4372437.0 }
        }
      }
    ]
  };

  const chart = new QuantChart(chartContainer, mockVixDataWithoutExpirations, { mode: 'both' });
  chart.draw();

  console.log(`  Rendered filled exposure bars: ${barFills.length}`);
  assert(barFills.length > 0, `QuantChart MUST draw exposure bars even when data.expirations is omitted (got ${barFills.length} bars)`);
  console.log('  ✓ PASS: QuantChart successfully draws exposure bars using strike-level expirations fallback');

  // 2. PROBE 2: RadarView renderExposureChart passing expirations
  console.log('\n--- PROBE 2: RadarView renderExposureChart Expirations Propagation ---');
  const radar = new RadarView();
  const radarContainer = new MockElement('div');
  radar.container = radarContainer;
  const radarChartSlot = new MockElement('div');
  radarChartSlot.id = 'radarChartSlot';
  radarContainer.children.push(radarChartSlot);

  const mockCockpitPayload = {
    ticker: 'VIX',
    spot_price: 14.53,
    gex: {
      spot_price: 14.53,
      zero_gex_level: 13.92,
      call_wall: 14.5,
      put_wall: 14.5,
      expirations: ['2026-09-16', '2026-10-21'],
      strikes: mockVixDataWithoutExpirations.strikes
    }
  };

  radar.renderExposureChart(mockCockpitPayload);
  assert(radar.quantChartInstance, 'QuantChart instance must be mounted');
  assert(
    Array.isArray(radar.quantChartInstance.data.expirations) && radar.quantChartInstance.data.expirations.length > 0,
    'radarView MUST propagate expirations from cockpitData into QuantChart'
  );
  console.log('  ✓ PASS: RadarView cleanly propagates expirations array into QuantChart');

  console.log('\n==================================================================');
  console.log('  ALL REPRO CHECKS PASSED');
  console.log('==================================================================');
}

runReproTests().catch(err => {
  console.error('\n[REPRO DEFECT CAPTURED]:', err.message);
  process.exit(1);
});
