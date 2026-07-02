// ============================================
// Public Gallery — `/gallery`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { icon } from '../icons.js';

export function renderGallery() {
  const user = auth.getCurrentUser();
  if (!user) return;

  let page = 1;
  const limit = 12;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  function render() {
    const { items, total } = store.getSharedMatches(page, limit);
    const totalPages = Math.ceil(total / limit);

    content.innerHTML = `
      <div class="container">
        <div class="gallery-header">
          <h1 class="gallery-header__title">
            ${icon('gallery', 28)} <span class="text-gradient">Gallery</span>
          </h1>
          <div style="display:flex;gap:var(--space-3);">
            <a href="#/game" class="btn btn--secondary">
              ${icon('gamepad', 16)}
              Play Matching Game
            </a>
          </div>
        </div>

        ${items.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state__icon">🖼️</div>
            <div class="empty-state__title">No shared matches yet</div>
            <p style="color:var(--color-text-secondary);">Be the first to share your dog twin!</p>
          </div>
        ` : `
          <div class="gallery-grid" id="gallery-grid">
            ${items.map((m, i) => `
              <div class="gallery-card" style="animation: scaleIn 0.3s ease ${i * 0.05}s both;">
                <div class="gallery-card__pair">
                  <img src="${m.humanImage}" alt="Human" />
                  <img src="${m.dogImage}" alt="${m.dogBreed}" />
                </div>
                <div class="gallery-card__footer">
                  <div class="gallery-card__user">
                    <img src="${store.getUser(m.userId)?.avatar || ''}" class="avatar avatar--sm" alt="" />
                    @${m.username}
                  </div>
                  <span class="gallery-card__similarity">${m.similarity}%</span>
                </div>
              </div>
            `).join('')}
          </div>

          ${totalPages > 1 ? `
            <div style="display:flex;justify-content:center;gap:var(--space-2);margin-top:var(--space-8);">
              <button class="btn btn--secondary btn--sm" id="gallery-prev" ${page <= 1 ? 'disabled' : ''}>
                ${icon('arrowLeft', 14)} Prev
              </button>
              <span style="display:flex;align-items:center;padding:0 var(--space-4);font-size:var(--text-sm);color:var(--color-text-secondary);">
                Page ${page} of ${totalPages}
              </span>
              <button class="btn btn--secondary btn--sm" id="gallery-next" ${page >= totalPages ? 'disabled' : ''}>
                Next ${icon('arrowRight', 14)}
              </button>
            </div>
          ` : ''}
        `}
      </div>
    `;

    // Pagination
    content.querySelector('#gallery-prev')?.addEventListener('click', () => {
      if (page > 1) { page--; render(); }
    });
    content.querySelector('#gallery-next')?.addEventListener('click', () => {
      if (page < totalPages) { page++; render(); }
    });
  }

  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
