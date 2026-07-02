// ============================================
// Client-side hash router
// ============================================

const routes = {};
let currentCleanup = null;

export function route(path, handler) {
  routes[path] = handler;
}

function matchRoute(hash) {
  const path = hash.replace('#', '') || '/';

  // Try exact match first
  if (routes[path]) return { handler: routes[path], params: {} };

  // Try parameterized routes
  for (const [pattern, handler] of Object.entries(routes)) {
    const patternParts = pattern.split('/');
    const pathParts = path.split('/');

    if (patternParts.length !== pathParts.length) continue;

    const params = {};
    let match = true;

    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i].startsWith(':')) {
        params[patternParts[i].slice(1)] = pathParts[i];
      } else if (patternParts[i] !== pathParts[i]) {
        match = false;
        break;
      }
    }

    if (match) return { handler, params };
  }

  return null;
}

export function navigate(path) {
  window.location.hash = path;
}

export function getQueryParams() {
  const hash = window.location.hash.replace('#', '');
  const queryStart = hash.indexOf('?');
  if (queryStart === -1) return {};
  const params = new URLSearchParams(hash.slice(queryStart));
  return Object.fromEntries(params);
}

export function initRouter() {
  function handleRoute() {
    const hash = window.location.hash || '#/';
    const result = matchRoute(hash);

    if (result) {
      // Clean up previous page
      if (currentCleanup && typeof currentCleanup === 'function') {
        currentCleanup();
        currentCleanup = null;
      }

      const cleanup = result.handler(result.params);
      if (typeof cleanup === 'function') {
        currentCleanup = cleanup;
      }
    } else {
      // 404
      const app = document.getElementById('app');
      app.innerHTML = `
        <div class="page" style="display:flex;align-items:center;justify-content:center;text-align:center;">
          <div>
            <h1 style="font-size:6rem;margin-bottom:1rem;">🐾</h1>
            <h2 style="font-size:2rem;margin-bottom:0.5rem;">Page Not Found</h2>
            <p style="color:var(--color-text-secondary);margin-bottom:2rem;">This page doesn't exist. Maybe the dog ran away with it?</p>
            <a href="#/dashboard" class="btn btn--primary btn--lg">Go Home</a>
          </div>
        </div>
      `;
    }
  }

  window.addEventListener('hashchange', handleRoute);
  handleRoute();
}

export default { route, navigate, initRouter, getQueryParams };
