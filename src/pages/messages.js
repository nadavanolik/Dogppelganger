// ============================================
// Messages Inbox — `/messages`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { timeAgo, truncate } from '../utils.js';

export function renderMessages() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  let showNewModal = false;

  function render() {
    const conversations = store.getConversationsByUser(user.id);

    content.innerHTML = `
      <div class="container" style="max-width:700px;">
        <div class="messages-header">
          <h1 style="font-size:var(--text-3xl);">
            ${icon('messages', 28)} <span class="text-gradient">Messages</span>
          </h1>
          <button class="btn btn--primary" id="new-message-btn">
            ${icon('plus', 16)}
            New Message
          </button>
        </div>

        ${conversations.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state__icon">📨</div>
            <div class="empty-state__title">No conversations yet</div>
            <p style="color:var(--color-text-secondary);">Start a conversation with another user!</p>
          </div>
        ` : `
          <div class="conversation-list">
            ${conversations.map(conv => {
              const otherId = conv.participants.find(p => p !== user.id);
              const other = store.getUser(otherId);
              const unread = conv.unreadCount[user.id] || 0;
              return `
                <div class="conversation-item" data-conv-id="${conv.id}">
                  <img src="${other?.avatar || ''}" class="avatar avatar--lg" alt="" />
                  <div class="conversation-item__info">
                    <div class="conversation-item__name">@${other?.username || 'Unknown'}</div>
                    <div class="conversation-item__preview">${truncate(conv.lastMessage, 60)}</div>
                  </div>
                  <div class="conversation-item__meta">
                    <div class="conversation-item__time">${timeAgo(conv.lastMessageAt)}</div>
                    ${unread > 0 ? `<div class="badge badge--count" style="margin-top:var(--space-1);">${unread}</div>` : ''}
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        `}

        <!-- New message modal -->
        <div class="modal-overlay" id="new-msg-modal" style="display:${showNewModal ? '' : 'none'};">
          <div class="modal">
            <div class="modal__header">
              <h3 class="modal__title">New Message</h3>
              <button class="btn btn--icon btn--ghost" id="modal-close">${icon('x', 20)}</button>
            </div>
            <p style="font-size:var(--text-sm);color:var(--color-text-secondary);margin-bottom:var(--space-4);">
              Choose someone to message:
            </p>
            <div class="recipient-list">
              ${store.getAllUsers().filter(u => u.id !== user.id).map(u => `
                <div class="recipient-item" data-recipient-id="${u.id}">
                  <img src="${u.avatar}" class="avatar avatar--sm" alt="" />
                  <span style="font-weight:500;">@${u.username}</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      </div>
    `;

    // Conversation click
    content.querySelectorAll('.conversation-item').forEach(item => {
      item.addEventListener('click', () => {
        navigate(`/messages/${item.dataset.convId}`);
      });
    });

    // New message modal
    document.getElementById('new-message-btn')?.addEventListener('click', () => {
      showNewModal = true;
      render();
    });

    document.getElementById('modal-close')?.addEventListener('click', () => {
      showNewModal = false;
      render();
    });

    // Recipient click
    content.querySelectorAll('.recipient-item').forEach(item => {
      item.addEventListener('click', () => {
        const recipientId = item.dataset.recipientId;
        const conv = store.createConversation(user.id, recipientId);
        navigate(`/messages/${conv.id}`);
      });
    });
  }

  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
