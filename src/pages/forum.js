// ============================================
// Forum Feed — `/forum`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { timeAgo, truncate, debounce } from '../utils.js';

export function renderForum() {
  const user = auth.getCurrentUser();
  if (!user) return;

  let page = 1;
  let searchQuery = '';

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  function render() {
    let postsData;
    if (searchQuery) {
      const results = store.searchPosts(searchQuery);
      postsData = { items: results, total: results.length };
    } else {
      postsData = store.getPosts(page, 10);
    }
    const totalPages = Math.ceil(postsData.total / 10);

    content.innerHTML = `
      <div class="container" style="max-width:800px;">
        <div class="forum-header">
          <h1 style="font-size:var(--text-3xl);">
            ${icon('forum', 28)} <span class="text-gradient">Forum</span>
          </h1>
          <a href="#/forum/new" class="btn btn--primary">
            ${icon('plus', 16)}
            New Post
          </a>
        </div>

        <div class="forum-search" style="margin-bottom:var(--space-6);max-width:100%;">
          <div class="search-box" style="width:100%;">
            <span class="search-box__icon">${icon('search', 16)}</span>
            <input type="text" id="forum-search-input" placeholder="Search posts..." value="${searchQuery}" style="padding-left:var(--space-10);" />
          </div>
        </div>

        ${searchQuery ? `
          <p style="font-size:var(--text-sm);color:var(--color-text-secondary);margin-bottom:var(--space-4);">
            ${postsData.items.length} result${postsData.items.length !== 1 ? 's' : ''} for "${searchQuery}"
            <button class="btn btn--ghost btn--sm" id="clear-search">Clear</button>
          </p>
        ` : ''}

        ${postsData.items.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state__icon">💬</div>
            <div class="empty-state__title">${searchQuery ? 'No results found' : 'No posts yet'}</div>
            <p style="color:var(--color-text-secondary);">${searchQuery ? 'Try a different search term' : 'Be the first to post!'}</p>
          </div>
        ` : `
          <div class="forum-list">
            ${postsData.items.map(p => `
              <div class="forum-post-card" data-post-id="${p.id}">
                ${p.mediaId ? `<img src="${p.mediaId}" class="forum-post-card__media" alt="" />` : ''}
                <div class="forum-post-card__content">
                  <div class="forum-post-card__title">${p.title}</div>
                  <div class="forum-post-card__snippet">${truncate(p.body, 120)}</div>
                  <div class="forum-post-card__meta">
                    <span class="forum-post-card__meta-item">
                      <img src="${p.avatar}" class="avatar avatar--sm" style="width:20px;height:20px;" alt="" />
                      @${p.username}
                    </span>
                    <span class="forum-post-card__meta-item">${icon('thumbsUp', 12)} ${p.likes}</span>
                    <span class="forum-post-card__meta-item">${icon('thumbsDown', 12)} ${p.dislikes}</span>
                    <span class="forum-post-card__meta-item">${icon('forum', 12)} ${p.commentCount}</span>
                    <span class="forum-post-card__meta-item">${icon('clock', 12)} ${timeAgo(p.createdAt)}</span>
                  </div>
                </div>
              </div>
            `).join('')}
          </div>

          ${!searchQuery && totalPages > 1 ? `
            <div style="display:flex;justify-content:center;gap:var(--space-2);margin-top:var(--space-8);">
              <button class="btn btn--secondary btn--sm" id="forum-prev" ${page <= 1 ? 'disabled' : ''}>
                ${icon('arrowLeft', 14)} Prev
              </button>
              <span style="display:flex;align-items:center;padding:0 var(--space-4);font-size:var(--text-sm);color:var(--color-text-secondary);">
                Page ${page} of ${totalPages}
              </span>
              <button class="btn btn--secondary btn--sm" id="forum-next" ${page >= totalPages ? 'disabled' : ''}>
                Next ${icon('arrowRight', 14)}
              </button>
            </div>
          ` : ''}
        `}
      </div>
    `;

    // Post click
    content.querySelectorAll('.forum-post-card').forEach(card => {
      card.addEventListener('click', () => {
        navigate(`/forum/post/${card.dataset.postId}`);
      });
    });

    // Search
    const searchInput = document.getElementById('forum-search-input');
    const doSearch = debounce((val) => {
      searchQuery = val;
      page = 1;
      render();
    }, 300);

    searchInput?.addEventListener('input', (e) => {
      doSearch(e.target.value);
    });

    // Clear search
    document.getElementById('clear-search')?.addEventListener('click', () => {
      searchQuery = '';
      page = 1;
      render();
    });

    // Pagination
    document.getElementById('forum-prev')?.addEventListener('click', () => {
      if (page > 1) { page--; render(); }
    });
    document.getElementById('forum-next')?.addEventListener('click', () => {
      page++; render();
    });
  }

  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
