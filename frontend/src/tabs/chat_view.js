import { createMessageElement } from '../components/message_renderer.js';
import { QuantChart } from '../components/quant_chart.js';

export class ChatView {
  constructor() {
    this.messages = [];
    this.streamContainer = null;
    this.currentAssistantElement = null;
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
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
    
    if (this.messages.length === 0) {
      this.renderWelcomeMessage();
    } else {
      this.messages.forEach((msg) => {
        const el = createMessageElement(msg.role, msg.content, msg.metadata, msg.toolUiEvents);
        this.streamContainer.appendChild(el);
      });
      this.scrollToBottom();
    }
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

  startAssistantMessage(metadata = null) {
    this.hideToolStatus();
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
    this.currentAssistantElement = createMessageElement('assistant', '', metadata);
    
    // Immediately show active querying spinner while awaiting response
    const pill = document.createElement('div');
    pill.className = 'tool-pill';
    pill.innerHTML = `<div class="tool-spinner"></div> <span>Analyzing options market data...</span>`;
    this.currentAssistantElement.insertBefore(pill, this.currentAssistantElement.firstChild);

    this.streamContainer.appendChild(this.currentAssistantElement);
    this.scrollToBottom();
  }

  addToolUiEvent(event) {
    this.hideToolStatus();
    if (!this.currentAssistantElement || !event) return;
    this.currentToolUiEvents.push(event);

    if (event.name === 'get_gexdex' && event.payload) {
      const chartBox = document.createElement('div');
      chartBox.className = 'tool-ui-slot';
      new QuantChart(chartBox, event.payload);
      
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
    this.currentAssistantContent += token;
    
    const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
    if (contentDiv) {
      let cleaned = (this.currentAssistantContent || '')
        .replace(/!\[.*?\]\([^)]*(?:chart|gexdex)[^)]*\)/gi, '')
        .replace(/!\[.*?\]\([^)]*\.(?:png|webp|jpg|jpeg)[^)]*\)/gi, '');
      if (this.currentToolUiEvents.length > 0) {
        cleaned = cleaned.replace(/!\[.*?\]\(.*?\)/gi, '').trim();
      }
      contentDiv.innerHTML = createMessageElement('assistant', cleaned, null, this.currentToolUiEvents).querySelector('.markdown-body').innerHTML;
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
      this.messages.push({
        role: 'assistant',
        content: this.currentAssistantContent,
        toolUiEvents: [...this.currentToolUiEvents]
      });
    } else if (this.currentAssistantElement) {
      // Remove empty placeholder element if nothing arrived
      this.currentAssistantElement.remove();
    }
    
    this.currentAssistantElement = null;
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
    this.scrollToBottom();
    return this.messages;
  }

  scrollToBottom() {
    if (this.streamContainer) {
      this.streamContainer.scrollTop = this.streamContainer.scrollHeight;
    }
  }
}
