// ============================================
// Login — `/login`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate, getQueryParams } from '../router.js';
import { icon } from '../icons.js';
import { toast } from '../utils.js';

let failedAttempts = 0;

export function renderLogin() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card__logo">
          ${icon('paw', 32)}
          Dogppelganger
        </div>
        <h1 class="auth-card__title">Welcome Back</h1>
        <p class="auth-card__subtitle">Log in to your account</p>

        <div class="auth-error" id="login-error"></div>

        <form class="auth-form" id="login-form">
          <div class="form-group">
            <label for="login-username">Username or Email</label>
            <input type="text" id="login-username" placeholder="Enter username or email" autocomplete="username" required />
          </div>

          <div class="form-group">
            <label for="login-password">Password</label>
            <input type="password" id="login-password" placeholder="Enter password" autocomplete="current-password" required />
          </div>

          <button type="submit" class="btn btn--primary btn--lg" id="login-submit">
            Log In
          </button>
        </form>

        <div class="auth-card__footer">
          Don't have an account? <a href="#/signup">Sign up</a>
        </div>

        <div style="margin-top:var(--space-6);padding-top:var(--space-4);border-top:1px solid var(--color-border);">
          <p style="font-size:var(--text-xs);color:var(--color-text-tertiary);text-align:center;margin-bottom:var(--space-3);">Demo accounts — click to auto-fill:</p>
          <div style="display:flex;flex-wrap:wrap;gap:var(--space-2);justify-content:center;" id="demo-accounts">
          </div>
        </div>
      </div>
    </div>
  `;

  // Demo account quick-fill buttons
  const demoContainer = document.getElementById('demo-accounts');
  const demoUsers = ['DogLover42', 'PawsAndClaws', 'WoofWoof'];
  demoUsers.forEach(username => {
    const btn = document.createElement('button');
    btn.className = 'btn btn--ghost btn--sm';
    btn.textContent = `@${username}`;
    btn.addEventListener('click', () => {
      document.getElementById('login-username').value = username;
      document.getElementById('login-password').value = 'password123';
    });
    demoContainer.appendChild(btn);
  });

  // Form submit
  document.getElementById('login-form').addEventListener('submit', (e) => {
    e.preventDefault();

    const errEl = document.getElementById('login-error');
    errEl.classList.remove('visible');

    if (failedAttempts >= 5) {
      errEl.textContent = 'Too many failed attempts. Please wait a moment and try again.';
      errEl.classList.add('visible');
      setTimeout(() => { failedAttempts = 0; }, 10000);
      return;
    }

    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;

    const user = store.getUserByUsername(username);

    if (!user || user.password !== password) {
      failedAttempts++;
      errEl.textContent = 'Invalid username/email or password';
      errEl.classList.add('visible');
      // Shake animation
      const card = document.querySelector('.auth-card');
      card.style.animation = 'none';
      requestAnimationFrame(() => {
        card.style.animation = 'shake 0.4s ease';
      });
      return;
    }

    failedAttempts = 0;
    auth.login(user);
    toast(`Welcome back, ${user.username}! 🐾`, 'success');

    const params = getQueryParams();
    navigate(params.next || '/dashboard');
  });

  // Add shake animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes shake {
      0%, 100% { transform: translateX(0); }
      20% { transform: translateX(-10px); }
      40% { transform: translateX(10px); }
      60% { transform: translateX(-6px); }
      80% { transform: translateX(6px); }
    }
  `;
  document.head.appendChild(style);
}
