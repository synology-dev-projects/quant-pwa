import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const htmlPath = path.join(__dirname, '../frontend/index.html');
const cssPath = path.join(__dirname, '../frontend/styles.css');
const jsPath = path.join(__dirname, '../frontend/src/components/settings_modal.js');

const html = fs.readFileSync(htmlPath, 'utf8');
const css = fs.readFileSync(cssPath, 'utf8');
const js = fs.readFileSync(jsPath, 'utf8');

let errors = [];

function assert(condition, message) {
  if (!condition) {
    errors.push(message);
  }
}

// 1. HTML DOM Structure
assert(html.includes('id="pipelineSectionCard"'), 'Missing #pipelineSectionCard container');
assert(html.includes('id="dynamicPipelineList"'), 'Missing #dynamicPipelineList in Settings modal');
assert(html.includes('id="runAllPipelinesBtn"'), 'Missing #runAllPipelinesBtn in Settings modal');

// 2. Backward Compatibility
assert(html.includes('id="flowStatusText"'), 'Missing legacy #flowStatusText fallback');
assert(html.includes('id="levelsStatusText"'), 'Missing legacy #levelsStatusText fallback');
assert(html.includes('id="snapshotStatusText"'), 'Missing legacy #snapshotStatusText fallback');

// 3. CSS Invariants
assert(css.includes('.pipeline-section-card'), 'Missing .pipeline-section-card styling');
assert(css.includes('.pipeline-compact-row'), 'Missing .pipeline-compact-row styling');
assert(css.includes('.btn-pipe-action'), 'Missing .btn-pipe-action styling');
assert(css.includes('.btn-pipe-cascade'), 'Missing .btn-pipe-cascade styling');
assert(css.includes('.btn-pipe-synced'), 'Missing .btn-pipe-synced styling');

// 4. JS Methods & Event Handlers
assert(js.includes('checkPipelinesStatus'), 'SettingsModal missing checkPipelinesStatus method');
assert(js.includes('handleRunPipeline('), 'SettingsModal missing handleRunPipeline method');
assert(js.includes('handleRunPipelineCascade('), 'SettingsModal missing handleRunPipelineCascade method');
assert(js.includes('handleRunAllPipelines('), 'SettingsModal missing handleRunAllPipelines method');
assert(js.includes('this.pipelinePollingTimer'), 'SettingsModal missing pipeline polling timer');

if (errors.length > 0) {
  console.error('❌ Dynamic Pipeline Settings Test failed with ' + errors.length + ' errors:');
  errors.forEach(e => console.error(' - ' + e));
  process.exit(1);
} else {
  console.log('✅ Dynamic Pipeline Settings Test Passed: 100% compliant with DOM, CSS, and JS contracts!');
}
