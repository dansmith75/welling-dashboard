// Player minutes reporting and player-summary layout for the Welling dashboard.
// Completed Matchday data is authoritative for appearances and match attendance.
(() => {
  const MINUTES_URL = "data/minutes.json";

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function canonicalId(value) {
    const id = String(value || "").trim();
    if (id === "keiran-d") return "kieran-d";
    return id;
  }

  function playerIdentity(player) {
    const name = String(player || "").trim();
    const squadPlayer = (store.players || []).find(item =>
      String(item?.displayName || "").trim() === name || canonicalId(item?.id) === canonicalId(name)
    );
    return {
      name,
      id: canonicalId(squadPlayer?.id || name)
    };
  }

  function recordMatchesPlayer(record, player) {
    const identity = playerIdentity(player);
    return canonicalId(record?.playerId) === identity.id ||
      String(record?.displayName || "").trim() === identity.name;
  }

  function recordsForPlayer(player) {
    return (store.minutes || []).filter(record => recordMatchesPlayer(record, player));
  }

  function mergeMatchdayAttendance(rows) {
    store.attendance = store.attendance || { sessions: [] };
    store.attendance.sessions = Array.isArray(store.attendance.sessions) ? store.attendance.sessions : [];

    const groups = new Map();
    (rows || [])
      .filter(record => number(record.minutes) > 0 && record.date)
      .forEach(record => {
        const key = String(record.matchId || record.date);
        if (!groups.has(key)) {
          groups.set(key, {
            matchId: record.matchId || key,
            date: record.date,
            opposition: record.opposition || "",
            competition: record.competition || "",
            players: []
          });
        }
        groups.get(key).players.push(record);
      });

    groups.forEach(group => {
      let session = store.attendance.sessions.find(item =>
        String(item?.type || "").toLowerCase() === "match" &&
        String(item?.date || "") === String(group.date)
      );

      if (!session) {
        session = {
          sessionKey: `matchday-${group.matchId}`,
          sessionId: `matchday-${group.matchId}`,
          date: group.date,
          type: "Match",
          venue: (store.matches || []).find(match => match.id === group.matchId)?.homeAway || null,
          submittedBy: "Matchday App",
          submittedAt: null,
          records: []
        };
        store.attendance.sessions.push(session);
      }

      session.records = Array.isArray(session.records) ? session.records : [];

      group.players.forEach(record => {
        const pid = canonicalId(record.playerId);
        const displayName = pid === "kieran-d" ? "Kieran" : (record.displayName || pid);
        let attendanceRecord = session.records.find(item => canonicalId(item?.playerId) === pid);

        if (!attendanceRecord) {
          attendanceRecord = {
            playerId: pid,
            displayName,
            status: "Present",
            source: "Matchday App"
          };
          session.records.push(attendanceRecord);
        } else {
          // A completed Matchday appearance overrides an older absent/blank attendance value.
          attendanceRecord.playerId = pid;
          attendanceRecord.displayName = displayName;
          attendanceRecord.status = "Present";
          attendanceRecord.source = attendanceRecord.source || "Matchday App";
        }
      });
    });

    // Rebuild the legacy rows consumed by the Attendance charts/profile counters.
    if (typeof legacyAttendanceRows === "function") {
      store.matchAttendance = legacyAttendanceRows("Match");
    }
  }

  function appearanceRecords(player) {
    const seen = new Set();
    const appearances = [];

    if (typeof attendanceRecordsForPlayer === "function") {
      attendanceRecordsForPlayer(player, "Match")
        .filter(record => typeof isAttendancePresent === "function" ? isAttendancePresent(record.status) : /^(present|late)$/i.test(String(record.status || "")))
        .forEach(record => {
          const key = `${record.date || ""}|${record.sessionId || record.sessionKey || ""}`;
          if (seen.has(key)) return;
          seen.add(key);
          appearances.push(record);
        });
    }

    return appearances.sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
  }

  function minutesSummary(player) {
    const records = recordsForPlayer(player).filter(record => number(record.minutes) > 0);
    const totalMinutes = records.reduce((sum, record) => sum + number(record.minutes), 0);
    return {
      totalMinutes: Math.round(totalMinutes),
      appearances: appearanceRecords(player).length,
    };
  }

  function statCard(value, label, onclick = "", tone = "") {
    const clickable = onclick ? " clickable" : "";
    const toneClass = tone ? ` ${tone}` : "";
    const action = onclick ? ` onclick="${onclick}"` : "";
    return `<div class="stat${toneClass}${clickable}"${action}><b>${value}</b><span>${label}</span></div>`;
  }

  function matchForStatRow(row) {
    return (store.matches || []).find(match =>
      match.date === row.date && match.opposition === row.opposition
    );
  }

  function matchContext(row) {
    const match = matchForStatRow(row);
    const competition = row.competition || match?.competition || "";
    const homeAway = row.homeAway || match?.homeAway || match?.venue || "";
    const parts = [competition, homeAway].filter(Boolean);
    return parts.length ? ` — ${parts.join(" · ")}` : "";
  }

  const style = document.createElement("style");
  style.textContent = `
    #playerProfile .summary.player-summary-grid {
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:14px;
    }
    #playerProfile .summary.player-summary-grid .stat {
      min-width:0;
      min-height:114px;
      height:114px;
      display:flex;
      flex-direction:column;
      justify-content:center;
      align-items:flex-start;
    }
    @media (max-width:760px) {
      #playerProfile .summary.player-summary-grid {
        grid-template-columns:repeat(2,minmax(0,1fr));
      }
    }
    @media (max-width:430px) {
      #playerProfile .summary.player-summary-grid {
        grid-template-columns:1fr;
      }
    }
  `;
  document.head.appendChild(style);

  const coreRenderPlayerProfile = renderPlayerProfile;
  renderPlayerProfile = function (player) {
    coreRenderPlayerProfile(player);
    const summary = document.querySelector("#playerProfile .summary");
    if (!summary) return;

    const stats = minutesSummary(player);
    const goals = getPlayerGoals(player);
    const assists = getPlayerAssists(player);
    const cards = getCardCounts(player);
    const trainingAttendance = countAttendanceForPlayer(store.trainingAttendance, player);
    const injuryWeeks = getInjuryDates(player).length;

    summary.classList.add("player-summary-grid");
    summary.innerHTML = [
      statCard(goals, "Goals", `showPlayerDetail('${player}', 'goals')`),
      statCard(assists, "Assists", `showPlayerDetail('${player}', 'assists')`),
      statCard(stats.appearances, "Recorded Appearances", `showPlayerDetail('${player}', 'minutes')`),
      statCard(stats.totalMinutes, "Recorded Minutes", `showPlayerDetail('${player}', 'minutes')`),
      statCard(cards.yellow, "Yellow Cards", `showPlayerDetail('${player}', 'yellowCards')`, "warning"),
      statCard(cards.red, "Red Cards", `showPlayerDetail('${player}', 'redCards')`, "danger"),
      statCard(trainingAttendance, "Training Attendances", `showPlayerDetail('${player}', 'trainingAttendance')`, "training"),
      statCard(injuryWeeks, "Weeks Injured", `showPlayerDetail('${player}', 'injuries')`),
    ].join("");
  };

  const coreShowPlayerDetail = showPlayerDetail;
  showPlayerDetail = function (player, type) {
    if (type === "goals" || type === "assists") {
      const box = document.getElementById("playerDetailBox");
      if (!box) return;

      const source = type === "goals" ? (store.goals || []) : (store.assists || []);
      const key = type;
      const label = type === "goals" ? "Goals" : "Assists";
      const rows = source
        .filter(row => number(row?.[key]?.[player]) > 0)
        .map(row => `<li><strong>${formatDateUK(row.date)}</strong> vs ${row.opposition || ""}${matchContext(row)}: <strong>${number(row[key][player])}</strong></li>`);

      box.innerHTML = `
        <div class="player-detail-box">
          <h2>${player} — ${label}</h2>
          ${rows.length ? `<ul>${rows.join("")}</ul>` : `<p>No ${label.toLowerCase()} recorded for ${player}.</p>`}
        </div>
      `;
      return;
    }

    if (type !== "minutes") {
      coreShowPlayerDetail(player, type);
      return;
    }

    const box = document.getElementById("playerDetailBox");
    if (!box) return;

    const minuteRows = recordsForPlayer(player)
      .filter(record => number(record.minutes) > 0);
    const minuteByDate = new Map(minuteRows.map(record => [String(record.date || ""), record]));
    const appearances = appearanceRecords(player);
    const stats = minutesSummary(player);

    const items = appearances.map(appearance => {
      const record = minuteByDate.get(String(appearance.date || ""));
      const match = (store.matches || []).find(item => String(item.date || "") === String(appearance.date || ""));
      const opposition = record?.opposition || match?.opposition || "";
      const competition = record?.competition || match?.competition || "";
      const context = competition ? ` · ${competition}` : "";

      if (record) {
        const role = record.starter ? "Started" : "Sub appearance";
        return `<li><strong>${formatDateUK(appearance.date)}</strong> vs ${opposition}${context} — <strong>${Math.round(number(record.minutes))} min</strong> · ${role}</li>`;
      }

      return `<li><strong>${formatDateUK(appearance.date)}</strong> vs ${opposition}${context} — Appearance recorded · minutes not recorded</li>`;
    });

    box.innerHTML = `
      <div class="player-detail-box">
        <h2>${player} — Recorded Appearances & Minutes</h2>
        <p><strong>${stats.appearances}</strong> recorded appearances · <strong>${stats.totalMinutes}</strong> recorded minutes.</p>
        ${items.length ? `<ul>${items.join("")}</ul>` : `<p>No appearances recorded for ${player} yet.</p>`}
      </div>
    `;
  };

  fetch(MINUTES_URL, { cache: "no-store" })
    .then(response => response.ok ? response.json() : [])
    .then(rows => {
      store.minutes = Array.isArray(rows) ? rows : [];
      mergeMatchdayAttendance(store.minutes);

      // Refresh whichever attendance/player view is currently visible now that
      // Matchday appearances have been merged into the attendance model.
      const attendancePage = document.getElementById("attendance");
      if (attendancePage?.classList.contains("active") && typeof renderAttendance === "function") {
        renderAttendance();
      }

      const playersPage = document.getElementById("players");
      if (playersPage?.classList.contains("active") && selectedPlayer) {
        renderPlayerProfile(selectedPlayer);
      }
    })
    .catch(() => {
      store.minutes = [];
    });
})();
