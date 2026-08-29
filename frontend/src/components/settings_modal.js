import { AppState } from '../state.js';

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
    this.passcodeInput = document.getElementById('passcodeInput');
    this.gatewayUrlInput = document.getElementById('gatewayUrlInput');
    this.diagnosticsToggle = document.getElementById('diagnosticsToggle');

    this.init();
  }

  init() {
    if (!this.modal) return;

    this.forceUpdateBtn?.addEventListener('click', () => this.handleForceUpdate());

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
    this.modal.classList.add('open');
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
    if (this.forceUpdateBtn) {
      this.forceUpdateBtn.disabled = true;
      this.forceUpdateBtn.textContent = '⚡ Purging cache & updating...';
    }

    try {
      // 1. Unregister all active Service Workers
      if ('serviceWorker' in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        for (const reg of registrations) {
          await reg.unregister();
        }
      }

      // 2. Wipe CacheStorage API
      if ('caches' in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }

      // 3. Clear temporary local memory
      localStorage.removeItem('quant_cockpit_recent');
    } catch (e) {
      console.warn('Error during cache purge:', e);
    }

    // 4. Force hard reload with timestamp cache-buster
    const targetUrl = window.location.origin + window.location.pathname + '?_v=' + Date.now();
    window.location.href = targetUrl;
  }
}
