// ============================================
// Global Navigation Bar
// ============================================

import { icon } from '../icons.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { renderNotificationsDropdown } from './notifications.js';

export function renderNavbar() {
  const isAuth = auth.isAuthenticated();
  const user = auth.getCurrentUser();

  const nav = document.createElement('nav');
  nav.className = 'navbar';
  nav.id = 'main-navbar';

  if (isAuth) {
    nav.innerHTML = `
      <div class="navbar__inner">
        <a href="#/dashboard" class="navbar__logo" id="nav-logo">
          ${icon('paw', 28)}
          <span class="navbar__brand">Dogppelganger</span>
        </a>

        <div class="navbar__links">
          <a href="#/upload" class="navbar__link" data-route="/upload" id="nav-upload">
            ${icon('upload', 18)}
            <span>Upload</span>
          </a>
          <a href="#/gallery" class="navbar__link" data-route="/gallery" id="nav-gallery">
            ${icon('gallery', 18)}
            <span>Gallery</span>
          </a>
          <a href="#/game" class="navbar__link" data-route="/game" id="nav-game">
            ${icon('gamepad', 18)}
            <span>Game</span>
          </a>
          <a href="#/forum" class="navbar__link" data-route="/forum" id="nav-forum">
            ${icon('forum', 18)}
            <span>Forum</span>
          </a>
          <a href="#/messages" class="navbar__link" data-route="/messages" id="nav-messages">
            ${icon('messages', 18)}
            <span>Messages</span>
          </a>
        </div>

        <div class="navbar__actions">
          <div class="dropdown" id="notif-dropdown">
            <button class="navbar__icon-btn" id="notif-bell" aria-label="Notifications">
              ${icon('bell', 20)}
              <span class="navbar__badge" id="notif-badge" style="display:none">0</span>
            </button>
            <div class="dropdown__menu" id="notif-menu">
              <!-- Filled by notifications component -->
            </div>
          </div>

          <div class="dropdown" id="profile-dropdown">
            <button class="navbar__icon-btn navbar__profile" id="profile-btn">
              <img src="${user?.avatar || ''}" alt="${user?.username || ''}" class="avatar avatar--sm" />
              <span class="navbar__username">${user?.username || ''}</span>
            </button>
            <div class="dropdown__menu" id="profile-menu" style="min-width: 200px;">
              <div class="dropdown__item" style="border-bottom: 1px solid var(--color-border); padding-bottom: var(--space-3); pointer-events:none;">
                <img src="${user?.avatar || ''}" class="avatar avatar--sm" />
                <div>
                  <div style="font-weight:600;color:var(--color-text)">${user?.username || ''}</div>
                  <div style="font-size:var(--text-xs);color:var(--color-text-tertiary)">${user?.email || ''}</div>
                </div>
              </div>
              <div class="dropdown__item" id="nav-profile-dashboard">
                ${icon('user', 16)}
                Dashboard
              </div>
              <div class="dropdown__item" id="nav-logout" style="color:var(--color-danger)">
                ${icon('logout', 16)}
                Log out
              </div>
            </div>
          </div>
        </div>

        <button class="navbar__hamburger" id="nav-hamburger" aria-label="Menu">
          <span></span><span></span><span></span>
        </button>
      </div>
    `;
  } else {
    nav.innerHTML = `
      <div class="navbar__inner">
        <a href="#/" class="navbar__logo" id="nav-logo">
          ${icon('paw', 28)}
          <span class="navbar__brand">Dogppelganger</span>
        </a>
        <div class="navbar__actions">
          <a href="#/login" class="btn btn--ghost" id="nav-login">Log in</a>
          <a href="#/signup" class="btn btn--primary" id="nav-signup">Sign up</a>
        </div>
      </div>
    `;
  }

  return nav;
}

export function initNavbarEvents() {
  // Highlight active link
  function updateActiveLink() {
    const hash = window.location.hash.replace('#', '') || '/';
    document.querySelectorAll('.navbar__link').forEach(link => {
      const route = link.dataset.route;
      if (route && hash.startsWith(route)) {
        link.classList.add('active');
      } else {
        link.classList.remove('active');
      }
    });
  }
  updateActiveLink();
  window.addEventListener('hashchange', updateActiveLink);

  // Dropdowns
  document.querySelectorAll('.dropdown').forEach(dropdown => {
    const btn = dropdown.querySelector('.navbar__icon-btn, .navbar__profile');
    const menu = dropdown.querySelector('.dropdown__menu');
    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      // Close other dropdowns
      document.querySelectorAll('.dropdown__menu.active').forEach(m => {
        if (m !== menu) m.classList.remove('active');
      });
      menu.classList.toggle('active');
    });
  });

  // Close dropdowns on outside click
  document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown__menu.active').forEach(m => m.classList.remove('active'));
  });

  // Logout
  const logoutBtn = document.getElementById('nav-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      auth.logout();
      navigate('/');
    });
  }

  // Dashboard from profile menu
  const dashBtn = document.getElementById('nav-profile-dashboard');
  if (dashBtn) {
    dashBtn.addEventListener('click', () => {
      navigate('/dashboard');
    });
  }

  // Mobile hamburger
  const hamburger = document.getElementById('nav-hamburger');
  if (hamburger) {
    hamburger.addEventListener('click', () => {
      document.querySelector('.navbar__links')?.classList.toggle('open');
      hamburger.classList.toggle('active');
    });
  }

  // Initialize notifications dropdown
  renderNotificationsDropdown();
}
