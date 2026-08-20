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
    this.currentAssistantContent = '';
    this.currentToolUiEvents = [];
    this.currentAssistantElement = createMessageElement('assistant', '', metadata);
    this.streamContainer.appendChild(this.currentAssistantElement);
    this.scrollToBottom();
  }

  addToolUiEvent(event) {
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
    if (!this.currentAssistantElement) return;
    this.currentAssistantContent += token;
    
    const contentDiv = this.currentAssistantElement.querySelector('.markdown-body');
    if (contentDiv) {
      let cleaned = this.currentAssistantContent;
      if (this.currentToolUiEvents.length > 0) {
        cleaned = cleaned.replace(/!\[(.*?)Options Chart\]\(.*?\)/gi, '').trim();
      }
      contentDiv.innerHTML = createMessageElement('assistant', cleaned).querySelector('.markdown-body').innerHTML;
    }
    this.scrollToBottom();
  }

  showToolStatus(name, args) {
    if (!this.currentAssistantElement) return;
    
    let pill = this.currentAssistantElement.querySelector('.tool-pill');
    if (!pill) {
      pill = document.createElement('div');
      pill.className = 'tool-pill';
      pill.innerHTML = `<div class="tool-spinner"></div> <span>Querying Synology NAS for ${args?.ticker || 'quant data'}...</span>`;
      this.currentAssistantElement.insertBefore(pill, this.currentAssistantElement.firstChild);
    }
  }

  hideToolStatus() {
    if (!this.currentAssistantElement) return;
    const pill = this.currentAssistantElement.querySelector('.tool-pill');
    if (pill) pill.remove();
  }

  finishAssistantMessage() {
    this.hideToolStatus();
    if (this.currentAssistantContent || this.currentToolUiEvents.length > 0) {
      this.messages.push({
        role: 'assistant',
        content: this.currentAssistantContent,
        toolUiEvents: [...this.currentToolUiEvents]
      });
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
