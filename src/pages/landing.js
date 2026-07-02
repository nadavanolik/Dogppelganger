// ============================================
// Landing / Home — `/`
// ============================================

import { store } from '../store.js';
import { icon } from '../icons.js';

export function renderLanding() {
  const featured = store.getFeaturedMatches(6);

  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="landing-hero">
      <div class="landing-hero__content">
        <div class="landing-hero__badge">
          ${icon('paw', 16)}
          <span>AI-Powered Dog Matching</span>
        </div>

        <h1 class="landing-hero__title">
          Find Your <span class="text-gradient">Dog Twin</span>
        </h1>

        <p class="landing-hero__subtitle">
          Upload your photo and our AI will match you with the dog breed that looks just like you. Share, play games, and join a community of fellow dog lovers.
        </p>

        <div class="landing-hero__actions">
          <a href="#/signup" class="btn btn--primary btn--lg" id="landing-cta-signup">
            ${icon('paw', 20)}
            Try It — Sign Up
          </a>
          <a href="#/login" class="btn btn--secondary btn--lg" id="landing-cta-login">
            Log In
          </a>
        </div>

        <div class="landing-hero__match-demo">
          <div class="landing-hero__match-card">
            <img src="${featured[0]?.humanImage || ''}" alt="Human photo" />
          </div>
          <div class="landing-hero__match-arrow">
            <span style="font-size:2rem;">→</span>
            <div style="font-size:var(--text-xs);color:var(--color-primary);font-weight:600;margin-top:4px;">AI Match</div>
          </div>
          <div class="landing-hero__match-card" style="border-color: var(--color-primary);">
            <img src="${featured[0]?.dogImage || ''}" alt="Dog match" />
          </div>
        </div>
      </div>
    </div>

    <section class="landing-how">
      <div class="container">
        <h2 class="landing-how__title">How It <span class="text-gradient">Works</span></h2>
        <div class="landing-how__steps">
          <div class="landing-how__step">
            <div class="landing-how__step-icon">📸</div>
            <div class="landing-how__step-title">Upload Your Photo</div>
            <div class="landing-how__step-text">Take a selfie or upload any clear photo of your face. Our AI handles the rest.</div>
          </div>
          <div class="landing-how__step">
            <div class="landing-how__step-icon">🤖</div>
            <div class="landing-how__step-title">AI Matching</div>
            <div class="landing-how__step-text">CLIP AI analyzes your features and finds the most similar dog breed from thousands.</div>
          </div>
          <div class="landing-how__step">
            <div class="landing-how__step-icon">🐕</div>
            <div class="landing-how__step-title">Meet Your Twin!</div>
            <div class="landing-how__step-text">See your dog doppelganger, share it with friends, and play the matching game.</div>
          </div>
        </div>
      </div>
    </section>

    <section class="landing-gallery">
      <div class="container">
        <h2 class="landing-gallery__title">Recent <span class="text-gradient">Matches</span></h2>
        <div class="landing-gallery__grid">
          ${featured.map(m => `
            <div class="landing-gallery__item">
              <div class="landing-gallery__pair">
                <img src="${m.humanImage}" alt="Human" />
                <img src="${m.dogImage}" alt="Dog" />
              </div>
              <div class="landing-gallery__info">
                <span class="landing-gallery__user">@${m.username}</span>
                <span class="landing-gallery__similarity">${m.similarity}% match</span>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </section>

    <section class="landing-cta">
      <div class="container">
        <h2 class="landing-cta__title">Ready to Find Your <span class="text-gradient">Dog Twin</span>?</h2>
        <p class="landing-cta__text">Join thousands of users discovering their canine counterparts.</p>
        <a href="#/signup" class="btn btn--primary btn--lg">
          ${icon('paw', 20)}
          Get Started Free
        </a>
      </div>
    </section>
  `;
}
