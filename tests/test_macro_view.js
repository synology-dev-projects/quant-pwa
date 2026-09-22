import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const macroJsPath = path.join(__dirname, '../frontend/src/tabs/macro_view.js');
const cockpitJsPath = path.join(__dirname, '../frontend/src/tabs/cockpit_view.js');

const macroCode = fs.readFileSync(macroJsPath, 'utf8');
const cockpitCode = fs.readFileSync(cockpitJsPath, 'utf8');

let errors = [];
function assert(condition, message) {
  if (!condition) {
    errors.push(message);
  }
}

// Check MacroView
assert(macroCode.includes('id="macro-sensitivity-ribbon"'), 'Macro view missing ribbon container');
assert(macroCode.includes('loadData(ticker)'), 'Macro view missing loadData(ticker)');
assert(macroCode.includes('renderSensitivityRibbon'), 'Macro view missing renderSensitivityRibbon');

// Check CockpitView
assert(cockpitCode.includes('class="cockpit-macro-badge"'), 'Cockpit view missing macro badge class');

if (errors.length > 0) {
  console.error('Test failed with ' + errors.length + ' errors:');
  errors.forEach(e => console.error(' - ' + e));
  process.exit(1);
} else {
  console.log('Tests Passed: All requested changes are present.');
}
