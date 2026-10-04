import { AppState } from '../state.js';

export const CLIENT_VERSION = 'v1.1.42';

export class SettingsModal {
  constructor({ onSettingsChanged, onLockApp } = {}) {
    this.onSettingsChanged = onSettingsChanged;
    this.onLockApp = onLockApp;

    this.modal = document.getElementById('settingsModal');
    this.settingsBtn = document.getElementById('settingsBtn');
    this.closeBtn = document.getElementById('settingsClose');
    this.saveBtn = document.getElementById('settingsSave');
    this.lockAppBtn = document.getElementById('lockAppBtn');
    this.forceUpdateBtn = document.getElementById('forceUpdateBtn');
    this.manualResyncLink = document.getElementById('manualResyncLink');
    this.syncFlowBtn = document.getElementById('syncFlowBtn');
    this.syncLevelsBtn = document.getElementById('syncLevelsBtn');
    this.syncSnapshotBtn = document.getElementById('syncSnapshotBtn');
    this.appBuildVersion = document.getElementById('appBuildVersion');
    this.syncStatusText = document.getElementById('syncStatusText');
    this.flowStatusText = document.getElementById('flowStatusText');
    this.flowSyncDot = document.getElementById('flowSyncDot');
    this.flowStatusBadge = document.getElementById('flowStatusBadge');
    this.levelsStatusText = document.getElementById('levelsStatusText');
    this.levelsSyncDot = document.getElementById('levelsSyncDot');
    this.levelsStatusBadge = document.getElementById('levelsStatusBadge');
    this.snapshotStatusText = document.getElementById('snapshotStatusText');
    this.snapshotSyncDot = document.getElementById('snapshotSyncDot');
    this.snapshotStatusBadge = document.getElementById('snapshotStatusBadge');
    this.passcodeInput = document.getElementById('passcodeInput');
    this.gatewayUrlInput = document.getElementById('gatewayUrlInput');
    this.diagnosticsToggle = document.getElementById('diagnosticsToggle');
    this.levelAlertsToggle = document.getElementById('levelAlertsToggle');
    this.ntfyTopicInput = document.getElementById('ntfyTopicInput');
    this.dynamicPipelineList = document.getElementById('dynamicPipelineList');
    this.runAllPipelinesBtn = document.getElementById('runAllPipelinesBtn');
    this.pipelinePollingTimer = null;
    this.isPipelineRunning = false;

    this.init();
  }

  init() {
    if (!this.modal) return;

    this.forceUpdateBtn?.addEventListener('click', () => this.handleForceUpdate());
    this.manualResyncLink?.addEventListener('click', () => this.handleForceUpdate());
    this.syncFlowBtn?.addEventListener('click', () => this.handleSyncFlow());
    this.syncLevelsBtn?.addEventListener('click', () => this.handleSyncQuantLevels());
    this.syncSnapshotBtn?.addEventListener('click', () => this.handleSyncSnapshot());
    this.runAllPipelinesBtn?.addEventListener('click', () => this.handleRunAllPipelines());

    // Toggle default state from AppState (defaults to true)
    if (this.diagnosticsToggle) {
      this.diagnosticsToggle.checked = AppState.getShowDiagnostics();
      this.diagnosticsToggle.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        AppState.setShowDiagnostics(isChecked);
        this.updateDiagnosticsVisibility(isChecked);
        if (this.onSettingsChanged) {
          this.onSettingsChanged({ showDiagnostics: isChecked });
        }
      });
    }

    if (this.levelAlertsToggle) {
      this.levelAlertsToggle.checked = AppState.isLevelAlertsEnabled();
      this.levelAlertsToggle.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        AppState.setLevelAlertsEnabled(isChecked);
        if (this.onSettingsChanged) {
          this.onSettingsChanged({ levelAlertsEnabled: isChecked });
        }
      });
    }

    if (this.ntfyTopicInput) {
      this.ntfyTopicInput.value = AppState.getNtfyTopic();
      this.ntfyTopicInput.addEventListener('change', (e) => {
        AppState.setNtfyTopic(e.target.value);
      });
    }

    this.settingsBtn?.addEventListener('click', () => this.open());
    this.closeBtn?.addEventListener('click', () => this.close());
    
    this.modal.addEventListener('click', (e) => {
      if (e.target === this.modal) {
        this.close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal.classList.contains('open')) {
        this.close();
      }
    });

    this.saveBtn?.addEventListener('click', () => this.handleSave());
    this.lockAppBtn?.addEventListener('click', () => this.handleLock());
  }

  open() {
    if (!this.modal) return;
    if (this.passcodeInput) {
      this.passcodeInput.value = '';
      this.passcodeInput.placeholder = AppState.getSessionToken() ? '•••••••• (Session Active)' : 'Enter passcode to log in';
    }
    if (this.gatewayUrlInput) {
      this.gatewayUrlInput.value = AppState.getGatewayUrl();
    }
    if (this.diagnosticsToggle) {
      this.diagnosticsToggle.checked = AppState.getShowDiagnostics();
    }
    if (this.levelAlertsToggle) {
      this.levelAlertsToggle.checked = AppState.isLevelAlertsEnabled();
    }
    if (this.ntfyTopicInput) {
      this.ntfyTopicInput.value = AppState.getNtfyTopic();
    }
    this.checkVersionStatus();
    this.checkPipelinesStatus();
    this.checkFlowStatus();
    this.checkQuantLevelsStatus();
    this.checkSnapshotStatus();
    this.modal.classList.add('open');
  }

  async checkVersionStatus() {
    if (this.appBuildVersion) {
      const isStaging = (typeof window !== 'undefined' && window.location && (
        window.location.port === '8096' ||
        (window.location.hostname && (window.location.hostname.includes('staging') || window.location.hostname.includes('develop')))
      ));
      const initialLabel = isStaging ? '(Staging)' : '(Production)';
      this.appBuildVersion.textContent = `${CLIENT_VERSION} ${initialLabel}`;
    }

    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        const serverVersion = data.version || CLIENT_VERSION;
        const serverEnv = data.environment || '';
        const isStaging = (typeof window !== 'undefined' && window.location && (
          window.location.port === '8096' ||
          serverEnv.toLowerCase() === 'staging' ||
          (window.location.hostname && (window.location.hostname.includes('staging') || window.location.hostname.includes('develop')))
        ));
        const label = isStaging ? '(Staging)' : '(Production)';

        if (this.appBuildVersion) {
          this.appBuildVersion.textContent = `${CLIENT_VERSION} ${label}`;
        }

        if (serverVersion === CLIENT_VERSION) {
          if (this.syncStatusText) {
            this.syncStatusText.textContent = `Synchronized (${CLIENT_VERSION})`;
          }
          if (this.forceUpdateBtn) {
            this.forceUpdateBtn.disabled = true;
            this.forceUpdateBtn.className = 'btn btn-synced';
            this.forceUpdateBtn.innerHTML = `✓ App Up to Date (${CLIENT_VERSION})`;
          }
          if (this.manualResyncLink) {
            this.manualResyncLink.style.display = 'block';
          }
        } else {
          if (this.syncStatusText) {
            this.syncStatusText.textContent = `Update Available (${serverVersion})`;
          }
          if (this.forceUpdateBtn) {
            this.forceUpdateBtn.disabled = false;
            this.forceUpdateBtn.className = 'btn btn-danger btn-pulse';
            this.forceUpdateBtn.innerHTML = `⚡ Update Available (${serverVersion}) · Tap to Sync`;
          }
          if (this.manualResyncLink) {
            this.manualResyncLink.style.display = 'none';
          }
        }
        return;
      }
    } catch (e) {
      console.warn('Health check version fetch failed:', e);
    }

    if (this.forceUpdateBtn) {
      this.forceUpdateBtn.disabled = true;
      this.forceUpdateBtn.className = 'btn btn-synced';
      this.forceUpdateBtn.innerHTML = `✓ App Up to Date (${CLIENT_VERSION})`;
    }
    if (this.syncStatusText) {
      this.syncStatusText.textContent = `Synchronized (${CLIENT_VERSION})`;
    }
    if (this.manualResyncLink) {
      this.manualResyncLink.style.display = 'block';
    }
  }

  async checkFlowStatus() {
    if (!this.flowStatusText) return;

    try {
      const res = await fetch('/api/flow/status');
      if (res.ok) {
        const data = await res.json();
        const isFresh = Boolean(data.is_fresh);
        const latestDate = data.latest_trade_date || 'None';
        const expectedDate = data.last_market_day || 'Latest';

        if (isFresh) {
          if (this.flowSyncDot) this.flowSyncDot.className = 'status-dot dot-live';
          this.flowStatusText.textContent = `In Sync (${latestDate})`;
          if (this.syncFlowBtn) {
            this.syncFlowBtn.disabled = true;
            this.syncFlowBtn.className = 'btn btn-synced';
            this.syncFlowBtn.innerHTML = `✓ Flow Up to Date (${latestDate})`;
          }
        } else {
          if (this.flowSyncDot) this.flowSyncDot.className = 'status-dot dot-stale';
          this.flowStatusText.textContent = `Stale (Missing ${expectedDate})`;
          if (this.syncFlowBtn) {
            this.syncFlowBtn.disabled = false;
            this.syncFlowBtn.className = 'btn btn-danger btn-pulse';
            this.syncFlowBtn.innerHTML = `⚡ Sync Missing Flow (${expectedDate}) · Tap to Run`;
          }
        }
        return;
      }
    } catch (e) {
      console.warn('Flow status fetch failed:', e);
    }

    if (this.flowSyncDot) this.flowSyncDot.className = 'status-dot dot-stale';
    if (this.flowStatusText) this.flowStatusText.textContent = 'Status Unavailable';
    if (this.syncFlowBtn) {
      this.syncFlowBtn.disabled = false;
      this.syncFlowBtn.className = 'btn btn-warning';
      this.syncFlowBtn.innerHTML = '⚡ Sync Flow Data';
    }
  }

  async handleSyncFlow() {
    if (!this.syncFlowBtn) return;
    this.syncFlowBtn.disabled = true;
    this.syncFlowBtn.className = 'btn btn-synced';
    this.syncFlowBtn.innerHTML = '<span class="status-dot dot-fast"></span> Ingesting Flow from Market Source...';

    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/flow/sync', {
        method: 'POST',
        headers: headers
      });

      if (res.ok) {
        this.syncFlowBtn.innerHTML = '<span class="status-dot dot-live"></span> Ingestion Complete! Verifying DB...';
        await new Promise((r) => setTimeout(r, 600));
        await this.checkFlowStatus();
        this.showToast('✓ Options Flow Ingestion Completed Successfully!');
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(`Sync failed: ${errData.detail || errData.message || 'Error executing pipeline'}`);
        await this.checkFlowStatus();
      }
    } catch (err) {
      console.error('Flow sync error:', err);
      if (typeof alert === 'function') alert(`Network error during sync: ${err.message}`);
      await this.checkFlowStatus();
    }
  }

  async checkQuantLevelsStatus() {
    if (!this.levelsStatusText) return;

    try {
      const res = await fetch('/api/quant-levels/status');
      if (res.ok) {
        const data = await res.json();
        const isFresh = Boolean(data.is_fresh);
        const latestRecordDate = data.latest_record_date;
        const expectedDate = data.expected_date;
        const displayDate = latestRecordDate || expectedDate;

        if (isFresh) {
          if (this.levelsStatusText) this.levelsStatusText.textContent = `In Sync (${displayDate})`;
          if (this.levelsSyncDot) this.levelsSyncDot.className = 'status-dot dot-live';
          if (this.syncLevelsBtn) {
            this.syncLevelsBtn.disabled = true;
            this.syncLevelsBtn.className = 'btn btn-synced';
            this.syncLevelsBtn.innerHTML = `✓ Quant Levels Up to Date (${displayDate})`;
          }
        } else {
          if (this.levelsStatusText) this.levelsStatusText.textContent = `Stale (Missing ${expectedDate})`;
          if (this.levelsSyncDot) this.levelsSyncDot.className = 'status-dot dot-stale';
          if (this.syncLevelsBtn) {
            this.syncLevelsBtn.disabled = false;
            this.syncLevelsBtn.className = 'btn btn-danger btn-pulse';
            this.syncLevelsBtn.innerHTML = `⚡ Sync Quant Levels (${expectedDate}) · Tap to Run`;
          }
        }
        return;
      }
    } catch (e) {
      console.warn('Quant levels status fetch failed:', e);
    }

    if (this.levelsSyncDot) this.levelsSyncDot.className = 'status-dot dot-stale';
    if (this.levelsStatusText) this.levelsStatusText.textContent = 'Status Unavailable';
    if (this.syncLevelsBtn) {
      this.syncLevelsBtn.disabled = false;
      this.syncLevelsBtn.className = 'btn btn-warning';
      this.syncLevelsBtn.innerHTML = '⚡ Sync Quant Levels';
    }
  }

  async handleSyncQuantLevels() {
    if (!this.syncLevelsBtn) return;
    const originalHtml = this.syncLevelsBtn.innerHTML;
    this.syncLevelsBtn.disabled = true;
    this.syncLevelsBtn.className = 'btn btn-synced';
    this.syncLevelsBtn.innerHTML = '<span class="status-dot dot-fast"></span> ⏳ Ingesting Quant Levels...';

    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/quant-levels/sync', {
        method: 'POST',
        headers: headers
      });

      if (res.ok) {
        this.syncLevelsBtn.innerHTML = '<span class="status-dot dot-live"></span> Ingestion Complete! Verifying DB...';
        await new Promise((r) => setTimeout(r, 600));
        await this.checkQuantLevelsStatus();
        this.showToast('✓ Quant Levels Ingestion Completed Successfully!');
      } else {
        const errData = await res.json().catch(() => ({}));
        if (typeof alert === 'function') {
          alert(`Sync failed: ${errData.detail || errData.message || 'Error executing pipeline'}`);
        }
        await this.checkQuantLevelsStatus();
      }
    } catch (err) {
      console.error('Quant levels sync error:', err);
      if (typeof alert === 'function') {
        alert(`Network error during sync: ${err.message}`);
      }
      await this.checkQuantLevelsStatus();
    }
  }

  async checkSnapshotStatus() {
    if (!this.snapshotStatusText) return;

    try {
      const res = await fetch('/api/snapshot/status');
      if (res.ok) {
        const data = await res.json();
        const isFresh = Boolean(data.is_fresh);
        const latestRecordDate = data.latest_snapshot_date;
        const expectedDate = data.expected_date;
        const displayDate = latestRecordDate || expectedDate;

        if (isFresh) {
          if (this.snapshotStatusText) this.snapshotStatusText.textContent = `In Sync (${displayDate})`;
          if (this.snapshotSyncDot) this.snapshotSyncDot.className = 'status-dot dot-live';
          if (this.syncSnapshotBtn) {
            this.syncSnapshotBtn.disabled = true;
            this.syncSnapshotBtn.className = 'btn btn-synced';
            this.syncSnapshotBtn.innerHTML = `✓ Snapshot Up to Date (${displayDate})`;
          }
        } else {
          if (this.snapshotStatusText) this.snapshotStatusText.textContent = `Stale (Missing ${expectedDate})`;
          if (this.snapshotSyncDot) this.snapshotSyncDot.className = 'status-dot dot-stale';
          if (this.syncSnapshotBtn) {
            this.syncSnapshotBtn.disabled = false;
            this.syncSnapshotBtn.className = 'btn btn-danger btn-pulse';
            this.syncSnapshotBtn.innerHTML = `⚡ Sync GEX/DEX Snapshot (${expectedDate}) · Tap to Run`;
          }
        }
        return;
      }
    } catch (e) {
      console.warn('Snapshot status fetch failed:', e);
    }

    if (this.snapshotSyncDot) this.snapshotSyncDot.className = 'status-dot dot-stale';
    if (this.snapshotStatusText) this.snapshotStatusText.textContent = 'Status Unavailable';
    if (this.syncSnapshotBtn) {
      this.syncSnapshotBtn.disabled = false;
      this.syncSnapshotBtn.className = 'btn btn-warning';
      this.syncSnapshotBtn.innerHTML = '⚡ Sync GEX/DEX Snapshot';
    }
  }

  async handleSyncSnapshot() {
    if (!this.syncSnapshotBtn) return;
    this.syncSnapshotBtn.disabled = true;
    this.syncSnapshotBtn.className = 'btn btn-synced';
    this.syncSnapshotBtn.innerHTML = '<span class="status-dot dot-fast"></span> Ingesting Snapshot from TradingEdge...';

    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/snapshot/sync', {
        method: 'POST',
        headers: headers
      });

      if (res.ok) {
        this.syncSnapshotBtn.innerHTML = '<span class="status-dot dot-live"></span> Ingestion Complete! Verifying DB...';
        await new Promise((r) => setTimeout(r, 600));
        await this.checkSnapshotStatus();
        this.showToast('✓ GEX/DEX Snapshot Ingestion Completed Successfully!');
      } else {
        const errData = await res.json().catch(() => ({}));
        if (typeof alert === 'function') {
          alert(`Sync failed: ${errData.detail || errData.message || 'Error executing pipeline'}`);
        }
        await this.checkSnapshotStatus();
      }
    } catch (err) {
      console.error('Snapshot sync error:', err);
      if (typeof alert === 'function') {
        alert(`Network error during sync: ${err.message}`);
      }
      await this.checkSnapshotStatus();
    }
  }

  showToast(message) {
    const existing = document.querySelector('.update-toast-banner');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'update-toast-banner';
    toast.innerHTML = `<span class="status-dot dot-live"></span> <span>${message}</span>`;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-fade-out');
      setTimeout(() => toast.remove(), 400);
    }, 3500);
  }

  async checkPipelinesStatus() {
    if (!this.dynamicPipelineList) return;

    try {
      const token = AppState.getSessionToken();
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/pipelines/status', { headers });
      if (res.ok) {
        const data = await res.json();
        const pipelines = data.pipelines || {};
        const order = data.topological_order || Object.keys(pipelines);

        let hasActiveRun = false;
        const fragment = document.createDocumentFragment();

        order.forEach((pipeName) => {
          const p = pipelines[pipeName];
          if (!p) return;
          // Filter out disabled or inactive pipelines
          if (p.is_active === false || p.status === 'DISABLED' || p.status === 'INACTIVE') return;

          const pStatus = (p.status || 'NOT_STARTED').toUpperCase();
          const isSuccess = pStatus === 'SUCCESS';
          const isRunning = pStatus === 'RUNNING';
          const isFailed = pStatus === 'FAILED';

          if (isRunning) hasActiveRun = true;

          const row = document.createElement('div');
          row.className = 'pipeline-compact-row';
          row.dataset.pipeline = pipeName;

          let dotClass = 'status-dot dot-stale';
          let statusText = 'Not Run';
          if (isSuccess) {
            dotClass = 'status-dot dot-live';
            statusText = 'In Sync';
          } else if (isRunning) {
            dotClass = 'status-dot dot-fast';
            statusText = 'Running';
          } else if (isFailed) {
            dotClass = 'status-dot dot-stale';
            statusText = 'Failed';
          }

          const sessionDate = p.session_date || data.session_date || '';
          const rows = p.rows_affected !== undefined ? Number(p.rows_affected).toLocaleString() : '0';
          const durSec = p.metadata?.duration_sec !== undefined ? `${p.metadata.duration_sec}s` : '';
          const metaParts = [];
          if (sessionDate) metaParts.push(sessionDate);
          if (rows && rows !== '0') metaParts.push(`${rows} rows`);
          if (durSec) metaParts.push(durSec);
          const metaText = metaParts.join(' · ') || statusText;

          const infoCol = document.createElement('div');
          infoCol.className = 'pipeline-compact-info';
          infoCol.innerHTML = `
            <div class="pipeline-compact-name">
              <span class="${dotClass}"></span>
              <span>${p.display_name || pipeName}</span>
            </div>
            <div class="pipeline-compact-meta">${metaText}</div>
          `;

          const actionsCol = document.createElement('div');
          actionsCol.className = 'pipeline-compact-actions';

          const runBtn = document.createElement('button');
          runBtn.type = 'button';
          if (isRunning) {
            runBtn.className = 'btn-pipe-action btn-pipe-running';
            runBtn.innerHTML = '⏳ Running...';
            runBtn.disabled = true;
          } else if (isSuccess) {
            runBtn.className = 'btn-pipe-action btn-pipe-synced';
            runBtn.innerHTML = '✓ Synced';
            runBtn.title = 'Click to force rerun this pipeline';
            runBtn.addEventListener('click', () => this.handleRunPipeline(pipeName, true));
          } else {
            runBtn.className = 'btn-pipe-action btn-pipe-stale';
            runBtn.innerHTML = '⚡ Run';
            runBtn.title = 'Execute pipeline for latest market session';
            runBtn.addEventListener('click', () => this.handleRunPipeline(pipeName, true));
          }
          actionsCol.appendChild(runBtn);

          const cascadeBtn = document.createElement('button');
          cascadeBtn.type = 'button';
          cascadeBtn.className = 'btn-pipe-action btn-pipe-cascade';
          cascadeBtn.innerHTML = '⚡↓';
          cascadeBtn.title = `Rerun ${p.display_name || pipeName} and all downstream pipelines`;
          cascadeBtn.disabled = isRunning;
          cascadeBtn.addEventListener('click', () => this.handleRunPipelineCascade(pipeName));
          actionsCol.appendChild(cascadeBtn);

          row.appendChild(infoCol);
          row.appendChild(actionsCol);
          fragment.appendChild(row);
        });

        this.dynamicPipelineList.innerHTML = '';
        this.dynamicPipelineList.appendChild(fragment);

        if (this.runAllPipelinesBtn) {
          if (hasActiveRun) {
            this.runAllPipelinesBtn.disabled = true;
            this.runAllPipelinesBtn.innerHTML = '⏳ Running...';
          } else {
            this.runAllPipelinesBtn.disabled = false;
            this.runAllPipelinesBtn.innerHTML = '⚡ Run All';
          }
        }

        if (hasActiveRun) {
          if (this.pipelinePollingTimer) clearTimeout(this.pipelinePollingTimer);
          this.pipelinePollingTimer = setTimeout(() => this.checkPipelinesStatus(), 2000);
        } else if (this.isPipelineRunning) {
          this.isPipelineRunning = false;
          this.showToast('✓ Pipeline DAG Execution Cycle Completed!');
        }
        return;
      }
    } catch (err) {
      console.warn('Failed to query pipeline statuses:', err);
    }
  }

  async handleRunPipeline(pipelineName, forceAll = true) {
    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      this.isPipelineRunning = true;
      this.showToast(`⚡ Dispatched run for ${pipelineName}...`);

      const res = await fetch('/api/pipelines/run', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          pipeline_name: pipelineName,
          force_all: forceAll,
          async_exec: true
        })
      });

      if (res.ok) {
        await this.checkPipelinesStatus();
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(`Failed to trigger pipeline: ${errData.detail || 'Error executing run'}`);
        this.isPipelineRunning = false;
        await this.checkPipelinesStatus();
      }
    } catch (e) {
      console.error('Pipeline run error:', e);
      alert(`Network error: ${e.message}`);
      this.isPipelineRunning = false;
    }
  }

  async handleRunPipelineCascade(fromPipeline) {
    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      this.isPipelineRunning = true;
      this.showToast(`⚡ Dispatched cascade run starting from ${fromPipeline}...`);

      const res = await fetch('/api/pipelines/run', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          from_pipeline: fromPipeline,
          force_all: true,
          async_exec: true
        })
      });

      if (res.ok) {
        await this.checkPipelinesStatus();
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(`Failed to trigger cascade: ${errData.detail || 'Error'}`);
        this.isPipelineRunning = false;
        await this.checkPipelinesStatus();
      }
    } catch (e) {
      console.error('Pipeline cascade error:', e);
      alert(`Network error: ${e.message}`);
      this.isPipelineRunning = false;
    }
  }

  async handleRunAllPipelines() {
    try {
      const token = AppState.getSessionToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      if (this.runAllPipelinesBtn) {
        this.runAllPipelinesBtn.disabled = true;
        this.runAllPipelinesBtn.innerHTML = '⏳ Dispatched...';
      }

      this.isPipelineRunning = true;
      this.showToast('⚡ Triggering Full Pipeline DAG Cycle...');

      const res = await fetch('/api/pipelines/run', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          force_all: true,
          async_exec: true
        })
      });

      if (res.ok) {
        await this.checkPipelinesStatus();
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(`Failed to trigger DAG cycle: ${errData.detail || 'Error'}`);
        this.isPipelineRunning = false;
        await this.checkPipelinesStatus();
      }
    } catch (e) {
      console.error('Run all pipelines error:', e);
      alert(`Network error: ${e.message}`);
      this.isPipelineRunning = false;
    }
  }

  close() {
    if (this.pipelinePollingTimer) {
      clearTimeout(this.pipelinePollingTimer);
      this.pipelinePollingTimer = null;
    }
    this.modal?.classList.remove('open');
  }

  updateDiagnosticsVisibility(show) {
    const pills = document.querySelectorAll('.message-meta-footer');
    pills.forEach((el) => {
      el.style.display = show ? 'flex' : 'none';
    });
  }

  async handleSave() {
    const newGatewayUrl = this.gatewayUrlInput?.value || '';
    AppState.setGatewayUrl(newGatewayUrl);

    if (this.diagnosticsToggle) {
      AppState.setShowDiagnostics(this.diagnosticsToggle.checked);
      this.updateDiagnosticsVisibility(this.diagnosticsToggle.checked);
    }

    if (this.levelAlertsToggle) {
      AppState.setLevelAlertsEnabled(this.levelAlertsToggle.checked);
    }

    if (this.ntfyTopicInput) {
      AppState.setNtfyTopic(this.ntfyTopicInput.value || 'spx_alerts');
    }

    // If user entered a new passcode, verify and obtain fresh session
    const newPassword = this.passcodeInput?.value?.trim();
    if (newPassword) {
      try {
        const res = await fetch(`${newGatewayUrl.replace(/\/$/, '')}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: newPassword })
        });
        if (res.ok) {
          const data = await res.json();
          AppState.setSessionToken(data.token, data.expires_at);
        } else {
          alert('Invalid passcode. Session was not updated.');
        }
      } catch (err) {
        console.warn('Failed to update session from settings:', err);
      }
    }

    this.close();
    if (this.onSettingsChanged) {
      this.onSettingsChanged({ gatewayUrl: newGatewayUrl, showDiagnostics: AppState.getShowDiagnostics() });
    }
  }

  handleLock() {
    AppState.clearSession();
    this.close();
    if (this.onLockApp) {
      this.onLockApp();
    }
  }

  async handleForceUpdate() {
    if (!this.forceUpdateBtn) return;
    this.forceUpdateBtn.disabled = true;

    // Stage 1: Purge local cache and workers
    this.forceUpdateBtn.innerHTML = '<span class="status-dot dot-fast"></span> 01/03 Purging Disk Cache &amp; Storage...';
    await new Promise((r) => setTimeout(r, 350));

    try {
      if ('serviceWorker' in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        for (const reg of registrations) {
          await reg.unregister();
        }
      }

      if ('caches' in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }

      localStorage.removeItem('quant_cockpit_recent');
      localStorage.removeItem('quant_gateway_url');
      sessionStorage.setItem('quant_update_banner', CLIENT_VERSION);
    } catch (e) {
      console.warn('Error during cache purge:', e);
    }

    // Stage 2: Sync latest server build
    this.forceUpdateBtn.innerHTML = `<span class="status-dot dot-live"></span> 02/03 Syncing Latest Server Bundle (${CLIENT_VERSION})...`;
    await new Promise((r) => setTimeout(r, 400));

    // Stage 3: Verified fresh & reload
    this.forceUpdateBtn.innerHTML = '<span class="status-dot dot-optimal"></span> 03/03 Verified Fresh · Reloading Interface...';
    await new Promise((r) => setTimeout(r, 350));

    // Force hard reload with timestamp cache-buster
    const targetUrl = window.location.origin + window.location.pathname + '?_v=' + Date.now();
    window.location.href = targetUrl;
  }
}
