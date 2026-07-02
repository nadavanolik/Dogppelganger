// ============================================
// DM Conversation — `/messages/:conversationId`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { realtime } from '../realtime.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { timeAgo } from '../utils.js';

export function renderConversation(params) {
  const user = auth.getCurrentUser();
  if (!user) return;

  const conv = store.getConversation(params.conversationId);
  if (!conv) {
    navigate('/messages');
    return;
  }

  // Check access
  if (!conv.participants.includes(user.id)) {
    navigate('/messages');
    return;
  }

  const otherId = conv.participants.find(p => p !== user.id);
  const other = store.getUser(otherId);

  // Mark as read
  store.markConversationRead(conv.id, user.id);

  // For the bot reply simulation
  store._currentViewUserId = user.id;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  function render() {
    const messages = store.getMessages(conv.id);

    content.innerHTML = `
      <div class="container dm-container">
        <div class="dm-header">
          <a href="#/messages" class="dm-header__back btn btn--icon btn--ghost">
            ${icon('arrowLeft', 20)}
          </a>
          <img src="${other?.avatar || ''}" class="avatar" alt="" />
          <div>
            <div class="dm-header__name">@${other?.username || 'Unknown'}</div>
            <div style="font-size:var(--text-xs);color:var(--color-success);">● Online</div>
          </div>
        </div>

        <div class="dm-messages" id="dm-messages">
          ${messages.map(m => {
            const isMine = m.senderId === user.id;
            return `
              <div class="dm-message ${isMine ? 'dm-message--mine' : 'dm-message--other'}">
                ${!isMine ? `<img src="${other?.avatar || ''}" class="avatar avatar--sm" alt="" />` : ''}
                <div class="dm-message__bubble">${m.body}</div>
                <span class="dm-message__time">${formatTime(m.createdAt)}</span>
              </div>
            `;
          }).join('')}
        </div>

        <div class="dm-composer">
          <button class="btn btn--icon btn--ghost" title="Attach">
            ${icon('paperclip', 18)}
          </button>
          <input type="text" id="dm-input" placeholder="Type a message..." autocomplete="off" />
          <button class="btn btn--primary btn--icon" id="dm-send" title="Send">
            ${icon('send', 18)}
          </button>
        </div>
      </div>
    `;

    // Scroll to bottom
    const messagesEl = document.getElementById('dm-messages');
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // Send message
    const input = document.getElementById('dm-input');
    const sendBtn = document.getElementById('dm-send');

    function sendMessage() {
      const body = input.value.trim();
      if (!body) return;

      store.sendMessage({
        conversationId: conv.id,
        senderId: user.id,
        senderUsername: user.username,
        body,
      });

      input.value = '';
      render();

      // Simulate reply
      realtime.simulateIncomingDM(conv.id, store);
    }

    sendBtn?.addEventListener('click', sendMessage);
    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Focus input
    input?.focus();
  }

  function formatTime(date) {
    const d = new Date(date);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // Listen for incoming messages
  function onDMReceived(data) {
    if (data.conversationId === conv.id) {
      store.markConversationRead(conv.id, user.id);
      render();
    }
  }

  realtime.on('dm_received', onDMReceived);
  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);

  return () => {
    realtime.off('dm_received', onDMReceived);
    store._currentViewUserId = null;
  };
}
