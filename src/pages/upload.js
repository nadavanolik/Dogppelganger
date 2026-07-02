// ============================================
// Upload / Match — `/upload`
// ============================================

import { store } from '../store.js';
import { auth } from '../auth.js';
import { realtime } from '../realtime.js';
import { navigate } from '../router.js';
import { icon } from '../icons.js';
import { toast, readFileAsDataURL, formatFileSize } from '../utils.js';

export function renderUpload() {
  const user = auth.getCurrentUser();
  if (!user) return;

  const app = document.querySelector('.page-content') || document.getElementById('app');
  const content = document.createElement('div');
  content.className = 'page';
  content.innerHTML = `
    <div class="container" style="max-width:700px;">
      <h1 style="font-size:var(--text-3xl);margin-bottom:var(--space-2);text-align:center;">
        Upload Your <span class="text-gradient">Photo</span>
      </h1>
      <p style="color:var(--color-text-secondary);text-align:center;margin-bottom:var(--space-8);">
        Drop your photo below and we'll find your dog twin
      </p>

      <div class="upload-zone" id="upload-zone">
        <div class="upload-zone__icon">${icon('upload', 48)}</div>
        <div class="upload-zone__text">Drag & drop your photos here</div>
        <div class="upload-zone__hint">or click to browse — PNG, JPG up to 10MB</div>
        <input type="file" id="upload-input" accept="image/png,image/jpeg,image/jpg" multiple hidden />
      </div>

      <div class="upload-files-list" id="upload-files-list" style="display:none;"></div>

      <div class="upload-actions" id="upload-actions" style="display:none;">
        <button class="btn btn--secondary" id="upload-clear">Clear All</button>
        <button class="btn btn--primary btn--lg" id="upload-submit">
          ${icon('paw', 18)}
          Find My Dog Twin!
        </button>
      </div>

      <div id="upload-processing" style="display:none;"></div>
    </div>
  `;

  const appEl = document.getElementById('app');
  const navbar = appEl.querySelector('.navbar');
  appEl.innerHTML = '';
  if (navbar) appEl.appendChild(navbar);
  appEl.appendChild(content);

  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('upload-input');
  const filesList = document.getElementById('upload-files-list');
  const actions = document.getElementById('upload-actions');
  const processing = document.getElementById('upload-processing');
  let stagedFiles = [];

  // Click to browse
  zone.addEventListener('click', () => input.click());

  // Drag and drop
  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('dragover');
  });
  zone.addEventListener('dragleave', () => {
    zone.classList.remove('dragover');
  });
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
  });

  // File input change
  input.addEventListener('change', () => {
    handleFiles(input.files);
    input.value = '';
  });

  async function handleFiles(files) {
    for (const file of files) {
      // Validate
      if (!['image/png', 'image/jpeg', 'image/jpg'].includes(file.type)) {
        toast(`${file.name}: Invalid file type. Use PNG or JPG.`, 'error');
        continue;
      }
      if (file.size > 10 * 1024 * 1024) {
        toast(`${file.name}: File too large (max 10MB).`, 'error');
        continue;
      }

      const dataUrl = await readFileAsDataURL(file);
      stagedFiles.push({
        id: Math.random().toString(36).substr(2, 8),
        file,
        name: file.name,
        size: file.size,
        dataUrl,
        urgent: false,
      });
    }
    renderFileList();
  }

  function renderFileList() {
    if (stagedFiles.length === 0) {
      filesList.style.display = 'none';
      actions.style.display = 'none';
      zone.style.display = '';
      return;
    }

    zone.style.display = 'none';
    filesList.style.display = 'flex';
    actions.style.display = 'flex';

    filesList.innerHTML = stagedFiles.map(f => `
      <div class="upload-file-item" data-file-id="${f.id}">
        <img src="${f.dataUrl}" class="upload-file-item__thumb" alt="${f.name}" />
        <div class="upload-file-item__info">
          <div class="upload-file-item__name">${f.name}</div>
          <div class="upload-file-item__size">${formatFileSize(f.size)}</div>
        </div>
        <div class="upload-file-item__urgent">
          <label class="toggle">
            <input type="checkbox" ${f.urgent ? 'checked' : ''} data-urgent-id="${f.id}" />
            <span class="toggle__slider"></span>
          </label>
          <span>${icon('zap', 14)} Urgent</span>
        </div>
        <button class="btn btn--icon btn--ghost" data-remove-id="${f.id}" title="Remove">
          ${icon('x', 18)}
        </button>
      </div>
    `).join('');

    // Urgent toggles
    filesList.querySelectorAll('[data-urgent-id]').forEach(toggle => {
      toggle.addEventListener('change', () => {
        const sf = stagedFiles.find(f => f.id === toggle.dataset.urgentId);
        if (sf) sf.urgent = toggle.checked;
      });
    });

    // Remove buttons
    filesList.querySelectorAll('[data-remove-id]').forEach(btn => {
      btn.addEventListener('click', () => {
        stagedFiles = stagedFiles.filter(f => f.id !== btn.dataset.removeId);
        renderFileList();
      });
    });
  }

  // Clear all
  document.getElementById('upload-clear').addEventListener('click', () => {
    stagedFiles = [];
    renderFileList();
  });

  // Submit
  document.getElementById('upload-submit').addEventListener('click', () => {
    if (stagedFiles.length === 0) return;

    const isSingle = stagedFiles.length === 1;

    // Show processing UI
    filesList.style.display = 'none';
    actions.style.display = 'none';

    processing.style.display = 'block';
    processing.innerHTML = `
      <div class="upload-processing">
        <div class="spinner upload-processing__spinner" style="margin:0 auto;"></div>
        <div class="upload-processing__text">Finding your dog twin${stagedFiles.length > 1 ? 's' : ''}...</div>
        <p style="color:var(--color-text-secondary);font-size:var(--text-sm);">
          ${stagedFiles.length} image${stagedFiles.length > 1 ? 's' : ''} being processed
        </p>
        <div style="margin-top:var(--space-6);display:flex;flex-direction:column;gap:var(--space-3);" id="processing-items">
          ${stagedFiles.map(f => `
            <div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3);background:var(--color-bg-elevated);border-radius:var(--radius-lg);" data-proc-id="${f.id}">
              <img src="${f.dataUrl}" style="width:40px;height:40px;border-radius:var(--radius-md);object-fit:cover;" />
              <div style="flex:1;">
                <div style="font-size:var(--text-sm);">${f.name}</div>
                <div class="progress-bar" style="margin-top:var(--space-1);">
                  <div class="progress-bar__fill" style="width:0%;transition:width 0.5s ease;"></div>
                </div>
              </div>
              <span class="badge badge--info" style="font-size:10px;">Processing</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    // Create jobs and simulate processing
    const createdJobs = [];
    stagedFiles.forEach(f => {
      const job = store.createJob({
        userId: user.id,
        username: user.username,
        humanImage: f.dataUrl,
        urgent: f.urgent,
        fileSize: f.size,
      });
      job._fileId = f.id;
      createdJobs.push(job);
    });

    // Listen for progress on each job
    function onQueueUpdate(data) {
      const job = createdJobs.find(j => j.id === data.jobId);
      if (!job) return;
      const procEl = document.querySelector(`[data-proc-id="${job._fileId}"]`);
      if (procEl) {
        const fill = procEl.querySelector('.progress-bar__fill');
        if (fill) fill.style.width = `${data.progress}%`;
        if (data.status === 'done') {
          const badge = procEl.querySelector('.badge');
          if (badge) {
            badge.className = 'badge badge--success';
            badge.textContent = 'Done ✓';
            badge.style.fontSize = '10px';
          }
        }
      }
    }

    function onMatchReady(data) {
      const job = createdJobs.find(j => j.id === data.jobId);
      if (!job) return;
      job._done = true;

      const allDone = createdJobs.every(j => j._done);

      if (isSingle) {
        // Single image → redirect to result
        realtime.off('queue_update', onQueueUpdate);
        realtime.off('match_ready', onMatchReady);
        navigate(`/result/${data.matchId}`);
      } else if (allDone) {
        // All done → redirect to dashboard
        realtime.off('queue_update', onQueueUpdate);
        realtime.off('match_ready', onMatchReady);
        toast('All matches complete! 🎉', 'success');
        setTimeout(() => navigate('/dashboard'), 1000);
      }
    }

    realtime.on('queue_update', onQueueUpdate);
    realtime.on('match_ready', onMatchReady);

    // Start processing simulation for each job
    createdJobs.forEach(job => {
      realtime.simulateJobProcessing(job, store, auth);
    });
  });
}
