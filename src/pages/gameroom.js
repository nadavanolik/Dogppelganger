// ============================================
// Multiplayer Game Room — `/game/room/:lobbyId`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast } from '../utils.js';

export function renderGameRoom(params) {
  const user = auth.getCurrentUser();
  if (!user) return;

  const lobby = store.getLobby(params.lobbyId);
  if (!lobby) {
    navigate('/game/lobbies');
    return;
  }

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  let gameState = 'waiting'; // waiting | playing | results
  let timer = 30;
  let timerInterval = null;
  let roundData = null;
  let selectedHuman = null;
  let selectedDog = null;
  let myPairs = {};
  let botPairs = {};
  let myScore = 0;
  let botScore = 0;
  let round = 1;

  // Simulate a bot opponent
  const botName = lobby.players.length > 1
    ? store.getUser(lobby.players.find(p => p !== user.id))?.username || 'Bot'
    : 'AI Opponent';

  function renderRoom() {
    content.innerHTML = `
      <div class="container game-container">
        <div class="gameroom-header">
          <h1 style="font-size:var(--text-2xl);">
            ${icon('gamepad', 24)} ${lobby.name}
          </h1>
          <div style="display:flex;gap:var(--space-3);">
            <span class="badge badge--info">Round ${round}</span>
            <button class="btn btn--danger btn--sm" id="leave-lobby">
              ${icon('x', 14)} Leave
            </button>
          </div>
        </div>

        <!-- Players -->
        <div class="gameroom-players">
          <div class="gameroom-player ${gameState !== 'waiting' ? 'gameroom-player--ready' : ''}">
            <img src="${user.avatar}" class="avatar avatar--sm" alt="" />
            ${user.username} (You)
          </div>
          <div class="gameroom-player ${gameState !== 'waiting' ? 'gameroom-player--ready' : ''}">
            🤖 ${botName}
          </div>
        </div>

        <!-- Scoreboard -->
        <div class="gameroom-scoreboard">
          <div class="gameroom-score">
            <div class="gameroom-score__name">${user.username}</div>
            <div class="gameroom-score__value" style="color:var(--color-primary);">${myScore}</div>
          </div>
          <div style="font-size:var(--text-2xl);color:var(--color-text-tertiary);display:flex;align-items:center;">vs</div>
          <div class="gameroom-score">
            <div class="gameroom-score__name">${botName}</div>
            <div class="gameroom-score__value" style="color:var(--color-secondary);">${botScore}</div>
          </div>
        </div>

        ${gameState === 'waiting' ? `
          <div style="text-align:center;padding:var(--space-12);">
            <div style="font-size:3rem;margin-bottom:var(--space-4);">🎮</div>
            <h2 style="margin-bottom:var(--space-4);">Ready to Play?</h2>
            <p style="color:var(--color-text-secondary);margin-bottom:var(--space-6);">
              Match the humans with their dog twins faster than your opponent!
            </p>
            <button class="btn btn--primary btn--lg" id="start-game">
              ${icon('paw', 18)} Start Game
            </button>
          </div>
        ` : ''}

        ${gameState === 'playing' ? `
          <div class="gameroom-timer">${timer}s</div>
          <div class="game-board">
            <div class="game-column">
              <div class="game-column__title">Humans 👤</div>
              ${roundData.humans.map(h => {
                const isPaired = myPairs[h.id] !== undefined;
                const isSelected = selectedHuman === h.id;
                return `
                  <div class="game-card ${isSelected ? 'selected' : ''} ${isPaired ? 'selected' : ''}" data-human-id="${h.id}" style="opacity:${isPaired ? '0.6' : '1'}">
                    <img src="${h.image}" alt="${h.username}" />
                    <div class="game-card__label">@${h.username}</div>
                    <div class="game-card__check">${icon('check', 16)}</div>
                  </div>
                `;
              }).join('')}
            </div>
            <div class="game-lines" style="display:flex;align-items:center;justify-content:center;">
              <div style="color:var(--color-text-tertiary);font-size:var(--text-sm);">
                ${Object.keys(myPairs).length}/${roundData.humans.length}
              </div>
            </div>
            <div class="game-column">
              <div class="game-column__title">Dogs 🐕</div>
              ${roundData.dogs.map(d => {
                const isPaired = Object.values(myPairs).includes(d.id);
                const isSelected = selectedDog === d.id;
                return `
                  <div class="game-card ${isSelected ? 'selected' : ''} ${isPaired ? 'selected' : ''}" data-dog-id="${d.id}" style="opacity:${isPaired ? '0.6' : '1'}">
                    <img src="${d.image}" alt="${d.breed}" />
                    <div class="game-card__label">${d.breed}</div>
                    <div class="game-card__check">${icon('check', 16)}</div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
          <div class="game-actions">
            <button class="btn btn--primary btn--lg" id="submit-round" ${Object.keys(myPairs).length < roundData.humans.length ? 'disabled' : ''}>
              ${icon('check', 18)} Submit
            </button>
          </div>
        ` : ''}

        ${gameState === 'results' ? `
          <div class="game-score" id="round-results">
            <!-- Filled after scoring -->
          </div>
        ` : ''}
      </div>
    `;

    // Event handlers
    document.getElementById('leave-lobby')?.addEventListener('click', () => {
      store.leaveLobby(lobby.id, user.id);
      if (timerInterval) clearInterval(timerInterval);
      toast('Left the lobby', 'info');
      navigate('/game/lobbies');
    });

    document.getElementById('start-game')?.addEventListener('click', startGame);

    if (gameState === 'playing') {
      content.querySelectorAll('[data-human-id]').forEach(card => {
        card.addEventListener('click', () => {
          const id = card.dataset.humanId;
          if (myPairs[id] !== undefined) return;
          selectedHuman = selectedHuman === id ? null : id;
          if (selectedHuman && selectedDog) {
            myPairs[selectedHuman] = selectedDog;
            selectedHuman = null;
            selectedDog = null;
          }
          renderRoom();
        });
      });

      content.querySelectorAll('[data-dog-id]').forEach(card => {
        card.addEventListener('click', () => {
          const id = card.dataset.dogId;
          if (Object.values(myPairs).includes(id)) return;
          selectedDog = selectedDog === id ? null : id;
          if (selectedHuman && selectedDog) {
            myPairs[selectedHuman] = selectedDog;
            selectedHuman = null;
            selectedDog = null;
          }
          renderRoom();
        });
      });

      document.getElementById('submit-round')?.addEventListener('click', submitRound);
    }
  }

  function startGame() {
    roundData = store.generateRound(4);
    selectedHuman = null;
    selectedDog = null;
    myPairs = {};
    botPairs = {};
    timer = 30;
    gameState = 'playing';
    renderRoom();

    // Start timer
    timerInterval = setInterval(() => {
      timer--;
      const timerEl = content.querySelector('.gameroom-timer');
      if (timerEl) timerEl.textContent = `${timer}s`;
      if (timer <= 0) {
        clearInterval(timerInterval);
        submitRound();
      }
    }, 1000);

    // Simulate bot making pairs
    simulateBotPairs();
  }

  function simulateBotPairs() {
    // Bot randomly pairs after some time
    const shuffledHumans = [...roundData.humans].sort(() => Math.random() - 0.5);
    const shuffledDogs = [...roundData.dogs].sort(() => Math.random() - 0.5);
    shuffledHumans.forEach((h, i) => {
      botPairs[h.id] = shuffledDogs[i].id;
    });
  }

  function submitRound() {
    if (timerInterval) clearInterval(timerInterval);
    gameState = 'results';

    // Fill any unpaired with random
    if (roundData) {
      const unpairedHumans = roundData.humans.filter(h => !myPairs[h.id]);
      const unpairedDogs = roundData.dogs.filter(d => !Object.values(myPairs).includes(d.id));
      unpairedHumans.forEach((h, i) => {
        if (unpairedDogs[i]) myPairs[h.id] = unpairedDogs[i].id;
      });
    }

    const myResult = store.checkAnswer(roundData.token, myPairs);
    const botResult = store.checkAnswer(roundData.token, botPairs);

    myScore += myResult.correct;
    botScore += botResult.correct;

    renderRoom();

    const resultsEl = document.getElementById('round-results');
    if (resultsEl) {
      const won = myResult.correct > botResult.correct;
      const tied = myResult.correct === botResult.correct;
      resultsEl.innerHTML = `
        <div style="font-size:3rem;margin-bottom:var(--space-4);">${won ? '🎉' : tied ? '🤝' : '😅'}</div>
        <h2 style="margin-bottom:var(--space-4);">${won ? 'You Won This Round!' : tied ? 'It\'s a Tie!' : 'Bot Wins This Round!'}</h2>
        <p style="color:var(--color-text-secondary);margin-bottom:var(--space-6);">
          You got ${myResult.correct}/${myResult.total} · Bot got ${botResult.correct}/${botResult.total}
        </p>
        <div class="game-actions">
          <button class="btn btn--primary btn--lg" id="next-round">
            ${icon('arrowRight', 18)} Next Round
          </button>
          <button class="btn btn--secondary" id="end-game">End Game</button>
        </div>
      `;

      document.getElementById('next-round')?.addEventListener('click', () => {
        round++;
        startGame();
      });

      document.getElementById('end-game')?.addEventListener('click', () => {
        if (timerInterval) clearInterval(timerInterval);
        store.leaveLobby(lobby.id, user.id);
        const finalWin = myScore > botScore;
        toast(finalWin ? `You won ${myScore}-${botScore}! 🏆` : `Game over! ${myScore}-${botScore}`, finalWin ? 'success' : 'info');
        navigate('/game/lobbies');
      });
    }
  }

  renderRoom();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);

  return () => {
    if (timerInterval) clearInterval(timerInterval);
  };
}
