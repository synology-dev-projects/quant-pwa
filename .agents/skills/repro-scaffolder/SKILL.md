---
name: repro-scaffolder
description: >-
  Scaffolds isolated in-situ reproduction tests (pytest and node.js) in seconds
  to satisfy the mandatory RED Gate of the Bug Remediation Protocol.
  Use when reproducing a bug, setting up a failing test, or running /repro.
---

# ⚡ In-Situ Reproduction Scaffolder (`/repro`, `/test-repro`)

When a bug or defect is reported, **never modify source code first**. Use this skill to instantly scaffold a failing reproduction test that captures the authentic failure trace in-situ.

---

## 1. Backend FastAPI / Pytest Scaffolder Recipe

Create `gateway/tests/test_reproduce_<issue_slug>.py` using this template:

```python
import pytest
from datetime import datetime, date
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_reproduce_<issue_slug>():
    """
    REPRODUCTION TEST: <Description of bug>
    Expected: <Expected behavior>
    Actual:   <Failing behavior prior to patch>
    """
    # 1. Arrange: set up target state / parameters / fixtures
    target_date = "2026-09-08"
    
    # 2. Mock external database or API boundaries if necessary
    mock_df = pd.DataFrame([{
        "col1": "val1"
    }])
    
    with patch("common_lib.connectors.postgres.sql", return_value=mock_df):
        # 3. Act: hit the exact endpoint or function under test
        response = client.get(f"/api/target-route?date={target_date}")
        assert response.status_code == 200
        data = response.json()
        
        # 4. Assert: express the expected condition that FAILS before the fix
        assert data["expected_field"] == "expected_value", (
            f"Expected 'expected_value', got {data.get('expected_field')}"
        )
```

---

## 2. Frontend DOM / Vanilla JS Scaffolder Recipe

Create `frontend/tests/test_reproduce_<issue_slug>.js` using this template:

```javascript
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM(`<!DOCTYPE html><html><body>
  <div id="targetContainer"></div>
</body></html>`, { url: "http://localhost:3000" });

global.window = dom.window;
global.document = dom.window.document;
global.HTMLElement = dom.window.HTMLElement;

async function runReproduction() {
  console.log('--- REPRODUCING: <issue_slug> ---');
  
  // 1. Arrange: import component and mount
  const container = document.getElementById('targetContainer');
  
  // 2. Act: invoke rendering or user action
  // const component = new TargetComponent(container);
  // component.render();

  // 3. Assert: test expected DOM element, text, or class
  const target = container.querySelector('.expected-element');
  assert(target, 'Target element must be mounted in DOM');
  assert.strictEqual(target.textContent, 'Expected Text');
  
  console.log('  ✓ PASS: Issue resolved.');
}

runReproduction().catch(err => {
  console.error('❌ REPRODUCTION CONFIRMED FAILED:', err.message);
  process.exit(1);
});
```

---

## 3. Immediate Protocol Graph Verification Loop

Once the test is scaffolded, immediately execute:

```bash
# Verify the test fails (exit code != 0)
python scripts/protocol_graph.py red --test gateway/tests/test_reproduce_<issue_slug>.py

# Apply minimal fix...

# Verify the test passes (exit code 0)
python scripts/protocol_graph.py green
```
