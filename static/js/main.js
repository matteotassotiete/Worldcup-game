// ── Flag data ─────────────────────────────────────────────────────────────────
const FLAG_MAP = {
  'Mexico': 'mx', 'South Africa': 'za', 'Korea Republic': 'kr', 'Czechia': 'cz',
  'Canada': 'ca', 'Bosnia-H.': 'ba', 'USA': 'us', 'Paraguay': 'py',
  'Qatar': 'qa', 'Switzerland': 'ch', 'Argentina': 'ar', 'Brazil': 'br',
  'France': 'fr', 'Germany': 'de', 'Spain': 'es', 'England': 'gb-eng',
  'Portugal': 'pt', 'Italy': 'it', 'Netherlands': 'nl', 'Belgium': 'be',
  'Croatia': 'hr', 'Uruguay': 'uy', 'Colombia': 'co', 'Ecuador': 'ec',
  'Chile': 'cl', 'Peru': 'pe', 'Venezuela': 've', 'Bolivia': 'bo',
  'Morocco': 'ma', 'Senegal': 'sn', 'Nigeria': 'ng', 'Egypt': 'eg',
  'Cameroon': 'cm', 'Ghana': 'gh', 'Tunisia': 'tn', 'Algeria': 'dz',
  "Côte d'Ivoire": 'ci', 'Ivory Coast': 'ci', 'Japan': 'jp',
  'Australia': 'au', 'Iran': 'ir', 'Saudi Arabia': 'sa',
  'Costa Rica': 'cr', 'Honduras': 'hn', 'Panama': 'pa', 'Jamaica': 'jm',
  'El Salvador': 'sv', 'Haiti': 'ht', 'Trinidad and Tobago': 'tt',
  'Serbia': 'rs', 'Austria': 'at', 'Denmark': 'dk', 'Poland': 'pl',
  'Ukraine': 'ua', 'Turkey': 'tr', 'Scotland': 'gb-sct', 'Wales': 'gb-wls',
  'Slovakia': 'sk', 'Romania': 'ro', 'New Zealand': 'nz', 'Hungary': 'hu',
  'Slovenia': 'si', 'Albania': 'al', 'North Macedonia': 'mk', 'Montenegro': 'me',
  'Greece': 'gr', 'Norway': 'se', 'Sweden': 'se', 'Finland': 'fi',
  'Iceland': 'is', 'Israel': 'il', 'Mali': 'ml', 'Guinea': 'gn',
  'DR Congo': 'cd', 'Zambia': 'zm', 'Namibia': 'na', 'Zimbabwe': 'zw',
  'Mozambique': 'mz', 'Tanzania': 'tz', 'Uganda': 'ug', 'Kenya': 'ke',
  'Angola': 'ao', 'Cape Verde': 'cv', 'Equatorial Guinea': 'gq',
  'Burkina Faso': 'bf', 'Benin': 'bj', 'Comoros': 'km', 'Sudan': 'sd',
  'Libya': 'ly', 'Jordan': 'jo', 'Iraq': 'iq', 'UAE': 'ae',
  'Uzbekistan': 'uz', 'Kyrgyzstan': 'kg', 'Tajikistan': 'tj',
  'Thailand': 'th', 'Vietnam': 'vn', 'Philippines': 'ph',
  'Indonesia': 'id', 'Malaysia': 'my', 'China': 'cn', 'India': 'in',
  'Kazakhstan': 'kz', 'Bahrain': 'bh', 'Kuwait': 'kw', 'Oman': 'om',
  'Myanmar': 'mm', 'Singapore': 'sg', 'Taiwan': 'tw',
};

function flagUrl(teamName) {
  const code = FLAG_MAP[teamName];
  return code ? `https://flagcdn.com/w40/${code}.png` : null;
}

function flagImg(teamName) {
  const url = flagUrl(teamName);
  if (!url) return '';
  return `<img class="team-flag" src="${url}" alt="${teamName}" onerror="this.style.display='none'">`;
}

// ── Flag Strip ────────────────────────────────────────────────────────────────
function buildFlagStrip() {
  const track = document.querySelector('#flag-strip .flag-track');
  if (!track) return;
  const teams = Object.entries(FLAG_MAP).slice(0, 40);
  let html = '';
  for (let rep = 0; rep < 2; rep++) {
    for (const [name, code] of teams) {
      html += `<div class="flag-item">
        <img src="https://flagcdn.com/w40/${code}.png" alt="${name}" onerror="this.parentElement.style.display='none'">
        <span>${name}</span>
      </div>`;
    }
  }
  track.innerHTML = html;
}
buildFlagStrip();

// ── Inject flags into match cards ─────────────────────────────────────────────
document.querySelectorAll('.team[data-name]').forEach(el => {
  const name = el.dataset.name;
  const img = flagImg(name);
  const nameEl = el.querySelector('.team-name-text');
  if (img && nameEl) {
    const imgEl = document.createElement('div');
    imgEl.innerHTML = img;
    if (el.classList.contains('home')) {
      nameEl.after(imgEl.firstChild);
    } else {
      nameEl.before(imgEl.firstChild);
    }
  }
});

// ── Floating footballs background ────────────────────────────────────────────
function spawnBalls() {
  const count = 8;
  for (let i = 0; i < count; i++) {
    const el = document.createElement('div');
    el.className = 'bg-ball';
    el.textContent = '⚽';
    el.style.left = `${Math.random() * 100}%`;
    el.style.animationDuration = `${12 + Math.random() * 18}s`;
    el.style.animationDelay = `${-Math.random() * 20}s`;
    el.style.fontSize = `${1 + Math.random() * 2}rem`;
    document.body.appendChild(el);
  }
}
spawnBalls();

// ── Local time display ────────────────────────────────────────────────────────
document.querySelectorAll('.kickoff-time[data-utc]').forEach(el => {
  const d = new Date(el.dataset.utc);
  if (!isNaN(d)) {
    el.textContent = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      + ' · ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }
});

// ── Lock countdown ────────────────────────────────────────────────────────────
function formatCountdown(ms) {
  if (ms <= 0) return 'Locked';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  if (h > 0) return `locks in ${h}h ${m}m`;
  if (m > 0) return `locks in ${m}m ${s}s`;
  return `locks in ${s}s`;
}

function updateCountdowns() {
  const now = Date.now();
  document.querySelectorAll('.lock-countdown[data-kickoff]').forEach(el => {
    const lockTime = new Date(el.dataset.kickoff).getTime() - 3600000;
    const ms = lockTime - now;
    el.textContent = formatCountdown(ms);
    el.classList.toggle('urgent', ms > 0 && ms < 7200000);
    el.classList.toggle('critical', ms > 0 && ms < 1800000);
  });
}
updateCountdowns();
setInterval(updateCountdowns, 1000);

// ── Confetti burst ────────────────────────────────────────────────────────────
function confetti(el) {
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const colors = ['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6', '#fbbf24'];
  for (let i = 0; i < 18; i++) {
    const dot = document.createElement('div');
    dot.style.cssText = `
      position:fixed; width:7px; height:7px; border-radius:50%;
      background:${colors[i % colors.length]};
      left:${cx}px; top:${cy}px;
      pointer-events:none; z-index:9999;
      animation: none;
    `;
    document.body.appendChild(dot);
    const angle = (i / 18) * Math.PI * 2;
    const dist = 60 + Math.random() * 60;
    const tx = Math.cos(angle) * dist;
    const ty = Math.sin(angle) * dist - 30;
    dot.animate([
      { transform: 'translate(0,0) scale(1)', opacity: 1 },
      { transform: `translate(${tx}px,${ty}px) scale(0)`, opacity: 0 }
    ], { duration: 600, easing: 'cubic-bezier(.2,.8,.4,1)', fill: 'forwards' })
      .onfinish = () => dot.remove();
  }
}

// ── Save predictions (AJAX) ───────────────────────────────────────────────────
document.querySelectorAll('.save-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const matchId = btn.dataset.match;
    const card = btn.closest('.match-card');
    const homeInput = card.querySelector('.home-pred');
    const awayInput = card.querySelector('.away-pred');
    const statusEl = document.getElementById('status-' + matchId);

    const hp = parseInt(homeInput.value);
    const ap = parseInt(awayInput.value);

    if (isNaN(hp) || isNaN(ap)) {
      statusEl.textContent = 'Enter both scores.';
      statusEl.className = 'save-status save-err';
      return;
    }

    btn.disabled = true;
    btn.textContent = '…';
    statusEl.className = 'save-status';
    statusEl.textContent = '';

    try {
      const res = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_id: matchId, home_pred: hp, away_pred: ap })
      });
      const data = await res.json();
      if (res.ok) {
        statusEl.textContent = 'Saved ✓';
        statusEl.className = 'save-status save-ok';
        confetti(btn);
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = 'Save'; btn.disabled = false; }, 1500);
      } else {
        statusEl.textContent = data.error || 'Error saving.';
        statusEl.className = 'save-status save-err';
        btn.textContent = 'Save';
        btn.disabled = false;
      }
    } catch {
      statusEl.textContent = 'Network error.';
      statusEl.className = 'save-status save-err';
      btn.textContent = 'Save';
      btn.disabled = false;
    }
  });
});

// ── Stagger card animations ───────────────────────────────────────────────────
document.querySelectorAll('.match-card').forEach((card, i) => {
  card.style.animationDelay = `${i * 40}ms`;
});

// ── Group code uppercase ──────────────────────────────────────────────────────
const codeInput = document.querySelector("input[name='code']");
if (codeInput) {
  codeInput.addEventListener('input', e => { e.target.value = e.target.value.toUpperCase(); });
}
