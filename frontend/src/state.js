const STORAGE_KEYS = {
  SESSION_TOKEN: 'quant_session_token',
  SESSION_EXPIRES_AT: 'quant_session_expires_at',
  MODEL: 'quant_selected_model',
  GATEWAY_URL: 'quant_gateway_url',
  ACTIVE_TAB: 'quant_active_tab',
  CHAT_HISTORY: 'quant_chat_history',
  SHOW_DIAGNOSTICS: 'quant_show_diagnostics'
};

const _sessionExpiredCallbacks = new Set();

export const AppState = {
  getSessionToken() {
    return localStorage.getItem(STORAGE_KEYS.SESSION_TOKEN) || '';
  },

  setSessionToken(token, expiresAt) {
    if (token) {
      localStorage.setItem(STORAGE_KEYS.SESSION_TOKEN, token.trim());
      if (expiresAt) {
        localStorage.setItem(STORAGE_KEYS.SESSION_EXPIRES_AT, String(expiresAt));
      }
    } else {
      this.clearSession();
    }
  },

  getSessionExpiresAt() {
    const exp = localStorage.getItem(STORAGE_KEYS.SESSION_EXPIRES_AT);
    return exp ? parseInt(exp, 10) : 0;
  },

  isSessionExpired() {
    const exp = this.getSessionExpiresAt();
    if (!exp) return true;
    const now = Math.floor(Date.now() / 1000);
    return now >= exp;
  },

  clearSession() {
    localStorage.removeItem(STORAGE_KEYS.SESSION_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.SESSION_EXPIRES_AT);
  },

  onSessionExpired(callback) {
    if (typeof callback === 'function') {
      _sessionExpiredCallbacks.add(callback);
      return () => _sessionExpiredCallbacks.delete(callback);
    }
  },

  // Legacy helper for backward compatibility
  getPasscode() {
    return this.getSessionToken();
  },

  getModel() {
    return localStorage.getItem(STORAGE_KEYS.MODEL) || 'gemini-3.5-flash-lite';
  },

  setModel(modelId) {
    localStorage.setItem(STORAGE_KEYS.MODEL, modelId);
  },

  getGatewayUrl() {
    const custom = localStorage.getItem(STORAGE_KEYS.GATEWAY_URL);
    if (custom) return custom.replace(/\/+$/, '');
    // In local dev without reverse proxy (e.g. port 3000 or 5173), automatically route to gateway on port 8000
    if (typeof window !== 'undefined' && (window.location.port === '3000' || window.location.port === '5173')) {
      return `http://${window.location.hostname}:8000`;
    }
    if (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin !== 'null') {
      return window.location.origin;
    }
    return '';
  },

  setGatewayUrl(url) {
    localStorage.setItem(STORAGE_KEYS.GATEWAY_URL, url.trim().replace(/\/$/, ''));
  },

  getActiveTab() {
    return localStorage.getItem(STORAGE_KEYS.ACTIVE_TAB) || 'chat';
  },

  setActiveTab(tabId) {
    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, tabId);
  },

  getShowDiagnostics() {
    const val = localStorage.getItem(STORAGE_KEYS.SHOW_DIAGNOSTICS);
    return val === null ? true : val === 'true';
  },

  setShowDiagnostics(enabled) {
    localStorage.setItem(STORAGE_KEYS.SHOW_DIAGNOSTICS, String(enabled));
  },

  getHistory() {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.CHAT_HISTORY);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      console.warn('Failed to parse chat history from localStorage', e);
      return [];
    }
  },

  saveHistory(messages) {
    try {
      localStorage.setItem(STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(messages));
    } catch (e) {
      console.warn('Failed to save chat history to localStorage', e);
    }
  },

  clearHistory() {
    localStorage.removeItem(STORAGE_KEYS.CHAT_HISTORY);
  }
};

export async function fetchWithAuth(url, options = {}) {
  const token = AppState.getSessionToken();
  let headers = options.headers;

  if (typeof Headers !== 'undefined' && headers instanceof Headers) {
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  } else if (Array.isArray(headers)) {
    const hasAuth = headers.some(([k]) => k.toLowerCase() === 'authorization');
    headers = [...headers];
    if (token && !hasAuth) {
      headers.push(['Authorization', `Bearer ${token}`]);
    }
  } else {
    headers = { ...(headers || {}) };
    const hasAuth = Object.keys(headers).some(k => k.toLowerCase() === 'authorization');
    if (token && !hasAuth) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const mergedOptions = {
    ...options,
    headers
  };

  const res = await fetch(url, mergedOptions);

  if (res.status === 401) {
    AppState.clearSession();
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      try {
        const evt = typeof CustomEvent === 'function'
          ? new CustomEvent('quant-session-expired')
          : { type: 'quant-session-expired' };
        window.dispatchEvent(evt);
      } catch (e) {
        // Fallback for mock environments
      }
    }
    _sessionExpiredCallbacks.forEach(cb => {
      try {
        cb();
      } catch (err) {
        console.error('Error in session expired callback:', err);
      }
    });
    throw new Error('SessionExpired: 401 Unauthorized');
  }

  return res;
}
