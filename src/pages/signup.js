// ============================================
// Sign-up — `/signup`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast } from '../utils.js';

export function renderSignup() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card__logo">
          ${icon('paw', 32)}
          Dogppelganger
        </div>
        <h1 class="auth-card__title">Create Account</h1>
        <p class="auth-card__subtitle">Join and find your dog twin!</p>

        <div class="auth-error" id="signup-error"></div>

        <form class="auth-form" id="signup-form">
          <div class="form-group">
            <label for="signup-username">Username</label>
            <input type="text" id="signup-username" placeholder="Choose a username" autocomplete="username" required />
            <span class="error-text" id="signup-username-error"></span>
          </div>

          <div class="form-group">
            <label for="signup-email">Email</label>
            <input type="email" id="signup-email" placeholder="your@email.com" autocomplete="email" required />
            <span class="error-text" id="signup-email-error"></span>
          </div>

          <div class="form-group">
            <label for="signup-password">Password</label>
            <input type="password" id="signup-password" placeholder="Create a password" autocomplete="new-password" required />
            <div class="password-strength" id="password-strength">
              <div class="password-strength__bar" id="str-bar-1"></div>
              <div class="password-strength__bar" id="str-bar-2"></div>
              <div class="password-strength__bar" id="str-bar-3"></div>
              <div class="password-strength__bar" id="str-bar-4"></div>
            </div>
            <span class="error-text" id="signup-password-error"></span>
          </div>

          <div class="form-group">
            <label for="signup-confirm">Confirm Password</label>
            <input type="password" id="signup-confirm" placeholder="Repeat your password" autocomplete="new-password" required />
            <span class="error-text" id="signup-confirm-error"></span>
          </div>

          <button type="submit" class="btn btn--primary btn--lg" id="signup-submit">
            ${icon('paw', 18)}
            Create Account
          </button>
        </form>

        <div class="auth-card__footer">
          Already have an account? <a href="#/login">Log in</a>
        </div>
      </div>
    </div>
  `;

  // Password strength
  const passwordInput = document.getElementById('signup-password');
  passwordInput.addEventListener('input', () => {
    const val = passwordInput.value;
    const bars = [
      document.getElementById('str-bar-1'),
      document.getElementById('str-bar-2'),
      document.getElementById('str-bar-3'),
      document.getElementById('str-bar-4'),
    ];

    let strength = 0;
    if (val.length >= 6) strength++;
    if (val.length >= 8) strength++;
    if (/[A-Z]/.test(val) && /[a-z]/.test(val)) strength++;
    if (/\d/.test(val) || /[^a-zA-Z0-9]/.test(val)) strength++;

    bars.forEach((bar, i) => {
      bar.className = 'password-strength__bar';
      if (i < strength) {
        if (strength <= 1) bar.classList.add('weak');
        else if (strength <= 2) bar.classList.add('medium');
        else bar.classList.add('strong');
      }
    });
  });

  // Form submit
  document.getElementById('signup-form').addEventListener('submit', (e) => {
    e.preventDefault();

    const username = document.getElementById('signup-username').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    const confirm = document.getElementById('signup-confirm').value;

    // Clear errors
    document.querySelectorAll('.error-text').forEach(el => el.textContent = '');
    document.querySelectorAll('input.error').forEach(el => el.classList.remove('error'));

    let hasError = false;

    if (username.length < 3) {
      document.getElementById('signup-username-error').textContent = 'Username must be at least 3 characters';
      document.getElementById('signup-username').classList.add('error');
      hasError = true;
    }

    if (!email.includes('@')) {
      document.getElementById('signup-email-error').textContent = 'Please enter a valid email';
      document.getElementById('signup-email').classList.add('error');
      hasError = true;
    }

    if (password.length < 6) {
      document.getElementById('signup-password-error').textContent = 'Password must be at least 6 characters';
      document.getElementById('signup-password').classList.add('error');
      hasError = true;
    }

    if (password !== confirm) {
      document.getElementById('signup-confirm-error').textContent = 'Passwords do not match';
      document.getElementById('signup-confirm').classList.add('error');
      hasError = true;
    }

    if (hasError) return;

    const result = store.createUser({ username, email, password });

    if (result.error) {
      const errEl = document.getElementById('signup-error');
      errEl.textContent = result.error;
      errEl.classList.add('visible');
      return;
    }

    // Auto-login
    auth.login(result.user);
    toast('Welcome to Dogppelganger! 🐕', 'success');
    navigate('/dashboard');
  });
}
