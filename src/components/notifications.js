// ============================================
// Notifications dropdown component
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { realtime } from '../realtime.js';
import { icon } from '../icons.js';
import { timeAgo } from '../utils.js';
import { navigate } from '../router.js';

function getNotifIcon(type) {
  switch (type) {
    case 'match_ready': return icon('paw', 16);
    case 'dm_received': return icon('messages', 16);
    case 'post_reaction': return icon('thumbsUp', 16);
    default: return icon('bell', 16);
  }
}

function getNotifRoute(notif) {
  switch (notif.type) {
    case 'match_ready': return `/result/${notif.targetId}`;
    case 'dm_received': return `/messages/${notif.targetId}`;
    case 'post_reaction': return `/forum/post/${notif.targetId}`;
    default: return '/dashboard';
  }
}

export function renderNotificationsDropdown() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const menu = document.getElementById('notif-menu');
  const badge = document.getElementById('notif-badge');
  if (!menu || !badge) return;

  function updateBadge() {
    const count = store.getUnreadCount(user.id);
    if (count > 0) {
      badge.style.display = 'flex';
      badge.textContent = count > 9 ? '9+' : count;
    } else {
      badge.style.display = 'none';
    }
  }

  function renderList() {
    const notifs = store.getNotifications(user.id);

    if (notifs.length === 0) {
      menu.innerHTML = `
        <div style="padding: var(--space-6); text-align: center; color: var(--color-text-tertiary);">
          <div style="font-size: 2rem; margin-bottom: var(--space-2);">🔔</div>
          No notifications yet
        </div>
      `;
      return;
    }

    menu.innerHTML = `
      <div style="padding: var(--space-3) var(--space-4); display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-border);">
        <span style="font-weight: 600; font-size: var(--text-sm);">Notifications</span>
        <button class="btn btn--ghost btn--sm" id="notif-mark-all-read">Mark all read</button>
      </div>
      <div class="notif-list" style="max-height: 360px; overflow-y: auto;">
        ${notifs.slice(0, 10).map(n => `
          <div class="dropdown__item notif-item ${n.read ? '' : 'notif-item--unread'}" data-notif-id="${n.id}" data-target="${getNotifRoute(n)}" style="align-items: flex-start;">
            <div class="notif-item__icon">${getNotifIcon(n.type)}</div>
            <div style="flex:1;min-width:0;">
              <div style="font-size:var(--text-sm);color:${n.read ? 'var(--color-text-secondary)' : 'var(--color-text)'};">${n.message}</div>
              <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-top:2px;">${timeAgo(n.createdAt)}</div>
            </div>
            ${n.read ? '' : '<div style="width:8px;height:8px;background:var(--color-primary);border-radius:50%;flex-shrink:0;margin-top:6px;"></div>'}
          </div>
        `).join('')}
      </div>
    `;

    // Click handlers
    menu.querySelectorAll('.notif-item').forEach(item => {
      item.addEventListener('click', () => {
        const target = item.dataset.target;
        menu.classList.remove('active');
        navigate(target);
      });
    });

    const markAllBtn = menu.querySelector('#notif-mark-all-read');
    if (markAllBtn) {
      markAllBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        store.markAllRead(user.id);
        updateBadge();
        renderList();
      });
    }
  }

  updateBadge();
  renderList();

  // Listen for new notifications
  realtime.on('notification', () => {
    updateBadge();
    renderList();
  });
}
