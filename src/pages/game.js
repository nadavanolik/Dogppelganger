// ============================================
// Single-player Game — `/game`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { icon } from '../icons.js';
import { toast } from '../utils.js';

export function renderGame() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  let selectedHuman = null;
  let selectedDog = null;
  let pairs = {};
  let roundData = null;
  let state = 'playing'; // playing | submitted

  function startRound() {
    roundData = store.generateRound(4);
    selectedHuman = null;
    selectedDog = null;
    pairs = {};
    state = 'playing';
    renderBoard();
  }

  function renderBoard() {
    const pairCount = Object.keys(pairs).length;

    content.innerHTML = `
      <div class="container game-container">
        <div class="game-header">
          <h1 class="game-header__title">
            ${icon('gamepad', 28)} Match the <span class="text-gradient">Pairs</span>
          </h1>
          <p class="game-header__subtitle">
            ${state === 'playing'
              ? `Click a person, then click their dog twin. ${pairCount}/${roundData.humans.length} paired.`
              : 'Results revealed! See how you did.'}
          </p>
        </div>

        <div class="game-board">
          <div class="game-column">
            <div class="game-column__title">Humans 👤</div>
            ${roundData.humans.map(h => {
              const isPaired = pairs[h.id] !== undefined;
              const isSelected = selectedHuman === h.id;
              let extraClass = '';
              if (state === 'submitted') {
                extraClass = pairs[h.id] === h.id ? 'correct' : (pairs[h.id] ? 'wrong' : '');
              } else if (isSelected) {
                extraClass = 'selected';
              }
              return `
                <div class="game-card ${extraClass} ${isPaired && state === 'playing' ? 'selected' : ''}" data-human-id="${h.id}" style="opacity:${isPaired && state === 'playing' ? '0.6' : '1'}">
                  <img src="${h.image}" alt="${h.username}" />
                  <div class="game-card__label">@${h.username}</div>
                  <div class="game-card__check">${icon('check', 16)}</div>
                </div>
              `;
            }).join('')}
          </div>

          <div class="game-lines" style="display:flex;align-items:center;justify-content:center;flex-direction:column;gap:var(--space-4);">
            ${state === 'playing' ? `
              <div style="writing-mode:vertical-lr;color:var(--color-text-tertiary);font-size:var(--text-sm);">
                ${pairCount > 0 ? `${pairCount} paired` : 'Select pairs'}
              </div>
            ` : ''}
          </div>

          <div class="game-column">
            <div class="game-column__title">Dogs 🐕</div>
            ${roundData.dogs.map(d => {
              const pairedTo = Object.entries(pairs).find(([, dogId]) => dogId === d.id);
              const isPaired = !!pairedTo;
              const isSelected = selectedDog === d.id;
              let extraClass = '';
              if (state === 'submitted') {
                extraClass = pairedTo && pairedTo[0] === d.id ? 'correct' : (isPaired ? 'wrong' : '');
              } else if (isSelected) {
                extraClass = 'selected';
              }
              return `
                <div class="game-card ${extraClass} ${isPaired && state === 'playing' ? 'selected' : ''}" data-dog-id="${d.id}" style="opacity:${isPaired && state === 'playing' ? '0.6' : '1'}">
                  <img src="${d.image}" alt="${d.breed}" />
                  <div class="game-card__label">${d.breed}</div>
                  <div class="game-card__check">${icon('check', 16)}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        ${state === 'playing' ? `
          <div class="game-actions">
            <button class="btn btn--primary btn--lg" id="game-submit" ${pairCount < roundData.humans.length ? 'disabled' : ''}>
              ${icon('check', 18)}
              Submit Answers
            </button>
          </div>
        ` : ''}

        ${state === 'submitted' ? `
          <div class="game-score" id="game-score">
            <!-- Filled after checking -->
          </div>
        ` : ''}

        <div style="text-align:center;margin-top:var(--space-6);">
          <a href="#/game/lobbies" class="btn btn--ghost">
            ${icon('users', 16)}
            Play Multiplayer
          </a>
        </div>
      </div>
    `;

    if (state === 'playing') {
      // Human click
      content.querySelectorAll('[data-human-id]').forEach(card => {
        card.addEventListener('click', () => {
          const id = card.dataset.humanId;
          if (pairs[id] !== undefined) return; // already paired
          selectedHuman = selectedHuman === id ? null : id;
          if (selectedHuman && selectedDog) {
            pairs[selectedHuman] = selectedDog;
            selectedHuman = null;
            selectedDog = null;
          }
          renderBoard();
        });
      });

      // Dog click
      content.querySelectorAll('[data-dog-id]').forEach(card => {
        card.addEventListener('click', () => {
          const id = card.dataset.dogId;
          const alreadyPaired = Object.values(pairs).includes(id);
          if (alreadyPaired) return;
          selectedDog = selectedDog === id ? null : id;
          if (selectedHuman && selectedDog) {
            pairs[selectedHuman] = selectedDog;
            selectedHuman = null;
            selectedDog = null;
          }
          renderBoard();
        });
      });

      // Submit
      content.querySelector('#game-submit')?.addEventListener('click', () => {
        state = 'submitted';
        const result = store.checkAnswer(roundData.token, pairs);
        renderBoard();

        // Show score
        const scoreEl = document.getElementById('game-score');
        if (scoreEl) {
          const percent = Math.round((result.correct / result.total) * 100);
          scoreEl.innerHTML = `
            <div class="game-score__value">${result.correct}/${result.total}</div>
            <div class="game-score__label">
              ${percent === 100 ? '🎉 Perfect score!' : percent >= 50 ? '👏 Good job!' : '🤔 Better luck next time!'}
            </div>
            <div class="game-actions">
              <button class="btn btn--primary btn--lg" id="game-next">
                ${icon('arrowRight', 18)}
                Next Round
              </button>
            </div>
          `;
          document.getElementById('game-next')?.addEventListener('click', startRound);
        }
      });
    }
  }

  startRound();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
