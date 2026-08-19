import { AppState } from '../state.js';

export class LockScreen {
  constructor(onAuthenticated) {
    this.onAuthenticated = onAuthenticated;
    this.overlay = document.getElementById('lockScreen');
    this.form = document.getElementById('lockForm');
    this.passwordInput = document.getElementById('lockPasswordInput');
    this.togglePassBtn = document.getElementById('lockTogglePassBtn');
    this.submitBtn = document.getElementById('lockSubmitBtn');
    this.errorMsg = document.getElementById('lockErrorMsg');
    this.card = document.getElementById('lockCard');

    this.init();
  }

  init() {
    if (!this.overlay) return;

    // Toggle show/hide password
    this.togglePassBtn?.addEventListener('click', () => {
      const isPassword = this.passwordInput.type === 'password';
      this.passwordInput.type = isPassword ? 'text' : 'password';
      this.togglePassBtn.innerHTML = isPassword
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
    });

    // Form submit
    this.form?.addEventListener('submit', (e) => this.handleSubmit(e));

    // Clear error on user typing
    this.passwordInput?.addEventListener('input', () => {
      this.clearError();
    });
  }

  async checkAuthentication() {
    const gatewayBase = AppState.getGatewayUrl() || '';
    
    // 1. Check if auth is required on server
    try {
      const statusRes = await fetch(`${gatewayBase}/api/auth/status`);
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        if (!statusData.auth_required) {
          this.unlock(true);
          return true;
        }
      }
    } catch (e) {
      console.warn('Gateway status check error:', e);
    }

    // 2. Check if active session exists & is not expired locally
    const token = AppState.getSessionToken();
    if (!token || AppState.isSessionExpired()) {
      this.show();
      return false;
    }

    // 3. Verify session token with backend gateway
    try {
      const res = await fetch(`${gatewayBase}/api/auth/verify`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        this.unlock(true);
        return true;
      }
    } catch (e) {
      console.warn('Session verification error:', e);
    }

    // Token invalid or expired
    AppState.clearSession();
    this.show();
    return false;
  }

  show() {
    if (!this.overlay) return;
    this.overlay.classList.remove('hidden', 'unlocked-exit');
    this.overlay.classList.add('visible');
    this.clearError();
    if (this.passwordInput) {
      this.passwordInput.value = '';
      setTimeout(() => this.passwordInput.focus(), 100);
    }
  }

  unlock(immediate = false) {
    if (!this.overlay) return;

    if (immediate) {
      this.overlay.classList.remove('visible');
      this.overlay.classList.add('hidden');
      if (this.onAuthenticated) this.onAuthenticated();
    } else {
      this.overlay.classList.add('unlocked-exit');
      setTimeout(() => {
        this.overlay.classList.remove('visible', 'unlocked-exit');
        this.overlay.classList.add('hidden');
        if (this.onAuthenticated) this.onAuthenticated();
      }, 350);
    }
  }

  async handleSubmit(e) {
    e.preventDefault();
    const password = this.passwordInput?.value?.trim();

    if (!password) {
      this.showError('Please enter your passcode');
      return;
    }

    this.setLoading(true);
    this.clearError();

    const gatewayBase = AppState.getGatewayUrl() || '';
    try {
      const res = await fetch(`${gatewayBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok && data.token) {
        // Save session token (never store raw password)
        AppState.setSessionToken(data.token, data.expires_at);
        this.unlock();
      } else {
        const errorText = data.detail || 'Invalid passcode. Please try again.';
        this.showError(errorText);
        this.shakeCard();
      }
    } catch (err) {
      this.showError('Unable to connect to Gateway. Check connection.');
      this.shakeCard();
    } finally {
      this.setLoading(false);
    }
  }

  showError(message) {
    if (this.errorMsg) {
      this.errorMsg.textContent = message;
      this.errorMsg.classList.add('visible');
    }
  }

  clearError() {
    if (this.errorMsg) {
      this.errorMsg.textContent = '';
      this.errorMsg.classList.remove('visible');
    }
  }

  shakeCard() {
    if (!this.card) return;
    this.card.classList.remove('shake');
    void this.card.offsetWidth; // Trigger DOM reflow
    this.card.classList.add('shake');
  }

  setLoading(isLoading) {
    if (!this.submitBtn) return;
    this.submitBtn.disabled = isLoading;
    const btnText = this.submitBtn.querySelector('.btn-text');
    const spinner = this.submitBtn.querySelector('.btn-spinner');

    if (btnText) btnText.style.display = isLoading ? 'none' : 'inline-block';
    if (spinner) spinner.style.display = isLoading ? 'inline-block' : 'none';
  }
}
