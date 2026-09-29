const messagesEl = document.getElementById("chatMessages");
const input = document.getElementById("chatInput");
const sendBtn = document.getElementById("chatSend");
const suggestedRow = document.getElementById("suggestedRow");

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";

  let body = text;
  let citations = [];

  const marker = "__CITATIONS__:";
  const idx = text.indexOf(marker);
  if (idx !== -1) {
    body = text.substring(0, idx).trim();
    const rawCitations = text.substring(idx + marker.length).trim();
    try {
      citations = JSON.parse(rawCitations);
    } catch (e) {
      // Incase JSON is being streamed or partially cut off
    }
  }

  let html = body
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // Convert inline literature tags [Author et al., Year] into clickable knowledge graph chips
  html = html.replace(/\[([A-Z][a-zA-Z\s]+(?:et al\.)?,\s*\d{4})\]/g, (match, p1) => {
    return `<a href="/knowledge-graph" class="chat-citation-tag" title="View in Knowledge Graph">📄 ${p1}</a>`;
  });

  // Convert line breaks
  html = html.replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br/>");
  let output = `<div class="msg-content"><p>${html}</p></div>`;

  // Mainstream LLM-style source pills block at the bottom
  if (citations && citations.length > 0) {
    const pillsHtml = citations.map(c => {
      const doiUrl = c.doi ? `https://doi.org/${encodeURIComponent(c.doi)}` : `/knowledge-graph`;
      const firstAuthor = (c.authors || "").split(",")[0].trim();
      const authorShort = firstAuthor ? `${firstAuthor} et al. (${c.year})` : c.title;
      const journal = c.journal || "Medical Journal";
      const tooltip = `${c.title}\nJournal: ${journal} (${c.year})\nKey finding: ${c.key_findings || ''}`;

      return `
        <a href="${doiUrl}" target="_blank" rel="noopener noreferrer" class="source-pill" title="${escapeHtml(tooltip)}">
          <span class="source-pill-icon">
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
            </svg>
          </span>
          <span class="source-pill-name">${escapeHtml(authorShort)}</span>
          <span class="source-pill-sep">·</span>
          <span class="source-pill-domain">${escapeHtml(journal)}</span>
        </a>
      `;
    }).join("");

    output += `
      <div class="chat-sources-block">
        <div class="chat-sources-label">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
          </svg>
          <span>Sources</span>
        </div>
        <div class="chat-sources-list">
          ${pillsHtml}
        </div>
      </div>
    `;
  }

  return output;
}

function addMessage(role, content) {
  const hint = messagesEl.querySelector(".empty-hint");
  if (hint) hint.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") {
    div.innerHTML = formatMarkdown(content);
  } else {
    div.textContent = content;
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addTypingBubble() {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span>`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function send(prefilledText) {
  const text = (prefilledText !== undefined ? prefilledText : input.value).trim();
  if (!text) return;
  input.value = "";
  sendBtn.disabled = true;
  if (suggestedRow) suggestedRow.remove();
  addMessage("user", text);

  const bubble = addTypingBubble();
  let receivedFirstChunk = false;
  let fullText = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      bubble.textContent = data.error || "Something went wrong.";
      return;
    }

    // Stream plain text chunks straight through -- read them as they arrive
    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunkText = decoder.decode(value, { stream: true });
      if (chunkText) {
        if (!receivedFirstChunk) {
          bubble.innerHTML = "";
          receivedFirstChunk = true;
        }
        fullText += chunkText;
        bubble.innerHTML = formatMarkdown(fullText);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    if (!receivedFirstChunk) {
      bubble.textContent = "Sorry, I didn't get a response.";
    }
  } catch (e) {
    bubble.textContent = "Something went wrong reaching the server.";
  } finally {
    sendBtn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

sendBtn.addEventListener("click", () => send());
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") send();
});

if (suggestedRow) {
  suggestedRow.querySelectorAll(".suggested-chip").forEach((chip) => {
    chip.addEventListener("click", () => send(chip.textContent));
  });
}

// Automatically format history and trigger ?q= if URL parameter is present
document.addEventListener("DOMContentLoaded", () => {
  // Format existing assistant history messages
  if (messagesEl) {
    messagesEl.querySelectorAll(".msg.assistant").forEach(el => {
      if (!el.querySelector(".msg-content")) {
        el.innerHTML = formatMarkdown(el.textContent);
      }
    });
  }

  const urlParams = new URLSearchParams(window.location.search);
  const q = urlParams.get("q");
  if (q) {
    input.value = q;
    send(q);
  }
});