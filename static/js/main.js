// ── Local time display ────────────────────────────────────────────────────────
document.querySelectorAll(".kickoff-time[data-utc]").forEach(el => {
  const d = new Date(el.dataset.utc);
  if (!isNaN(d)) {
    el.textContent = d.toLocaleDateString(undefined, {
      month: "short", day: "numeric"
    }) + " · " + d.toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit"
    });
  }
});

// ── Lock countdown ────────────────────────────────────────────────────────────
function formatCountdown(ms) {
  if (ms <= 0) return "Locked";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  if (h > 0) return `locks in ${h}h ${m}m`;
  if (m > 0) return `locks in ${m}m ${s}s`;
  return `locks in ${s}s`;
}

function updateCountdowns() {
  const now = Date.now();
  document.querySelectorAll(".lock-countdown[data-kickoff]").forEach(el => {
    const kickoff = new Date(el.dataset.kickoff).getTime();
    const lockTime = kickoff - 3600000; // 1 hour before
    el.textContent = formatCountdown(lockTime - now);
  });
}
updateCountdowns();
setInterval(updateCountdowns, 1000);

// ── Save predictions (AJAX) ───────────────────────────────────────────────────
document.querySelectorAll(".save-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    const matchId = btn.dataset.match;
    const card = btn.closest(".match-card");
    const homeInput = card.querySelector(".home-pred");
    const awayInput = card.querySelector(".away-pred");
    const statusEl = document.getElementById("status-" + matchId);

    const hp = parseInt(homeInput.value);
    const ap = parseInt(awayInput.value);

    if (isNaN(hp) || isNaN(ap)) {
      statusEl.textContent = "Enter both scores.";
      statusEl.className = "save-status save-err";
      return;
    }

    btn.disabled = true;
    statusEl.textContent = "Saving…";
    statusEl.className = "save-status";

    try {
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_id: matchId, home_pred: hp, away_pred: ap })
      });
      const data = await res.json();
      if (res.ok) {
        statusEl.textContent = "Saved ✓";
        statusEl.className = "save-status save-ok";
      } else {
        statusEl.textContent = data.error || "Error saving.";
        statusEl.className = "save-status save-err";
      }
    } catch {
      statusEl.textContent = "Network error.";
      statusEl.className = "save-status save-err";
    } finally {
      btn.disabled = false;
    }
  });
});

// ── Group code uppercase ──────────────────────────────────────────────────────
const codeInput = document.querySelector("input[name='code']");
if (codeInput) {
  codeInput.addEventListener("input", e => {
    e.target.value = e.target.value.toUpperCase();
  });
}
