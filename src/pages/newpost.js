// ============================================
// Create Post — `/forum/new`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast, readFileAsDataURL } from '../utils.js';

export function renderNewPost() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  let mediaDataUrl = null;

  content.innerHTML = `
    <div class="container newpost-form">
      <a href="#/forum" class="btn btn--ghost btn--sm" style="margin-bottom:var(--space-6);">
        ${icon('arrowLeft', 14)} Back to Forum
      </a>

      <h1 class="newpost-form__title">Create <span class="text-gradient">New Post</span></h1>

      <form id="newpost-form">
        <div class="form-group">
          <label for="post-title">Title</label>
          <input type="text" id="post-title" placeholder="Give your post a catchy title" maxlength="100" required />
          <span class="error-text" id="title-error"></span>
        </div>

        <div class="form-group">
          <label for="post-body">Body</label>
          <textarea id="post-body" placeholder="Write your thoughts, share your experience, ask a question..." rows="8" required></textarea>
          <span class="error-text" id="body-error"></span>
        </div>

        <div class="form-group">
          <label>Attach Image (optional)</label>
          <div style="display:flex;gap:var(--space-3);align-items:center;">
            <button type="button" class="btn btn--secondary" id="attach-media">
              ${icon('paperclip', 16)}
              Attach Image
            </button>
            <span id="media-name" style="font-size:var(--text-sm);color:var(--color-text-secondary);"></span>
          </div>
          <input type="file" id="media-input" accept="image/*" hidden />
          <div class="newpost-media-preview" id="media-preview" style="display:none;">
            <img id="media-preview-img" src="" alt="Preview" />
            <button type="button" class="btn btn--ghost btn--sm" id="media-remove" style="margin-top:var(--space-2);">
              ${icon('x', 14)} Remove
            </button>
          </div>
        </div>

        <div style="display:flex;gap:var(--space-3);margin-top:var(--space-6);">
          <a href="#/forum" class="btn btn--secondary" style="flex:1;">Cancel</a>
          <button type="submit" class="btn btn--primary" style="flex:1;" id="post-submit">
            ${icon('send', 16)}
            Publish Post
          </button>
        </div>
      </form>
    </div>
  `;

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);

  // Media attach
  document.getElementById('attach-media').addEventListener('click', () => {
    document.getElementById('media-input').click();
  });

  document.getElementById('media-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      toast('Image too large (max 5MB)', 'error');
      return;
    }

    mediaDataUrl = await readFileAsDataURL(file);
    document.getElementById('media-name').textContent = file.name;
    document.getElementById('media-preview').style.display = '';
    document.getElementById('media-preview-img').src = mediaDataUrl;
  });

  document.getElementById('media-remove')?.addEventListener('click', () => {
    mediaDataUrl = null;
    document.getElementById('media-name').textContent = '';
    document.getElementById('media-preview').style.display = 'none';
    document.getElementById('media-input').value = '';
  });

  // Submit
  document.getElementById('newpost-form').addEventListener('submit', (e) => {
    e.preventDefault();

    const title = document.getElementById('post-title').value.trim();
    const body = document.getElementById('post-body').value.trim();

    document.querySelectorAll('.error-text').forEach(el => el.textContent = '');

    let hasError = false;

    if (!title) {
      document.getElementById('title-error').textContent = 'Title is required';
      hasError = true;
    }
    if (!body) {
      document.getElementById('body-error').textContent = 'Body is required';
      hasError = true;
    }

    if (hasError) return;

    const post = store.createPost({
      userId: user.id,
      username: user.username,
      avatar: user.avatar,
      title,
      body,
      mediaId: mediaDataUrl,
    });

    toast('Post published! 🎉', 'success');
    navigate(`/forum/post/${post.id}`);
  });
}
