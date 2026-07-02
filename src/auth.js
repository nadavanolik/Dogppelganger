// ============================================
// Auth module — simulated Flask-Login sessions
// ============================================

const SESSION_KEY = 'dogppelganger_session';

let currentUser = null;

// Try to restore session on load
function restoreSession() {
  try {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      currentUser = JSON.parse(stored);
      return true;
    }
  } catch (e) { /* ignore */ }
  return false;
}

export const auth = {
  init() {
    return restoreSession();
  },

  isAuthenticated() {
    return currentUser !== null;
  },

  getCurrentUser() {
    return currentUser;
  },

  login(user) {
    currentUser = {
      id: user.id,
      username: user.username,
      email: user.email,
      avatar: user.avatar,
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(currentUser));
  },

  logout() {
    currentUser = null;
    localStorage.removeItem(SESSION_KEY);
  },
};

export default auth;
