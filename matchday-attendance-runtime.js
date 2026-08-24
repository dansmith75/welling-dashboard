// Final safety layer: completed Matchday minutes always count as a match appearance.
// Runs after all other dashboard UI wrappers so async load order cannot drop them.
(() => {
  function canonicalId(value) {
    const id = String(value || "").trim();
    return id === "keiran-d" ? "kieran-d" : id;
  }

  function mergeMatchdayAttendance() {
    const rows = Array.isArray(store.minutes) ? store.minutes : [];
    if (!rows.length) return;
    store.attendance = store.attendance || { sessions: [] };
    store.attendance.sessions = Array.isArray(store.attendance.sessions) ? store.attendance.sessions : [];

    const groups = new Map();
    rows.forEach(row => {
      const minutes = Number(row.minutes || 0);
      if (!Number.isFinite(minutes) || minutes <= 0 || !row.date) return;
      const key = String(row.matchId || row.date);
      if (!groups.has(key)) groups.set(key, { matchId: row.matchId || key, date: row.date, players: [] });
      groups.get(key).players.push(row);
    });

    groups.forEach(group => {
      let session = store.attendance.sessions.find(item => String(item?.type || "").toLowerCase() === "match" && String(item?.date || "") === String(group.date));
      if (!session) {
        const match = (store.matches || []).find(item => item.id === group.matchId);
        session = { sessionKey:`matchday-${group.matchId}`, sessionId:`matchday-${group.matchId}`, date:group.date, type:"Match", venue:match?.homeAway || match?.venue || null, submittedBy:"Matchday App", submittedAt:null, records:[] };
        store.attendance.sessions.push(session);
      }
      session.records = Array.isArray(session.records) ? session.records : [];
      group.players.forEach(row => {
        const pid = canonicalId(row.playerId);
        if (!pid) return;
        const displayName = pid === "kieran-d" ? "Kieran" : (row.displayName || pid);
        let record = session.records.find(item => canonicalId(item?.playerId) === pid);
        if (!record) {
          record = { playerId:pid, displayName, status:"Present", source:"Matchday App" };
          session.records.push(record);
        } else {
          record.playerId = pid;
          record.displayName = displayName;
          record.status = "Present";
          record.source = "Matchday App";
        }
      });
    });

    if (typeof legacyAttendanceRows === "function") store.matchAttendance = legacyAttendanceRows("Match");
  }

  window.ensureMatchdayAttendance = mergeMatchdayAttendance;

  const previousRenderAttendance = renderAttendance;
  renderAttendance = function () {
    mergeMatchdayAttendance();
    return previousRenderAttendance();
  };

  const previousRenderPlayerProfile = renderPlayerProfile;
  renderPlayerProfile = function (player) {
    mergeMatchdayAttendance();
    return previousRenderPlayerProfile(player);
  };

  // Re-merge after async minutes load, even if attendance loaded after minutes.
  const timer = setInterval(() => {
    if (!Array.isArray(store.minutes) || !store.minutes.length || !store.attendance?.sessions) return;
    mergeMatchdayAttendance();
    clearInterval(timer);
    if (document.getElementById("attendance")?.classList.contains("active")) renderAttendance();
    if (document.getElementById("players")?.classList.contains("active") && selectedPlayer) renderPlayerProfile(selectedPlayer);
  }, 250);
  setTimeout(() => clearInterval(timer), 10000);
})();
