import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Confluence Radar (Debloated Clean Slate)
 */

class MockElement {
  constructor(tagName = 'div', id = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.className = '';
    this.children = [];
    this.innerHTML = '';
    this.textContent = '';
  }

  querySelector(sel) {
    if (sel.startsWith('#')) {
      const id = sel.slice(1);
      if (this.id === id) return this;
      for (const child of this.children) {
        if (child.querySelector) {
          const res = child.querySelector(sel);
          if (res) return res;
        }
      }
    }
    return null;
  }
}

// Emulate simple DOM container
const rootContainer = {
  innerHTML: '',
  querySelector(sel) {
    if (this.innerHTML.includes(sel.replace('#', 'id="').replace('.', 'class="'))) {
      return { textContent: 'found', innerHTML: '' };
    }
    return null;
  }
};

global.window = {};

console.log('==================================================================');
console.log('  PROBING CONFLUENCE RADAR DEBLOATED VIEW');
console.log('==================================================================\n');

import('../src/tabs/radar_view.js').then(({ RadarView }) => {
  const radar = new RadarView();
  const testDiv = { innerHTML: '' };
  
  radar.render(testDiv);
  
  console.log('--- TEST 1: Debloated Shell Mounting ---');
  assert(testDiv.innerHTML.includes('radar-debloated'), 'Container has radar-debloated class');
  assert(testDiv.innerHTML.includes('Confluence Radar'), 'Header displays Confluence Radar');
  assert(testDiv.innerHTML.includes('radarCleanSlate'), 'Clean slate container mounted');
  assert(testDiv.innerHTML.includes('GEX/DEX Snapshot Pipeline'), 'Placeholder states snapshot engine');
  console.log('  ✓ PASS: Debloated shell mounted cleanly');

  console.log('\n--- TEST 2: Purged Legacy DOM Elements ---');
  assert(!testDiv.innerHTML.includes('radarTable'), 'Legacy radarTable purged');
  assert(!testDiv.innerHTML.includes('radarInspectorSection'), 'Legacy inspector section purged');
  assert(!testDiv.innerHTML.includes('radarFilterChips'), 'Legacy filter chips purged');
  assert(!testDiv.innerHTML.includes('radarChartSlot'), 'Legacy chart slot purged');
  console.log('  ✓ PASS: All legacy clutter and bloat 100% purged');

  console.log('\n--- TEST 3: Lifecycle Teardown ---');
  radar.destroy();
  assert(testDiv.innerHTML === '', 'destroy() successfully cleared container');
  console.log('  ✓ PASS: Teardown verified');

  console.log('\n==================================================================');
  console.log('  ALL RADAR DEBLOATED TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
}).catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
