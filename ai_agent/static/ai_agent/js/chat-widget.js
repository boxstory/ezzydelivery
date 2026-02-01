/**
 * AI Chat Widget
 * Handles messaging with the AI agent backend via SSE streaming.
 * Works across all dashboards using a prefix-based ID system.
 */

(function () {
  'use strict';

  // --- Helpers ---

  function getCsrfToken() {
    // First try hidden input (works when CSRF_COOKIE_HTTPONLY=True)
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;
    // Fallback to cookie
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function scrollToBottom(container) {
    container.scrollTop = container.scrollHeight;
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // --- Message Rendering ---

  function appendMessage(prefix, text, role) {
    var container = document.getElementById(prefix + '_chat_messages');
    if (!container) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'ai-chat-message ai-chat-message--' + role;

    var content = document.createElement('div');
    content.className = 'ai-chat-message-content';
    content.textContent = text;

    wrapper.appendChild(content);
    container.appendChild(wrapper);
    scrollToBottom(container);

    return content;
  }

  function showTypingIndicator(prefix) {
    var container = document.getElementById(prefix + '_chat_messages');
    if (!container) return null;

    var typing = document.createElement('div');
    typing.className = 'ai-chat-typing';
    typing.id = prefix + '_chat_typing';
    typing.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(typing);
    scrollToBottom(container);
    return typing;
  }

  function removeTypingIndicator(prefix) {
    var el = document.getElementById(prefix + '_chat_typing');
    if (el) el.remove();
  }

  function showError(prefix, message) {
    var container = document.getElementById(prefix + '_chat_messages');
    if (!container) return;

    var errorDiv = document.createElement('div');
    errorDiv.className = 'ai-chat-error';
    errorDiv.textContent = message || 'Something went wrong. Please try again.';
    container.appendChild(errorDiv);
    scrollToBottom(container);
  }

  // --- Toggle ---

  function setupToggle(prefix) {
    var header = document.querySelector('#' + prefix + '_dashboard_section_ai_chat .ai-chat-header');
    var section = document.getElementById(prefix + '_dashboard_section_ai_chat');
    if (!header || !section) return;

    // Restore collapsed state from localStorage
    var storageKey = 'ai_chat_collapsed_' + prefix;
    if (localStorage.getItem(storageKey) === 'true') {
      section.classList.add('collapsed');
    }

    header.addEventListener('click', function () {
      section.classList.toggle('collapsed');
      localStorage.setItem(storageKey, section.classList.contains('collapsed'));
    });
  }

  // --- Streaming Chat ---

  function setInputEnabled(prefix, enabled) {
    var input = document.getElementById(prefix + '_chat_input');
    var btn = document.getElementById(prefix + '_chat_send_btn');
    if (input) input.disabled = !enabled;
    if (btn) btn.disabled = !enabled;
  }

  async function sendMessage(prefix) {
    var input = document.getElementById(prefix + '_chat_input');
    if (!input) return;

    var message = input.value.trim();
    if (!message) return;

    // Show user message and clear input
    appendMessage(prefix, message, 'user');
    input.value = '';
    setInputEnabled(prefix, false);

    // Show typing indicator
    showTypingIndicator(prefix);

    // Get conversation ID from session
    var storageKey = 'ai_chat_conv_' + prefix;
    var convId = sessionStorage.getItem(storageKey) || '';

    // Build request body - only include conversation_id if we have a valid one
    var requestBody = { message: message, channel: 'web' };
    if (convId) {
      requestBody.conversation_id = convId;
    }

    try {
      var response = await fetch('/api/ai-agent/chat/stream/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(requestBody)
      });

      removeTypingIndicator(prefix);

      if (!response.ok) {
        // Fallback to non-streaming endpoint
        await sendMessageFallback(prefix, message, convId, storageKey);
        return;
      }

      // Create assistant message placeholder
      var contentEl = appendMessage(prefix, '', 'assistant');
      var fullText = '';

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      while (true) {
        var result = await reader.read();
        if (result.done) break;

        buffer += decoder.decode(result.value, { stream: true });

        // Parse SSE lines
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line.startsWith('data:')) continue;

          var dataStr = line.substring(5).trim();
          if (!dataStr) continue;

          try {
            var data = JSON.parse(dataStr);

            // Handle different chunk types from the API
            if (data.type === 'text' && data.content) {
              // Text content chunk - append to message
              fullText += data.content;
              contentEl.textContent = fullText;
              scrollToBottom(document.getElementById(prefix + '_chat_messages'));
            } else if (data.type === 'complete' && data.conversation_id) {
              // Stream complete - store conversation ID
              sessionStorage.setItem(storageKey, data.conversation_id);
            } else if (data.type === 'tool_start') {
              // Tool is being called - show indicator
              if (!fullText) {
                contentEl.textContent = 'Looking up information...';
              }
            } else if (data.type === 'tool_result') {
              // Tool finished - clear placeholder if needed
              if (contentEl.textContent === 'Looking up information...') {
                contentEl.textContent = '';
                fullText = '';
              }
            } else if (data.type === 'error') {
              // Remove empty assistant bubble before showing error
              if (!fullText && contentEl && contentEl.parentNode) {
                contentEl.parentNode.remove();
                contentEl = null;
              }
              showError(prefix, data.error || 'Something went wrong.');
            }

            // Also handle legacy/fallback format
            if (data.success !== undefined && data.response) {
              fullText = data.response;
              contentEl.textContent = fullText;
              if (data.conversation_id) {
                sessionStorage.setItem(storageKey, data.conversation_id);
              }
            }
          } catch (e) {
            // Skip unparseable lines
          }
        }
      }

      // If no text was streamed, clean up empty bubble
      if (!fullText && contentEl && contentEl.parentNode) {
        contentEl.parentNode.remove();
      }

    } catch (err) {
      removeTypingIndicator(prefix);
      showError(prefix, 'Connection error. Please check your network and try again.');
    } finally {
      setInputEnabled(prefix, true);
      var inputEl = document.getElementById(prefix + '_chat_input');
      if (inputEl) inputEl.focus();
    }
  }

  // Fallback to non-streaming endpoint
  async function sendMessageFallback(prefix, message, convId, storageKey) {
    try {
      var requestBody = { message: message, channel: 'web' };
      if (convId) {
        requestBody.conversation_id = convId;
      }

      var response = await fetch('/api/ai-agent/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(requestBody)
      });

      var data = await response.json();

      if (data.conversation_id) {
        sessionStorage.setItem(storageKey, data.conversation_id);
      }

      if (data.success && data.response) {
        appendMessage(prefix, data.response, 'assistant');
      } else {
        showError(prefix, data.error || 'Failed to get a response.');
      }
    } catch (err) {
      showError(prefix, 'Connection error. Please try again.');
    } finally {
      setInputEnabled(prefix, true);
    }
  }

  // --- Initialization ---

  function initChatWidget(prefix) {
    setupToggle(prefix);

    var input = document.getElementById(prefix + '_chat_input');
    var sendBtn = document.getElementById(prefix + '_chat_send_btn');

    if (sendBtn) {
      sendBtn.addEventListener('click', function () {
        sendMessage(prefix);
      });
    }

    if (input) {
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage(prefix);
        }
      });
    }
  }

  // Auto-init: find all chat widgets on the page
  function autoInit() {
    var sections = document.querySelectorAll('.ai-chat-section');
    sections.forEach(function (section) {
      var id = section.id || '';
      // Extract prefix: e.g., "workforce_dashboard_section_ai_chat" → "workforce"
      var match = id.match(/^(.+?)_dashboard_section_ai_chat$/);
      if (match) {
        initChatWidget(match[1]);
      }
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  // Also re-init after HTMX swaps (dashboards use HTMX navigation)
  document.addEventListener('htmx:afterSettle', function () {
    autoInit();
  });

})();
