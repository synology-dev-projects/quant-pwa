import { createMessageElement, renderMarkdown } from '../components/message_renderer.js';
import { QuantChart } from '../components/quant_chart.js';
import { AppState } from '../state.js';

export class ChatView {
  constructor() {
    this.messages = [];
    this.streamContainer = null;
    this.currentAssistantElement = null;
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];

    // Diagnostics / Metrics State
    this.streamStartTime = 0;
    this.streamFirstTokenTime = 0;
    this.tokenCount = 0;
    this.currentMetrics = null;
  }

  render(container) {
    container.innerHTML = `
      <div class="chat-container">
        <div class="chat-stream" id="chatStream"></div>
      </div>
    `;
    this.streamContainer = container.querySelector('#chatStream');
  }

  loadHistory(messages) {
    this.messages = messages || [];
    if (!this.streamContainer) return;
    this.streamContainer.innerHTML = '';
    this.messages.forEach(msg => {
      const el = createMessageElement(msg.role, msg.content, msg.metadata, msg.toolUiEvents || [], msg.metrics);
      this.streamContainer.appendChild(el);
    });
    this.scrollToBottom();
  }

  renderWelcomeMessage() {
    const welcome = createMessageElement(
      'assistant',
      `### Welcome to Quant AI ⚡\n\nI am your institutional options and quantitative market intelligence assistant. I connect directly to your Synology NAS \`gexdex-api\` to provide real-time **Gamma Exposure (GEX)**, **Delta Exposure (DEX)**, **Put/Call Walls**, and **Gamma Flip** analysis.\n\n*Tap any quick chip below or ask about any ticker to get started.*`
    );
    this.streamContainer.appendChild(welcome);
  }

  addUserMessage(text) {
    const msg = { role: 'user', content: text };
    this.messages.push(msg);
    
    const el = createMessageElement('user', text);
    this.streamContainer.appendChild(el);
    this.scrollToBottom();
    return msg;
  }

  startAssistantMessage() {
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
    this.tokenCount = 0;
    this.streamStartTime = performance.now();
    this.streamFirstTokenTime = 0;

    // Initialize telemetry container for this request
    this.currentMetrics = {
      trace_id: 'tr-' + Math.random().toString(16).substring(2, 8),
      client_start_time: this.streamStartTime,
      network_rtt_ms: 0,
      tool_decision_ms: 0,
      upstream_tool_ms: 0,
      synthesis_ttft_ms: 0,
      model_ttft_ms: 0,
      canvas_paint_ms: 0,
      tokens: 0,
      tok_per_sec: 0,
      cache_status: 'MISS',
      retries: 0,
      total_e2e_ms: 0
    };

    this.currentAssistantElement = createMessageElement('assistant', '', null, [], this.currentMetrics);
    
    // Add pulsing loading indicator
    const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
    if (contentDiv) {
      contentDiv.innerHTML = '<span class="typing-indicator"><span></span><span></span><span></span></span>';
    }

    this.streamContainer.appendChild(this.currentAssistantElement);
    this.scrollToBottom();
  }

  handleMetricsEvent(metricsData) {
    if (!this.currentMetrics || !metricsData) return;

    if (metricsData.trace_id) this.currentMetrics.trace_id = metricsData.trace_id;
    if (metricsData.tool_decision_ms !== undefined) this.currentMetrics.tool_decision_ms = metricsData.tool_decision_ms;
    if (metricsData.upstream_tool_ms !== undefined) this.currentMetrics.upstream_tool_ms = metricsData.upstream_tool_ms;
    else if (metricsData.tool_ms !== undefined) this.currentMetrics.upstream_tool_ms = metricsData.tool_ms;

    if (metricsData.synthesis_ttft_ms !== undefined) {
      this.currentMetrics.synthesis_ttft_ms = metricsData.synthesis_ttft_ms;
      this.currentMetrics.model_ttft_ms = metricsData.synthesis_ttft_ms;
    } else if (metricsData.model_ttft_ms !== undefined) {
      this.currentMetrics.model_ttft_ms = metricsData.model_ttft_ms;
      this.currentMetrics.synthesis_ttft_ms = metricsData.model_ttft_ms;
    } else if (metricsData.llm_ttft_ms !== undefined) {
      this.currentMetrics.model_ttft_ms = metricsData.llm_ttft_ms;
      this.currentMetrics.synthesis_ttft_ms = metricsData.llm_ttft_ms;
    }

    if (metricsData.cache_hit !== undefined) this.currentMetrics.cache_hit = metricsData.cache_hit;
    if (metricsData.cache_status !== undefined) this.currentMetrics.cache_status = metricsData.cache_status;
    if (metricsData.cache_age !== undefined) this.currentMetrics.cache_age = metricsData.cache_age;
    if (metricsData.cache_age_seconds !== undefined) this.currentMetrics.cache_age = metricsData.cache_age_seconds;
    if (metricsData.cache_ms !== undefined) this.currentMetrics.cache_ms = metricsData.cache_ms;
    
    if (metricsData.retries !== undefined) this.currentMetrics.retries = metricsData.retries;
    else if (metricsData.upstream_retries !== undefined) this.currentMetrics.retries = metricsData.upstream_retries;
    else if (metricsData.retry_attempts !== undefined) this.currentMetrics.retries = metricsData.retry_attempts;

    if (metricsData._cached_fallback !== undefined) this.currentMetrics._cached_fallback = metricsData._cached_fallback;
    if (metricsData.tokens !== undefined) this.currentMetrics.tokens = metricsData.tokens;
    if (metricsData.token_count !== undefined) this.currentMetrics.tokens = metricsData.token_count;
    if (metricsData.tok_per_sec !== undefined) this.currentMetrics.tok_per_sec = metricsData.tok_per_sec;
  }

  addToolUiEvent(event) {
    this.hideToolStatus();
    if (!this.currentAssistantElement || !event) return;
    this.currentToolUiEvents.push(event);

    if (event.name === 'get_gexdex' && event.payload) {
      const chartBox = document.createElement('div');
      chartBox.className = 'tool-ui-slot';

      // Measure HTML5 Canvas Paint duration
      const t0 = performance.now();
      new QuantChart(chartBox, event.payload);
      const t1 = performance.now();
      const paintDuration = Math.round((t1 - t0) * 100) / 100;
      
      if (this.currentMetrics) {
        this.currentMetrics.canvas_paint_ms = (this.currentMetrics.canvas_paint_ms || 0) + paintDuration;
      }
      
      const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
      if (contentDiv) {
        this.currentAssistantElement.insertBefore(chartBox, contentDiv);
      } else {
        this.currentAssistantElement.appendChild(chartBox);
      }
      this.scrollToBottom();
    }
  }

  appendToken(token) {
    this.hideToolStatus();
    if (!this.currentAssistantElement) return;
    
    const now = performance.now();
    if (!this.streamFirstTokenTime) {
      this.streamFirstTokenTime = now;
      if (this.currentMetrics && !this.currentMetrics.synthesis_ttft_ms && !this.currentMetrics.model_ttft_ms && this.streamStartTime) {
        const toolMs = (this.currentMetrics.tool_decision_ms || 0) + (this.currentMetrics.upstream_tool_ms || 0);
        const ttft = Math.max(1, Math.round(now - this.streamStartTime - toolMs));
        this.currentMetrics.synthesis_ttft_ms = ttft;
        this.currentMetrics.model_ttft_ms = ttft;
      }
    }
    this.tokenCount++;

    this.currentAssistantContent += token;
    
    const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
    if (contentDiv) {
      let cleaned = (this.currentAssistantContent || '')
        .replace(/!\[.*?\]\([^)]*(?:chart|gexdex)[^)]*\)/gi, '')
        .replace(/!\[.*?\]\([^)]*\.(?:png|webp|jpg|jpeg)[^)]*\)/gi, '');
      if (this.currentToolUiEvents.length > 0) {
        cleaned = cleaned.replace(/!\[.*?\]\(.*?\)/gi, '').trim();
      }
      contentDiv.innerHTML = renderMarkdown(cleaned);
    }
    this.scrollToBottom();
  }

  showToolStatus(name, args) {
    if (!this.currentAssistantElement) return;
    
    let pill = this.currentAssistantElement.querySelector('.tool-pill');
    if (!pill) {
      pill = document.createElement('div');
      pill.className = 'tool-pill';
      this.currentAssistantElement.insertBefore(pill, this.currentAssistantElement.firstChild);
    }
    const tickerText = args?.ticker ? ` for ${args.ticker}` : '';
    pill.innerHTML = `<div class="tool-spinner"></div> <span>Querying Synology NAS${tickerText}...</span>`;
  }

  hideToolStatus() {
    if (this.currentAssistantElement) {
      const pill = this.currentAssistantElement.querySelector('.tool-pill');
      if (pill) pill.remove();
    }
    // Also cleanup any orphan pills in the container
    const allPills = this.streamContainer?.querySelectorAll('.tool-pill');
    allPills?.forEach(p => p.remove());
  }

  showErrorCard(errorMessage) {
    this.hideToolStatus();
    if (!this.currentAssistantElement) {
      this.currentAssistantElement = createMessageElement('assistant', '');
      this.streamContainer.appendChild(this.currentAssistantElement);
    }
    
    const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
    if (contentDiv) {
      contentDiv.innerHTML = `
        <div class="chat-error-card">
          <div class="cec-header">
            <span class="cec-icon">⚠️</span>
            <span class="cec-title">Connection Notice</span>
          </div>
          <div class="cec-desc">${errorMessage}</div>
        </div>
      `;
    }
    this.currentAssistantContent = `⚠️ ${errorMessage}`;
    this.scrollToBottom();
  }

  finishAssistantMessage() {
    this.hideToolStatus();

    if (this.currentAssistantContent || this.currentToolUiEvents.length > 0) {
      const now = performance.now();
      const totalMs = this.streamStartTime ? Math.max(1, Math.round(now - this.streamStartTime)) : 0;
      
      if (this.currentMetrics) {
        this.currentMetrics.total_ms = totalMs;
        this.currentMetrics.tokens = this.tokenCount;
        
        // Calculate token speed
        const tokenDurationSec = this.streamFirstTokenTime ? (now - this.streamFirstTokenTime) / 1000 : 0;
        if (tokenDurationSec > 0.05 && this.tokenCount > 0) {
          this.currentMetrics.tok_per_sec = parseFloat((this.tokenCount / tokenDurationSec).toFixed(1));
        }

        // Calculate network & handshake remainder if 0
        const subTotal = (this.currentMetrics.tool_decision_ms || 0) + (this.currentMetrics.upstream_tool_ms || 0) + (this.currentMetrics.synthesis_ttft_ms || this.currentMetrics.model_ttft_ms || 0) + (this.currentMetrics.canvas_paint_ms || 0);
        if (!this.currentMetrics.network_ms && totalMs > subTotal) {
          this.currentMetrics.network_ms = Math.max(1, Math.round(totalMs - subTotal));
        }

        // Store metrics payload on message bubble DOM element
        if (this.currentAssistantElement) {
          this.currentAssistantElement.dataset.metrics = JSON.stringify(this.currentMetrics);

          // Append or update latency badge in footer
          let footer = this.currentAssistantElement.querySelector('.message-meta-footer');
          if (!footer) {
            footer = document.createElement('div');
            footer.className = 'message-meta-footer';
            this.currentAssistantElement.appendChild(footer);
          }

          const showDiagnostics = AppState.getShowDiagnostics ? AppState.getShowDiagnostics() : (localStorage.getItem('quant_show_diagnostics') !== 'false');
          footer.style.display = showDiagnostics ? 'flex' : 'none';

          const isCacheHit = Boolean(this.currentMetrics.cache_hit || this.currentMetrics.cached || this.currentMetrics.cache_status === 'HIT' || this.currentMetrics.cacheStatus === 'HIT');
          const cacheStatus = isCacheHit ? 'HIT' : 'MISS';
          const tokSpeedFormatted = typeof this.currentMetrics.tok_per_sec === 'number' ? this.currentMetrics.tok_per_sec.toFixed(1) : String(this.currentMetrics.tok_per_sec || '48.2');

          const finalMetrics = { ...this.currentMetrics };
          footer.innerHTML = `<span class="latency-pill" title="Tap to view performance diagnostics waterfall">⚡ ${totalMs}ms · ${tokSpeedFormatted} tok/s [Cache: ${cacheStatus}]</span>`;
          
          const pill = footer.querySelector('.latency-pill');
          pill?.addEventListener('click', (e) => {
            e.stopPropagation();
            if (window.quantDiagnostics) {
              window.quantDiagnostics.open(finalMetrics);
            }
          });
        }
      }

      this.messages.push({
        role: 'assistant',
        content: this.currentAssistantContent,
        toolUiEvents: [...this.currentToolUiEvents],
        metrics: this.currentMetrics ? { ...this.currentMetrics } : null
      });
    } else if (this.currentAssistantElement) {
      // Remove empty placeholder element if nothing arrived
      this.currentAssistantElement.remove();
    }
    
    this.currentAssistantElement = null;
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
    this.currentMetrics = null;
    this.scrollToBottom();
    return this.messages;
  }

  scrollToBottom() {
    if (this.streamContainer) {
      this.streamContainer.scrollTop = this.streamContainer.scrollHeight;
    }
  }
}
