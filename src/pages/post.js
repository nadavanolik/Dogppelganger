// ============================================
// Post Detail — `/forum/post/:postId`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { timeAgo, toast } from '../utils.js';

export function renderPost(params) {
  const user = auth.getCurrentUser();
  if (!user) return;

  const post = store.getPost(params.postId);

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  if (!post) {
    content.innerHTML = `
      <div class="container" style="text-align:center;padding:var(--space-20);">
        <div style="font-size:4rem;margin-bottom:var(--space-4);">💬</div>
        <h2>Post Not Found</h2>
        <p style="color:var(--color-text-secondary);margin-bottom:var(--space-6);">This post doesn't exist.</p>
        <a href="#/forum" class="btn btn--primary">Back to Forum</a>
      </div>
    `;
    app.innerHTML = '';
    if (navbar) app.appendChild(navbar);
    app.appendChild(content);
    return;
  }

  function render() {
    const comments = store.getCommentsByPost(post.id);
    const userLiked = post.likedBy.includes(user.id);
    const userDisliked = post.dislikedBy.includes(user.id);

    content.innerHTML = `
      <div class="container post-detail">
        <a href="#/forum" class="btn btn--ghost btn--sm" style="margin-bottom:var(--space-6);">
          ${icon('arrowLeft', 14)} Back to Forum
        </a>

        <div class="post-detail__header">
          <h1 class="post-detail__title">${post.title}</h1>
          <div class="post-detail__author">
            <img src="${post.avatar}" class="avatar" alt="" />
            <div>
              <div style="font-weight:600;">@${post.username}</div>
              <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);">${timeAgo(post.createdAt)}</div>
            </div>
          </div>
        </div>

        ${post.mediaId ? `<img src="${post.mediaId}" class="post-detail__media" alt="" />` : ''}

        <div class="post-detail__body">${post.body}</div>

        <div class="post-detail__reactions">
          <button class="reaction-btn ${userLiked ? 'active' : ''}" id="post-like">
            ${icon('thumbsUp', 16)} ${post.likes}
          </button>
          <button class="reaction-btn ${userDisliked ? 'active dislike' : ''}" id="post-dislike">
            ${icon('thumbsDown', 16)} ${post.dislikes}
          </button>
          <span style="margin-left:auto;font-size:var(--text-sm);color:var(--color-text-tertiary);">
            ${icon('forum', 14)} ${comments.length} comment${comments.length !== 1 ? 's' : ''}
          </span>
        </div>

        <div class="comments-section">
          <h2 class="comments-section__title">Comments</h2>

          ${comments.length === 0 ? `
            <p style="color:var(--color-text-tertiary);font-size:var(--text-sm);">No comments yet. Be the first!</p>
          ` : `
            <div class="comment-list">
              ${comments.map(c => {
                const cLiked = c.likedBy.includes(user.id);
                const cDisliked = c.dislikedBy.includes(user.id);
                return `
                  <div class="comment-item" data-comment-id="${c.id}">
                    <img src="${c.avatar}" class="avatar avatar--sm" alt="" />
                    <div class="comment-item__content">
                      <div class="comment-item__header">
                        <span class="comment-item__username">@${c.username}</span>
                        <span class="comment-item__time">${timeAgo(c.createdAt)}</span>
                      </div>
                      <div class="comment-item__body">${c.body}</div>
                      ${c.mediaId ? `<img src="${c.mediaId}" style="max-width:200px;border-radius:var(--radius-lg);margin-bottom:var(--space-2);" />` : ''}
                      <div class="comment-item__reactions">
                        <button class="reaction-btn ${cLiked ? 'active' : ''}" data-comment-like="${c.id}">
                          ${icon('thumbsUp', 12)} ${c.likes}
                        </button>
                        <button class="reaction-btn ${cDisliked ? 'active dislike' : ''}" data-comment-dislike="${c.id}">
                          ${icon('thumbsDown', 12)} ${c.dislikes}
                        </button>
                      </div>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          `}

          <div class="comment-composer">
            <img src="${user.avatar}" class="avatar" alt="" />
            <div class="comment-composer__input" style="flex:1;">
              <textarea id="comment-body" placeholder="Write a comment..." rows="2"></textarea>
              <div style="display:flex;justify-content:flex-end;margin-top:var(--space-2);">
                <button class="btn btn--primary btn--sm" id="comment-submit">
                  ${icon('send', 14)} Post Comment
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Post reactions
    document.getElementById('post-like')?.addEventListener('click', () => {
      store.reactToPost(post.id, user.id, 'like');
      render();
    });
    document.getElementById('post-dislike')?.addEventListener('click', () => {
      store.reactToPost(post.id, user.id, 'dislike');
      render();
    });

    // Comment reactions
    content.querySelectorAll('[data-comment-like]').forEach(btn => {
      btn.addEventListener('click', () => {
        store.reactToComment(btn.dataset.commentLike, user.id, 'like');
        render();
      });
    });
    content.querySelectorAll('[data-comment-dislike]').forEach(btn => {
      btn.addEventListener('click', () => {
        store.reactToComment(btn.dataset.commentDislike, user.id, 'dislike');
        render();
      });
    });

    // Submit comment
    document.getElementById('comment-submit')?.addEventListener('click', () => {
      const body = document.getElementById('comment-body').value.trim();
      if (!body) return;
      store.createComment({
        postId: post.id,
        userId: user.id,
        username: user.username,
        avatar: user.avatar,
        body,
        mediaId: null,
      });
      toast('Comment posted! 💬', 'success');
      render();
    });
  }

  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
