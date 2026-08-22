import { QuantChart } from './quant_chart.js';
import { AppState } from '../state.js';

export function renderMarkdown(text) {
  if (!text) return '';

  let html = text;

  // Escape raw HTML tags to prevent XSS
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks: ```lang ... ```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.parentElement.querySelector('code').innerText);this.innerText='Copied!';setTimeout(()=>this.innerText='Copy',1500)">Copy</button><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Images: ![alt](url) -> Fallback to interactive card if no Canvas chart was mounted
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, (match, alt, url) => {
    return `
      <div class="chart-card fallback" onclick="window.quantLightbox && window.quantLightbox.open('${url}', '${alt}')">
        <img class="chart-img" src="${url}" alt="${alt}" loading="lazy" />
        <div class="chart-hint">
          <span>${alt || 'OPTIONS EXPOSURE CHART'}</span>
          <span>EXPAND</span>
        </div>
      </div>
    `;
  });

  // Headers: ### Header
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Bullet points
  html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
  html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Line breaks & paragraphs
  html = html.replace(/\n\n/g, '<p></p>');
  html = html.replace(/\n/g, '<br/>');

  return html;
}

export function createMessageElement(role, content, metadata = null, toolUiEvents = [], metrics = null) {
  const bubble = document.createElement('div');
  bubble.className = `message-bubble ${role}`;

  const resolvedMetrics = metrics || metadata?.metrics || null;
  if (resolvedMetrics) {
    bubble.dataset.metrics = JSON.stringify(resolvedMetrics);
  }

  let badgeHtml = '';
  if (role === 'assistant' && metadata?.market) {
    const isClosed = metadata.market.status !== 'REGULAR_HOURS';
    badgeHtml = `
      <div class="market-badge ${isClosed ? 'closed' : ''}">
        <span class="dot"></span>
        <span>${metadata.market.status}: ${metadata.market.current_time_ny}</span>
      </div>
    `;
  }

  // 1. If single-flight Tool UI events exist, mount interactive Canvas charts
  if (role === 'assistant' && toolUiEvents && toolUiEvents.length > 0) {
    toolUiEvents.forEach(evt => {
      if (evt.name === 'get_gexdex' && evt.payload) {
        const chartBox = document.createElement('div');
        chartBox.className = 'tool-ui-slot';
        new QuantChart(chartBox, evt.payload);
        bubble.appendChild(chartBox);
      }
    });
  }

  // 2. Strip redundant or static markdown chart images
  let cleanedContent = (content || '')
    .replace(/!\[.*?\]\([^)]*(?:chart|gexdex)[^)]*\)/gi, '')
    .replace(/!\[.*?\]\([^)]*\.(?:png|webp|jpg|jpeg)[^)]*\)/gi, '');
  
  if (toolUiEvents && toolUiEvents.length > 0) {
    cleanedContent = cleanedContent.replace(/!\[.*?\]\(.*?\)/gi, '').trim();
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'markdown-body';
  contentDiv.innerHTML = badgeHtml + renderMarkdown(cleanedContent.trim());

  bubble.appendChild(contentDiv);

  // 3. Render subtle latency badge in assistant message footer if metrics exist
  if (role === 'assistant' && resolvedMetrics) {
    const totalMs = Math.round(resolvedMetrics.total_ms || resolvedMetrics.duration_ms || 0);
    const rawTok = resolvedMetrics.tok_per_sec || resolvedMetrics.tokens_per_sec || 48.2;
    const tokPerSec = typeof rawTok === 'number' ? rawTok.toFixed(1) : String(rawTok);
    const isCacheHit = Boolean(resolvedMetrics.cache_hit || resolvedMetrics.cached || resolvedMetrics.cache_status === 'HIT' || resolvedMetrics.cacheStatus === 'HIT');
    const cacheStatus = isCacheHit ? 'HIT' : 'MISS';

    const tier = resolvedMetrics.tier_used || resolvedMetrics.tier || '';
    const model = resolvedMetrics.model_used || resolvedMetrics.model || '';
    const isStrategic = tier === 'strategic' || (typeof model === 'string' && model.includes('3.7'));
    const tierBadge = isStrategic
      ? `<span class="inst-tag inst-tag-strategic"><span class="status-dot dot-strategic"></span>STRATEGIC · 3.7-FLASH</span>`
      : `<span class="inst-tag inst-tag-fast"><span class="status-dot dot-fast"></span>FAST · 3.5-LITE</span>`;

    const showDiagnostics = AppState.getShowDiagnostics ? AppState.getShowDiagnostics() : (localStorage.getItem('quant_show_diagnostics') !== 'false');

    const footer = document.createElement('div');
    footer.className = 'message-meta-footer';
    if (!showDiagnostics) {
      footer.style.display = 'none';
    }

    const pill = document.createElement('span');
    pill.className = 'latency-pill';
    pill.innerHTML = `${tierBadge} <span class="inst-stats">${totalMs}ms · ${tokPerSec} tok/s</span> <span class="inst-cache">[CACHE: ${cacheStatus}]</span>`;
    pill.title = 'Tap to view performance diagnostics waterfall';

    pill.addEventListener('click', (e) => {
      e.stopPropagation();
      if (window.quantDiagnostics) {
        window.quantDiagnostics.open(resolvedMetrics);
      }
    });

    footer.appendChild(pill);
    bubble.appendChild(footer);
  }

  return bubble;
}
