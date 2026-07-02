// ============================================
// Dashboard / "My Dogs" — `/dashboard`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { realtime } from '../realtime.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { timeAgo } from '../utils.js';

export function renderDashboard() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const myMatches = store.getMatchesByUser(user.id);
  const myJobs = store.getJobsByUser(user.id).filter(j => j.status !== 'done');
  const sharedCount = myMatches.filter(m => m.shared).length;
  const forumStats = store.getForumStats(user.id);

  const app = document.querySelector('.page-content') || document.getElementById('app');
  const content = document.createElement('div');
  content.className = 'page';
  content.innerHTML = `
    <div class="container">
      <div class="dashboard-header">
        <h1 class="dashboard-header__greeting">
          Welcome back, <span class="text-gradient">${user.username}</span> 🐾
        </h1>
        <p class="dashboard-header__subtitle">Here's an overview of your dog matching journey</p>
      </div>

      <!-- Stats Row -->
      <div class="stats-row" style="margin-bottom:var(--space-8);">
        <div class="stat-card">
          <div class="stat-card__value">${myMatches.length}</div>
          <div class="stat-card__label">Total Matches</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__value">${sharedCount}</div>
          <div class="stat-card__label">Shared</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__value">${forumStats.totalLikes}</div>
          <div class="stat-card__label">Likes Received</div>
        </div>
      </div>

      <div class="dashboard-grid">
        <!-- Processing Queue -->
        <div class="dashboard-section" id="dashboard-queue">
          <div class="dashboard-section__header">
            <h2 class="dashboard-section__title">${icon('clock', 18)} Processing Queue</h2>
          </div>
          <div id="queue-list">
            ${myJobs.length === 0 ? `
              <div class="empty-state" style="padding:var(--space-8);">
                <div style="font-size:2rem;margin-bottom:var(--space-2);">⏳</div>
                <div style="font-size:var(--text-sm);">No images processing</div>
              </div>
            ` : myJobs.map(job => `
              <div class="queue-item" data-job-id="${job.id}">
                <img src="${job.humanImage}" class="queue-item__thumb" alt="" />
                <div class="queue-item__info">
                  <div style="font-size:var(--text-sm);font-weight:500;">Image Upload</div>
                  <div class="queue-item__status">
                    ${job.urgent ? `<span class="badge badge--primary">${icon('zap', 12)} Urgent</span>` : ''}
                    <span class="badge badge--${job.status === 'processing' ? 'info' : 'primary'}">${job.status}</span>
                  </div>
                  <div class="progress-bar" style="margin-top:var(--space-2);">
                    <div class="progress-bar__fill" style="width:${job.progress}%"></div>
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Forum Activity -->
        <div class="dashboard-section">
          <div class="dashboard-section__header">
            <h2 class="dashboard-section__title">${icon('forum', 18)} Forum Activity</h2>
            <a href="#/forum" class="btn btn--ghost btn--sm">View All</a>
          </div>
          ${forumStats.posts.length === 0 ? `
            <div class="empty-state" style="padding:var(--space-8);">
              <div style="font-size:2rem;margin-bottom:var(--space-2);">💬</div>
              <div style="font-size:var(--text-sm);">No forum posts yet</div>
              <a href="#/forum/new" class="btn btn--primary btn--sm" style="margin-top:var(--space-3);">Create Post</a>
            </div>
          ` : `
            <div style="display:flex;flex-direction:column;gap:var(--space-3);">
              ${forumStats.posts.slice(0, 3).map(p => `
                <div class="forum-activity-item" data-post-id="${p.id}" style="padding:var(--space-3);background:var(--color-bg-elevated);border-radius:var(--radius-lg);cursor:pointer;transition:background var(--transition-fast);">
                  <div style="font-size:var(--text-sm);font-weight:500;margin-bottom:var(--space-1);">${p.title}</div>
                  <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);display:flex;gap:var(--space-3);">
                    <span>${icon('thumbsUp', 12)} ${p.likes}</span>
                    <span>${icon('thumbsDown', 12)} ${p.dislikes}</span>
                    <span>${icon('forum', 12)} ${p.commentCount}</span>
                  </div>
                </div>
              `).join('')}
            </div>
          `}
        </div>

        <!-- My Matches -->
        <div class="dashboard-section dashboard-section--full">
          <div class="dashboard-section__header">
            <h2 class="dashboard-section__title">${icon('paw', 18)} My Matches</h2>
            <a href="#/upload" class="btn btn--primary btn--sm">
              ${icon('upload', 14)}
              Upload More
            </a>
          </div>
          ${myMatches.length === 0 ? `
            <div class="empty-state">
              <div class="empty-state__icon">🐕</div>
              <div class="empty-state__title">No matches yet!</div>
              <p style="color:var(--color-text-secondary);margin-bottom:var(--space-4);">Upload your first photo to find your dog twin.</p>
              <a href="#/upload" class="btn btn--primary btn--lg">
                ${icon('upload', 18)}
                Upload a Photo
              </a>
            </div>
          ` : `
            <div class="dashboard-matches-grid" id="matches-grid">
              ${myMatches.map(m => `
                <div class="dashboard-match-card" data-match-id="${m.id}">
                  <img src="${m.dogImage}" alt="${m.dogBreed}" />
                  <div class="dashboard-match-card__info">
                    <span>${m.dogBreed}</span>
                    ${m.shared ? `<span class="badge badge--success" style="font-size:10px;">${icon('share', 10)} Shared</span>` : ''}
                  </div>
                </div>
              `).join('')}
            </div>
          `}
        </div>
      </div>
    </div>
  `;

  // Replace page content
  const appEl = document.getElementById('app');
  const navbar = appEl.querySelector('.navbar');
  appEl.innerHTML = '';
  if (navbar) appEl.appendChild(navbar);
  appEl.appendChild(content);

  // Click handlers
  content.querySelectorAll('.dashboard-match-card').forEach(card => {
    card.addEventListener('click', () => {
      navigate(`/result/${card.dataset.matchId}`);
    });
  });

  content.querySelectorAll('.forum-activity-item').forEach(item => {
    item.addEventListener('click', () => {
      navigate(`/forum/post/${item.dataset.postId}`);
    });
    item.addEventListener('mouseenter', () => {
      item.style.background = 'var(--color-bg-hover)';
    });
    item.addEventListener('mouseleave', () => {
      item.style.background = 'var(--color-bg-elevated)';
    });
  });

  // Live queue updates
  function onQueueUpdate(data) {
    const jobEl = document.querySelector(`[data-job-id="${data.jobId}"]`);
    if (!jobEl) return;
    const progressFill = jobEl.querySelector('.progress-bar__fill');
    if (progressFill) progressFill.style.width = `${data.progress}%`;
    const statusBadge = jobEl.querySelector('.badge--info, .badge--primary');
    if (statusBadge) statusBadge.textContent = data.status;
  }

  function onMatchReady(data) {
    // Refresh the whole page to show new match
    renderDashboard();
  }

  realtime.on('queue_update', onQueueUpdate);
  realtime.on('match_ready', onMatchReady);

  return () => {
    realtime.off('queue_update', onQueueUpdate);
    realtime.off('match_ready', onMatchReady);
  };
}
