// ============================================
// Dogppelganger — Main Entry Point
// ============================================

import './styles/index.css';
import './styles/navbar.css';
import './styles/pages.css';

import { route, initRouter, navigate } from './router.js';
import { auth } from './auth.js';
import { renderNavbar, initNavbarEvents } from './components/navbar.js';

// Pages
import { renderLanding } from './pages/landing.js';
import { renderSignup } from './pages/signup.js';
import { renderLogin } from './pages/login.js';
import { renderDashboard } from './pages/dashboard.js';
import { renderUpload } from './pages/upload.js';
import { renderResult } from './pages/result.js';
import { renderGallery } from './pages/gallery.js';
import { renderGame } from './pages/game.js';
import { renderLobbies } from './pages/lobbies.js';
import { renderGameRoom } from './pages/gameroom.js';
import { renderForum } from './pages/forum.js';
import { renderPost } from './pages/post.js';
import { renderNewPost } from './pages/newpost.js';
import { renderMessages } from './pages/messages.js';
import { renderConversation } from './pages/conversation.js';

// Initialize auth from stored session
auth.init();

// Helper: wrap a page renderer with navbar + auth guard
function publicPage(renderer) {
  return (params) => {
    // Redirect authenticated users to dashboard
    if (auth.isAuthenticated()) {
      navigate('/dashboard');
      return;
    }
    const app = document.getElementById('app');
    app.innerHTML = '';
    const nav = renderNavbar();
    app.appendChild(nav);
    initNavbarEvents();
    return renderer(params);
  };
}

function authPage(renderer) {
  return (params) => {
    if (!auth.isAuthenticated()) {
      const currentPath = window.location.hash.replace('#', '');
      navigate(`/login?next=${encodeURIComponent(currentPath)}`);
      return;
    }
    const app = document.getElementById('app');
    app.innerHTML = '';
    const nav = renderNavbar();
    app.appendChild(nav);
    initNavbarEvents();
    return renderer(params);
  };
}

// Landing is special — public but shows differently for auth users
function landingPage() {
  return () => {
    if (auth.isAuthenticated()) {
      navigate('/dashboard');
      return;
    }
    const app = document.getElementById('app');
    app.innerHTML = '';
    const nav = renderNavbar();
    app.appendChild(nav);
    initNavbarEvents();
    renderLanding();
  };
}

// ---- Register Routes ----

// PUBLIC
route('/', landingPage());
route('/signup', publicPage(renderSignup));
route('/login', (params) => {
  // Login is special — don't redirect if already authed (handled in the page)
  if (auth.isAuthenticated()) {
    navigate('/dashboard');
    return;
  }
  const app = document.getElementById('app');
  app.innerHTML = '';
  const nav = renderNavbar();
  app.appendChild(nav);
  initNavbarEvents();
  return renderLogin(params);
});

// AUTH
route('/dashboard', authPage(renderDashboard));
route('/upload', authPage(renderUpload));
route('/result/:matchId', authPage(renderResult));
route('/gallery', authPage(renderGallery));
route('/game', authPage(renderGame));
route('/game/lobbies', authPage(renderLobbies));
route('/game/room/:lobbyId', authPage(renderGameRoom));
route('/forum', authPage(renderForum));
route('/forum/new', authPage(renderNewPost));
route('/forum/post/:postId', authPage(renderPost));
route('/messages', authPage(renderMessages));
route('/messages/:conversationId', authPage(renderConversation));
route('/notifications', authPage(renderDashboard)); // Notifications mostly in dropdown; page falls back to dashboard

// ---- Start Router ----
initRouter();
