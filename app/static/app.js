// ─── Loading overlay ─────────────────────────────────────────
(function() {
  const overlay = document.getElementById('loading-overlay');
  if (!overlay) return;

  function showOverlay() { overlay.style.display = 'flex'; }
  function hideOverlay() { overlay.style.display = 'none'; }

  // Show on any non-HTMX form submit (tips, logout, admin, etc.)
  document.addEventListener('submit', function(e) {
    if (!e.target.closest('[hx-post],[hx-get],[hx-boost]')) {
      showOverlay();
    }
  });

  // HTMX: show overlay for non-rarity, non-modal requests (full-page actions like tip save)
  const _noOverlayPrefixes = ['rarity-', 'user-tips-modal'];
  function _isNoOverlay(targetId) {
    if (!targetId) return false;
    return _noOverlayPrefixes.some(p => targetId.startsWith(p));
  }

  document.addEventListener('htmx:beforeRequest', function(e) {
    const targetId = e.detail.target && e.detail.target.id;
    if (!_isNoOverlay(targetId)) {
      showOverlay();
    }
  });

  document.addEventListener('htmx:afterRequest', function(e) {
    const targetId = e.detail.target && e.detail.target.id;
    if (!_isNoOverlay(targetId)) {
      hideOverlay();
    }
  });

  // Poll /api/busy on page load – show overlay until files are free
  function checkBusy() {
    fetch('/api/busy')
      .then(r => r.json())
      .then(data => {
        if (data.busy) {
          showOverlay();
          setTimeout(checkBusy, 800);
        } else {
          hideOverlay();
        }
      })
      .catch(() => hideOverlay());
  }
  checkBusy();
})();

// ─── Clock ───────────────────────────────────────────────────
function updateClock() {
  const el = document.getElementById('clock');
  if (el) {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  }
}
setInterval(updateClock, 1000);
updateClock();

// ─── Countdown timers ────────────────────────────────────────
function fmtCountdown(seconds) {
  if (seconds <= 0) return 'ANPFIFF!';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (d > 0) return `${d}T ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function updateCountdowns() {
  const now = Date.now();
  document.querySelectorAll('[data-kickoff]').forEach(el => {
    const kickoff = new Date(el.dataset.kickoff).getTime();
    const diff = Math.floor((kickoff - now) / 1000);
    if (diff <= 0) {
      el.textContent = 'COUNTDOWN: ANPFIFF!';
      el.style.color = 'var(--red)';
    } else {
      el.textContent = 'COUNTDOWN: ' + fmtCountdown(diff);
    }
  });

  document.querySelectorAll('.countdown-sm[data-kickoff]').forEach(el => {
    const kickoff = new Date(el.dataset.kickoff).getTime();
    const diff = Math.floor((kickoff - now) / 1000);
    if (diff <= 0) {
      el.textContent = '';
    } else if (diff < 3600) {
      el.textContent = `(noch ${fmtCountdown(diff)})`;
      el.style.color = diff < 1800 ? 'var(--red)' : 'var(--amber)';
    } else {
      el.textContent = `(noch ${fmtCountdown(diff)})`;
    }
  });
}
setInterval(updateCountdowns, 1000);
updateCountdowns();

// ─── HTMX rarity panel rendering ─────────────────────────────
// The HTMX response from /api/rarity/<match_id> returns JSON.
// We intercept and render it as HTML.
document.addEventListener('htmx:afterRequest', function(e) {
  const target = e.detail.target;
  if (!target || !target.id || !target.id.startsWith('rarity-')) return;

  try {
    const data = JSON.parse(e.detail.xhr.responseText);
    renderRarityPanel(target, data);
  } catch(err) {
    target.innerHTML = '<div class="rarity-loading">FEHLER BEIM LADEN</div>';
  }
});

function pct(share) {
  return (share * 100).toFixed(1);
}

function renderRarityPanel(el, data) {
  const frozen = data.frozen;
  const total = data.total_tips || 0;

  let html = `<div class="rarity-title">`;
  html += frozen ? 'TIPPVERTEILUNG (EINGEFROREN)' : 'RARITÄTSBONUS LIVE';
  html += ` <button class="info-btn" onclick="openModal('modal-scoring')" title="Punktesystem">ℹ</button>`;
  html += `</div>`;

  html += `<div class="rarity-bars">`;
  html += rarityBar('HEIMSIEG', data.home_win_pct, 'bar-home');
  html += rarityBar('UNENTSCHIEDEN', data.draw_pct, 'bar-draw');
  html += rarityBar('AUSWÄRTSSIEG', data.away_win_pct, 'bar-away');
  html += `</div>`;

  if (data.rarity_factor !== undefined && !frozen) {
    const hasCalc = data.rarity_share !== null && data.rarity_share !== undefined;
    const sharePct = hasCalc ? (data.rarity_share * 100).toFixed(1) : null;
    const tLabel = hasCalc ? ({home:'HEIMSIEG', draw:'UNENTSCHIEDEN', away:'AUSWÄRTSSIEG'}[data.rarity_tendency] || data.rarity_tendency) : null;
    const result = data.rarity_factor.toFixed(2);
    html += `<div class="rarity-bonus-line">`;
    if (data.rarity_factor > 1.0) {
      html += `RARITÄTSFAKTOR: <span class="rarity-potential">×${result}</span>`;
    } else {
      html += `RARITÄTSFAKTOR: <span class="rarity-potential rarity-neutral">×1.00</span>`;
    }
    if (hasCalc) {
      html += ` <button class="info-btn" onclick="openRarityModal('${sharePct}', '${tLabel}', '${result}')" title="Berechnung &amp; Erklärung">ℹ</button>`;
    }
    html += `</div>`;
  }

  html += `<div class="rarity-note">${total} Tipp${total !== 1 ? 's' : ''} gesamt`;
  if (!frozen) html += ` · <span class="rarity-frozen-note">Wird zum Anpfiff eingefroren</span>`;
  html += `</div>`;

  el.innerHTML = html;
}

function rarityBar(label, pct_val, cls) {
  const w = Math.min(Math.max(pct_val, 0), 100);
  return `
    <div class="rarity-bar">
      <span class="rarity-label">${label}</span>
      <div class="bar-track"><div class="bar-fill ${cls}" style="width:${w}%"></div></div>
      <span class="rarity-pct">${pct_val.toFixed(1)}%</span>
    </div>`;
}

function openRarityModal(sharePct, tLabel, result) {
  const calcEl = document.getElementById('rarity-modal-calc');
  if (calcEl) {
    calcEl.innerHTML = `
      <div class="info-sep"></div>
      <div class="info-note" style="color:var(--gold);font-style:normal">DEINE AKTUELLE BERECHNUNG</div>
      <div class="info-row"><span class="info-pts">→</span><span>Deine Tendenz: <strong>${tLabel}</strong></span></div>
      <div class="info-row"><span class="info-pts">%</span><span>${sharePct}% aller Tipps liegen auf ${tLabel}</span></div>
      <div class="info-row info-row-special"><span class="info-pts info-pts-purple">×${result}</span><span>Faktor = 2 − ${sharePct}% = <strong>×${result}</strong></span></div>
    `;
  }
  openModal('modal-rarity');
}

// ─── Info modals ─────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.style.display = 'flex'; document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) { el.style.display = 'none'; document.body.style.overflow = ''; }
}
function openUserModal(url) {
  const body = document.getElementById('user-tips-modal-body');
  if (!body) return;
  body.innerHTML = '<div style="color:rgba(255,255,255,0.4);font-size:0.55rem;padding:1rem;text-align:center;">Lade...</div>';
  openModal('modal-user-tips');
  fetch(url)
    .then(r => r.text())
    .then(html => { body.innerHTML = html; })
    .catch(() => { body.innerHTML = '<div style="color:var(--red);padding:1rem">Fehler beim Laden.</div>'; });
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.info-modal').forEach(m => {
      m.style.display = 'none';
    });
    document.body.style.overflow = '';
  }
});

// ─── Nav expand ──────────────────────────────────────────────
function toggleNavExpand() {
  const panel = document.getElementById('nav-all-matchdays');
  const btn = document.getElementById('nav-expand-btn');
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : 'flex';
  if (btn) btn.textContent = isOpen ? '+' : '−';
}

// ─── Save / risk char burst animation ────────────────────────
function showSaveChar(type) {
  const src = (type === 'risk' ? '/static/large_risk.png' : '/static/yes_large.png') + '?v=' + Date.now();
  const wrap = document.createElement('div');
  wrap.className = 'char-burst char-burst-' + type;
  const img = document.createElement('img');
  img.src = src;
  img.className = 'char-burst-img';
  wrap.appendChild(img);
  document.body.appendChild(wrap);
  setTimeout(function() { if (wrap.parentNode) wrap.remove(); }, 2500);
}

// Trigger animation from URL param after successful server redirect
(function() {
  const params = new URLSearchParams(window.location.search);
  const saved = params.get('saved');
  if (saved === 'yes' || saved === 'risk') {
    showSaveChar(saved);
    const url = new URL(window.location);
    url.searchParams.delete('saved');
    history.replaceState({}, '', url);
  }
})();

// ─── Tip form: sync risk flag with risk button state ──────────
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.tip-form').forEach(form => {
    const matchId = form.action.split('/tip/')[1];
    if (!matchId) return;
    const riskFlag = document.getElementById('risk_flag_' + matchId);
    // Risk state is managed server-side; hidden input already set correctly.
  });
});

// ─── Admin: adjust points for a user ────────────────────────
function adminAdjustPts(username, matchId, newVal) {
  const delta = parseFloat(newVal);
  if (isNaN(delta)) return;
  fetch('/admin/users/' + encodeURIComponent(username) + '/adjust', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'delta=' + encodeURIComponent(delta) + '&note=' + encodeURIComponent('manual adj ' + matchId),
  }).then(r => {
    if (!r.ok) console.warn('Adjust failed', r.status);
  });
}
