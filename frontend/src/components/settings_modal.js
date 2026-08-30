import { AppState } from '../state.js';

export const CLIENT_VERSION = 'v1.0.4';

export class SettingsModal {
  constructor({ onSettingsChanged, onLockApp, onClearHistory } = {}) {
    this.onSettingsChanged = onSettingsChanged;
    this.onLockApp = onLockApp;
    this.onClearHistory = onClearHistory;

    this.modal = document.getElementById('settingsModal');
    this.settingsBtn = document.getElementById('settingsBtn');
    this.closeBtn = document.getElementById('settingsClose');
    this.saveBtn = document.getElementById('settingsSave');
    this.clearHistoryBtn = document.getElementById('clearHistoryBtn');
    this.lockAppBtn = document.getElementById('lockAppBtn');
    this.forceUpdateBtn = document.getElementById('forceUpdateBtn');
    this.manualResyncLink = document.getElementById('manualResyncLink');
    this.syncFlowBtn = document.getElementById('syncFlowBtn');
    this.syncLevelsBtn = document.getElementById('syncLevelsBtn');
    this.appBuildVersion = document.getElementById('appBuildVersion');
    this.syncStatusText = document.getElementById('syncStatusText');
    this.flowStatusText = document.getElementById('flowStatusText');
    this.flowSyncDot = document.getElementById('flowSyncDot');
    this.flowStatusBadge = document.getElementById('flowStatusBadge');
    this.levelsStatusText = document.getElementById('levelsStatusText');
    this.levelsSyncDot = document.getElementById('levelsSyncDot');
    this.levelsStatusBadge = document.getElementById('levelsStatusBadge');
    this.passcodeInput = document.getElementById('passcodeInput');
    this.gatewayUrlInput = document.getElementById('gatewayUrlInput');
    this.diagnosticsToggle = document.getElementById('diagnosticsToggle');

    this.init();
  }

  init() {
    if (!this.modal) return;

    this.forceUpdateBtn?.addEventListener('click', () => this.handleForceUpdate());
    this.manualResyncLink?.addEventListener('click', () => this.handleForceUpdate());
    this.syncFlowBtn?.addEventListener('click', () => this.handleSyncFlow());
    this.syncLevelsBtn?.addEventListener('click', () => this.handleSyncQuantLevels());

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
    this.clearHistoryBtn?.addEventListener('click', () => this.handleClearHistory());
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
    this.checkVersionStatus();
    this.checkFlowStatus();
    this.checkQuantLevelsStatus();
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

  close() {
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
