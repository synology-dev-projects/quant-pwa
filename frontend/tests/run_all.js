/**
 * frontend/tests/run_all.js
 * Consolidated runner for all frontend DOM, component, and layout test suites.
 * Executes all 9 suites sequentially via spawnSync, capturing exit codes,
 * and aggregating metrics into a unified report.
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const testSuites = [
  'test_settings_flow_modal.js',
  'test_cockpit_view.js',
  'test_watchlist_view.js',
  'test_levels_view.js',
  'test_levels_macro_ribbon.js',
  'test_levels_conviction_cards.js',
  'test_vertical_table_ui.js',
  'test_auth_guard.js',
  'audit_layout.js'
];

console.log('==================================================================');
console.log('  RUNNING ALL FRONTEND DOM & LAYOUT TEST SUITES                   ');
console.log('==================================================================\n');

const startTime = Date.now();
let passedCount = 0;

for (const suite of testSuites) {
  const suitePath = path.resolve(__dirname, suite);
  const suiteStart = Date.now();
  console.log(`▶ [${passedCount + 1}/${testSuites.length}] Executing: ${suite}...`);
  
  const res = spawnSync(process.execPath, [suitePath], {
    stdio: 'inherit',
    cwd: path.resolve(__dirname, '..')
  });

  const elapsed = ((Date.now() - suiteStart) / 1000).toFixed(2);

  if (res.status !== 0) {
    console.error(`\n❌ FAILED: ${suite} (exit code ${res.status}) in ${elapsed}s`);
    process.exit(res.status || 1);
  }

  console.log(`✓ PASSED: ${suite} (${elapsed}s)\n`);
  passedCount++;
}

const totalDuration = ((Date.now() - startTime) / 1000).toFixed(2);
console.log('==================================================================');
console.log(`  ALL ${passedCount}/${testSuites.length} TEST SUITES PASSED CLEANLY IN ${totalDuration}s!`);
console.log('==================================================================');
