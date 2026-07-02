// ============================================
// Multiplayer Lobby — `/game/lobbies`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast, timeAgo } from '../utils.js';

export function renderLobbies() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const app = document.getElementById('app');
  const navbar = app.querySelector('.navbar');
  const content = document.createElement('div');
  content.className = 'page';

  function render() {
    const lobbies = store.getLobbies();

    content.innerHTML = `
      <div class="container" style="max-width:800px;">
        <div class="lobbies-header">
          <h1 style="font-size:var(--text-3xl);">
            ${icon('users', 28)} <span class="text-gradient">Game Lobbies</span>
          </h1>
          <button class="btn btn--primary" id="create-lobby-btn">
            ${icon('plus', 16)}
            Create Lobby
          </button>
        </div>

        ${lobbies.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state__icon">🎮</div>
            <div class="empty-state__title">No open games</div>
            <p style="color:var(--color-text-secondary);margin-bottom:var(--space-4);">Create a lobby and invite others to play!</p>
          </div>
        ` : `
          <div class="lobby-list">
            ${lobbies.map(l => `
              <div class="lobby-card" data-lobby-id="${l.id}">
                <div style="width:48px;height:48px;background:linear-gradient(135deg,var(--color-primary),var(--color-secondary));border-radius:var(--radius-lg);display:flex;align-items:center;justify-content:center;font-size:1.5rem;flex-shrink:0;">
                  🎮
                </div>
                <div class="lobby-card__info">
                  <div class="lobby-card__name">${l.name}</div>
                  <div class="lobby-card__host">Hosted by @${l.hostUsername} · ${timeAgo(l.createdAt)}</div>
                </div>
                <div class="lobby-card__players">
                  ${icon('users', 16)}
                  ${l.players.length}/${l.maxPlayers}
                </div>
                <button class="btn btn--primary btn--sm lobby-join-btn" data-join-id="${l.id}" ${l.players.length >= l.maxPlayers ? 'disabled' : ''}>
                  ${l.players.length >= l.maxPlayers ? 'Full' : 'Join'}
                </button>
              </div>
            `).join('')}
          </div>
        `}

        <div style="text-align:center;margin-top:var(--space-8);">
          <a href="#/game" class="btn btn--ghost">
            ${icon('arrowLeft', 16)}
            Back to Single Player
          </a>
        </div>
      </div>

      <!-- Create lobby modal -->
      <div class="modal-overlay" id="create-lobby-modal" style="display:none;">
        <div class="modal">
          <div class="modal__header">
            <h3 class="modal__title">Create Game Lobby</h3>
            <button class="btn btn--icon btn--ghost" id="modal-close">${icon('x', 20)}</button>
          </div>
          <div class="form-group">
            <label for="lobby-name">Lobby Name</label>
            <input type="text" id="lobby-name" placeholder="e.g. Paw Patrol Squad" maxlength="30" />
          </div>
          <div style="display:flex;gap:var(--space-3);margin-top:var(--space-6);">
            <button class="btn btn--secondary" id="modal-cancel" style="flex:1;">Cancel</button>
            <button class="btn btn--primary" id="modal-create" style="flex:1;">
              ${icon('plus', 16)}
              Create
            </button>
          </div>
        </div>
      </div>
    `;

    // Create lobby
    document.getElementById('create-lobby-btn').addEventListener('click', () => {
      document.getElementById('create-lobby-modal').style.display = '';
      document.getElementById('lobby-name').focus();
    });

    const closeModal = () => {
      document.getElementById('create-lobby-modal').style.display = 'none';
    };
    document.getElementById('modal-close')?.addEventListener('click', closeModal);
    document.getElementById('modal-cancel')?.addEventListener('click', closeModal);

    document.getElementById('modal-create')?.addEventListener('click', () => {
      const name = document.getElementById('lobby-name').value.trim();
      if (!name) {
        toast('Please enter a lobby name', 'error');
        return;
      }
      const lobby = store.createLobby({ name, hostId: user.id, hostUsername: user.username });
      toast('Lobby created! 🎮', 'success');
      navigate(`/game/room/${lobby.id}`);
    });

    // Join lobby
    content.querySelectorAll('.lobby-join-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const lobbyId = btn.dataset.joinId;
        const result = store.joinLobby(lobbyId, user.id);
        if (result) {
          toast('Joined lobby!', 'success');
          navigate(`/game/room/${lobbyId}`);
        } else {
          toast('Could not join — lobby is full', 'error');
        }
      });
    });
  }

  render();

  app.innerHTML = '';
  if (navbar) app.appendChild(navbar);
  app.appendChild(content);
}
