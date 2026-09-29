const messagesEl = document.getElementById("chatMessages");
const input = document.getElementById("chatInput");
const sendBtn = document.getElementById("chatSend");
const suggestedRow = document.getElementById("suggestedRow");

function addMessage(role, content) {
  const hint = messagesEl.querySelector(".empty-hint");
  if (hint) hint.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
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

    // Groq streams plain text chunks straight through -- read them as they arrive
    // and grow the bubble in place, instead of waiting for the full reply.
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
        bubble.textContent = fullText;
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