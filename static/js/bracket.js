(function () {
  var dataEl = document.getElementById('bk-data');
  if (!dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  if (D.locked) return; // read-only view — nothing to wire up

  var picks = {};                 // mid(str) -> team
  Object.keys(D.picks).forEach(function (k) { picks[k] = D.picks[k]; });
  var slots = {};                 // mid(str) -> [home, away]
  Object.keys(D.slot_teams).forEach(function (k) { slots[k] = D.slot_teams[k].slice(); });
  var feeds = D.feeds;            // mid(str) -> [homeFeeder, awayFeeder]
  var ROUNDS = D.rounds_map;      // round -> [mid,...]
  var DOWNSTREAM = ['R16', 'QF', 'SF', 'FINAL'];

  function recompute() {
    DOWNSTREAM.forEach(function (rk) {
      ROUNDS[rk].forEach(function (mid) {
        var f = feeds[String(mid)];
        var home = picks[String(f[0])] || null;
        var away = picks[String(f[1])] || null;
        slots[String(mid)] = [home, away];
        var p = picks[String(mid)];
        if (p && p !== home && p !== away) {
          delete picks[String(mid)];
        }
      });
    });
  }

  function render() {
    document.querySelectorAll('.bk-match').forEach(function (matchEl) {
      var mid = matchEl.dataset.mid;
      var teams = slots[mid] || [null, null];
      var picked = picks[mid] || null;
      matchEl.querySelectorAll('.bk-team').forEach(function (btn) {
        var team = btn.dataset.pos === 'home' ? teams[0] : teams[1];
        btn.querySelector('.bk-team-name').textContent = team || '—';
        btn.classList.toggle('bk-empty', !team);
        btn.disabled = !team;
        btn.classList.toggle('bk-picked', !!team && picked === team);
      });
    });
    // Champion
    var champ = document.getElementById('bk-champion');
    if (champ) champ.textContent = picks['104'] || '—';
    // Progress
    var total = 0;
    Object.keys(ROUNDS).forEach(function (rk) {
      var n = ROUNDS[rk].reduce(function (acc, mid) {
        return acc + (picks[String(mid)] ? 1 : 0);
      }, 0);
      total += n;
      var pe = document.getElementById('bk-prog-' + rk);
      if (pe) pe.textContent = n + '/' + ROUNDS[rk].length;
    });
    var op = document.getElementById('bk-overall-progress');
    if (op) op.textContent = total + '/31 picked';
  }

  var toastTimer;
  function toast(msg, isError) {
    var t = document.getElementById('bk-toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'bk-toast show' + (isError ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'bk-toast'; }, 2200);
  }

  function save(mid, team) {
    fetch('/api/bracket/pick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ match_id: parseInt(mid, 10), picked_team: team })
    }).then(function (r) {
      if (r.status === 403) {
        toast('Bracket is locked — picks can no longer change.', true);
        setTimeout(function () { location.reload(); }, 1500);
        return null;
      }
      return r.json();
    }).then(function (resp) {
      if (!resp) return;
      if (resp.error) { toast(resp.error, true); return; }
      // Reconcile with authoritative server state (handles edge cases).
      picks = {};
      Object.keys(resp.picks).forEach(function (k) { picks[k] = resp.picks[k]; });
      slots = {};
      Object.keys(resp.slot_teams).forEach(function (k) { slots[k] = resp.slot_teams[k].slice(); });
      render();
    }).catch(function () {
      toast('Could not save — check your connection.', true);
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.bk-team');
    if (!btn || btn.disabled) return;
    var mid = btn.dataset.mid;
    var teams = slots[mid] || [null, null];
    var team = btn.dataset.pos === 'home' ? teams[0] : teams[1];
    if (!team) return;
    if (picks[mid] === team) return; // no-op re-tap
    picks[mid] = team;
    recompute();
    render();
    save(mid, team);
  });

  recompute();
  render();
})();
