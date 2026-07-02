// ============================================
// Result — `/result/:matchId`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast } from '../utils.js';

export function renderResult(params) {
  const user = auth.getCurrentUser();
  if (!user) return;

  const match = store.getMatch(params.matchId);

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  if (!match) {
    content.innerHTML = `
      <div class="container" style="text-align:center;padding:var(--space-20);">
        <div style="font-size:4rem;margin-bottom:var(--space-4);">🐾</div>
        <h2>Match Not Found</h2>
        <p style="color:var(--color-text-secondary);margin-bottom:var(--space-6);">This match doesn't exist or has been deleted.</p>
        <a href="#/dashboard" class="btn btn--primary">Back to Dashboard</a>
      </div>
    `;
  } else if (match.userId !== user.id) {
    content.innerHTML = `
      <div class="container" style="text-align:center;padding:var(--space-20);">
        <div style="font-size:4rem;margin-bottom:var(--space-4);">🚫</div>
        <h2>Access Denied</h2>
        <p style="color:var(--color-text-secondary);margin-bottom:var(--space-6);">You can only view your own matches.</p>
        <a href="#/dashboard" class="btn btn--primary">Back to Dashboard</a>
      </div>
    `;
  } else {
    content.innerHTML = `
      <div class="container result-container">
        <h1 style="text-align:center;font-size:var(--text-3xl);margin-bottom:var(--space-8);">
          Your <span class="text-gradient">Dog Twin</span>
        </h1>

        <div class="result-match">
          <div class="result-card">
            <img src="${match.humanImage}" alt="Your photo" />
            <div class="result-card__label">You</div>
          </div>

          <div class="result-arrow">
            <div class="result-similarity">${match.similarity}%</div>
            <div class="result-arrow__icon">⟷</div>
            <div class="result-breed">${match.dogBreed}</div>
          </div>

          <div class="result-card" style="border-color: var(--color-primary);">
            <img src="${match.dogImage}" alt="${match.dogBreed}" />
            <div class="result-card__label">${match.dogBreed}</div>
          </div>
        </div>

        ${match.caption ? `<p style="text-align:center;color:var(--color-text-secondary);margin-bottom:var(--space-6);font-style:italic;">"${match.caption}"</p>` : ''}

        <div class="result-actions">
          <button class="btn ${match.shared ? 'btn--secondary' : 'btn--primary'}" id="result-share">
            ${icon('share', 16)}
            ${match.shared ? 'Unshare from Gallery' : 'Share to Gallery'}
          </button>
          <button class="btn btn--secondary" id="result-download">
            ${icon('download', 16)}
            Download
          </button>
          <button class="btn btn--danger" id="result-delete">
            ${icon('trash', 16)}
            Delete
          </button>
          <a href="#/upload" class="btn btn--ghost">
            ${icon('camera', 16)}
            Match Another
          </a>
        </div>
      </div>
    `;
  }

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);

  if (!match || match.userId !== user.id) return;

  // Share toggle
  document.getElementById('result-share').addEventListener('click', () => {
    store.toggleShare(match.id);
    toast(match.shared ? 'Shared to gallery! 🎉' : 'Removed from gallery', match.shared ? 'success' : 'info');
    renderResult(params); // Re-render to update button state
  });

  // Download (simulated)
  document.getElementById('result-download').addEventListener('click', () => {
    toast('Download started! 📥', 'success');
  });

  // Delete
  document.getElementById('result-delete').addEventListener('click', () => {
    if (confirm('Delete this match? This cannot be undone.')) {
      store.deleteMatch(match.id);
      toast('Match deleted', 'info');
      navigate('/dashboard');
    }
  });
}
