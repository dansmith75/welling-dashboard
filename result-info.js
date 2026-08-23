// Results-page match information panel: full Matchday timeline where recorded.
(() => {
  store.timeline = store.timeline || [];

  // Visit counter is no longer part of the Dashboard UI.
  setupVisitCounter = function () {
    document.getElementById("visitCounter")?.remove();
  };

  function minuteText(value) {
    if (value === null || value === undefined || value === "") return "";
    const number = Number(value);
    if (Number.isFinite(number)) return `${Math.round(number)}' `;
    return `${value}' `;
  }

  function timelineForMatch(match) {
    return (store.timeline || []).find(row =>
      (row.matchId && match.id && row.matchId === match.id) ||
      (row.date === match.date && row.opposition === match.opposition)
    );
  }

  function parsedDetail(detail) {
    if (!detail) return null;
    if (typeof detail === "object") return detail;
    const text = String(detail).trim();
    if (!text.startsWith("{") || !text.endsWith("}")) return null;
    try {
      return JSON.parse(text);
    } catch (_) {
      return null;
    }
  }

  function cleanGoalDetail(detail, fallback = "") {
    const parsed = parsedDetail(detail);
    if (parsed) {
      return String(parsed.goalType || parsed.detail || fallback || "").trim();
    }
    const text = String(detail || fallback || "").trim();
    const lower = text.toLowerCase();
    if (["goal", "legacy player goal(s)", "guest player goal(s)"].includes(lower)) return "";
    return text;
  }

  function displayPlayer(event, related = false) {
    const display = related ? event.relatedPlayer : event.player;
    const id = related ? event.relatedPlayerId : event.playerId;
    if (display) return display === "Keiran" ? "Kieran" : display;
    if (!id) return "";
    const canonicalId = id === "keiran-d" ? "kieran-d" : id;
    const squadPlayer = (store.players || []).find(player => player && player.id === canonicalId);
    return squadPlayer?.displayName || (canonicalId === "kieran-d" ? "Kieran" : canonicalId);
  }

  function eventCount(event) {
    const count = Number(event.value);
    return Number.isFinite(count) && count > 0 ? Math.round(count) : 1;
  }

  function formatTimelineEvent(event, scoreText = "", scoreState = "") {
    const type = String(event.type || "Event").trim();
    const typeLower = type.toLowerCase();
    const minute = minuteText(event.minute);
    const player = displayPlayer(event);
    const related = displayPlayer(event, true);
    const detail = String(event.detail || "").trim();
    const count = eventCount(event);
    const score = scoreText ? ` <span class="timeline-score ${scoreState}">${scoreText}</span>` : "";

    if (typeLower === "substitution") {
      return `${minute}<strong>🔄</strong> ${player || "Player"} off for ${related || "Player"}`;
    }

    if (typeLower === "goal") {
      const goalType = cleanGoalDetail(detail);
      const goalDetail = goalType ? ` · ${goalType}` : "";
      const assist = related ? ` <span class="timeline-muted">(assist: ${related})</span>` : "";
      const label = count > 1 ? "Goals" : "Goal";
      const multiplier = count > 1 ? ` ×${count}` : "";
      return `${minute}<strong>⚽ ${label} — ${player || "Welling"}${multiplier}</strong>${assist}${goalDetail}${score}`;
    }

    if (typeLower === "own goal") {
      const goalType = cleanGoalDetail(detail, "Own Goal");
      const extra = goalType && goalType.toLowerCase() !== "own goal" ? ` · ${goalType}` : "";
      const multiplier = count > 1 ? ` ×${count}` : "";
      return `${minute}<strong>⚽ Own Goal — Welling${multiplier}</strong>${extra}${score}`;
    }

    if (typeLower === "opponent goal") {
      const goalType = cleanGoalDetail(detail);
      const multiplier = count > 1 ? ` ×${count}` : "";
      return `${minute}<strong><span class="opponent-goal-icon">⚽</span> Opponent Goal${multiplier}</strong>${goalType ? ` · ${goalType}` : ""}${score}`;
    }

    if (typeLower === "card") {
      const card = detail || "Card";
      const icon = card.toLowerCase().includes("red") ? "🟥" : card.toLowerCase().includes("yellow") ? "🟨" : "🟨";
      return `${minute}<strong>${icon} ${card}</strong>${player ? ` — ${player}` : ""}`;
    }

    if (typeLower === "note") {
      return `${minute}<strong>📝 Note</strong>${player ? ` — ${player}` : ""}${detail ? `: ${detail}` : ""}`;
    }

    return `${minute}<strong>${type}</strong>${player ? ` — ${player}` : ""}${detail ? ` · ${detail}` : ""}`;
  }

  function detailedTimelineLines(events) {
    let goalsFor = 0;
    let goalsAgainst = 0;

    return (events || []).map(event => {
      const type = String(event.type || "").trim().toLowerCase();
      const count = eventCount(event);
      let scoreText = "";
      let scoreState = "";

      if (type === "goal" || type === "own goal") {
        goalsFor += count;
        scoreText = `${goalsFor}–${goalsAgainst}`;
      } else if (type === "opponent goal") {
        goalsAgainst += count;
        scoreText = `${goalsFor}–${goalsAgainst}`;
      }

      if (scoreText) {
        scoreState = goalsFor > goalsAgainst ? "winning" : goalsFor < goalsAgainst ? "losing" : "drawing";
      }

      return `<li>${formatTimelineEvent(event, scoreText, scoreState)}</li>`;
    });
  }

  // Matchday timeline is the authoritative completed-match record. If a later Excel
  // export has blank fixture/goals/assists cells, rebuild those stats from the
  // detailed Matchday events instead of allowing a completed match to disappear.
  function reconcileMatchdayTimelineData() {
    (store.timeline || []).forEach(timeline => {
      const events = timeline?.events || [];
      if (!events.some(event => String(event.source || "").toLowerCase() === "matchday app")) return;

      let goalsFor = 0;
      let goalsAgainst = 0;
      const goals = {};
      const assists = {};

      events.forEach(event => {
        const type = String(event.type || "").trim().toLowerCase();
        const count = eventCount(event);
        if (type === "goal") {
          goalsFor += count;
          const scorer = displayPlayer(event);
          if (scorer) goals[scorer] = (goals[scorer] || 0) + count;
          const assist = displayPlayer(event, true);
          if (assist) assists[assist] = (assists[assist] || 0) + count;
        } else if (type === "own goal") {
          goalsFor += count;
        } else if (type === "opponent goal") {
          goalsAgainst += count;
        }
      });

      const match = (store.matches || []).find(item =>
        (timeline.matchId && item.id === timeline.matchId) ||
        (item.date === timeline.date && item.opposition === timeline.opposition)
      );
      if (match) {
        match.goalsFor = goalsFor;
        match.goalsAgainst = goalsAgainst;
        match.result = goalsFor > goalsAgainst ? "Win" : goalsFor < goalsAgainst ? "Loss" : "Draw";
      }

      let goalRow = (store.goals || []).find(row =>
        (timeline.matchId && row.matchId === timeline.matchId) ||
        (row.date === timeline.date && row.opposition === timeline.opposition)
      );
      if (!goalRow) {
        goalRow = { matchId: timeline.matchId, date: timeline.date, opposition: timeline.opposition, goals: {} };
        store.goals = store.goals || [];
        store.goals.push(goalRow);
      }
      goalRow.goals = goals;

      let assistRow = (store.assists || []).find(row =>
        (timeline.matchId && row.matchId === timeline.matchId) ||
        (row.date === timeline.date && row.opposition === timeline.opposition)
      );
      if (!assistRow) {
        assistRow = { matchId: timeline.matchId, date: timeline.date, opposition: timeline.opposition, assists: {} };
        store.assists = store.assists || [];
        store.assists.push(assistRow);
      }
      assistRow.assists = assists;
    });
  }

  function legacyInfoForMatch(match) {
    const lines = [];
    const goalRow = (store.goals || []).find(row => row.date === match.date && row.opposition === match.opposition);
    const assistRow = (store.assists || []).find(row => row.date === match.date && row.opposition === match.opposition);
    const eventRow = (store.events || []).find(row => row.date === match.date && row.opposition === match.opposition);

    Object.entries(goalRow?.goals || {}).forEach(([player, count]) => {
      const n = safeNumber(count);
      if (n > 0) lines.push(`<li><strong>⚽ Goal${n > 1 ? "s" : ""}</strong> — ${player}${n > 1 ? ` ×${n}` : ""}</li>`);
    });

    Object.entries(assistRow?.assists || {}).forEach(([player, count]) => {
      const n = safeNumber(count);
      if (n > 0) lines.push(`<li><strong>Assist${n > 1 ? "s" : ""}</strong> — ${player}${n > 1 ? ` ×${n}` : ""}</li>`);
    });

    Object.entries(eventRow?.events || {}).forEach(([player, event]) => {
      if (isRealEvent(event)) lines.push(`<li><strong>📝 ${player}</strong> — ${event}</li>`);
    });

    return lines;
  }

  renderResults = function () {
    const label = activeResultsFilter?.label || "";
    const rows = activeResultsFilter ? store.matches.filter(activeResultsFilter.filterFn) : store.matches;

    setDrillLabel("resultsDrillLabel", label);
    document.getElementById("resultsTitle").textContent = label || "Match Results";

    document.getElementById("resultsTable").innerHTML = rows.map((match, index) => {
      const timeline = timelineForMatch(match);
      const detailedEvents = detailedTimelineLines(timeline?.events || []);
      const fallback = detailedEvents.length ? [] : legacyInfoForMatch(match);
      const information = detailedEvents.length ? detailedEvents : fallback;

      return `
        <tr>
          <td>${formatDateUK(match.date)}</td>
          <td>${match.opposition || ""}</td>
          <td>${match.homeAway || ""}</td>
          <td>${match.competition || ""}</td>
          <td>${safeNumber(match.goalsFor)}</td>
          <td>${safeNumber(match.goalsAgainst)}</td>
          <td><span class="result-badge ${resultClass(match.result)}">${match.result || ""}</span></td>
          <td><button class="scorers-btn" onclick="toggleScorers(${index})">Info</button></td>
        </tr>
        <tr class="scorers-row" id="scorers-row-${index}">
          <td colspan="8">
            <div class="scorers-box match-info-box">
              <div class="match-info-heading">
                <strong>${formatDateUK(match.date)} · ${match.homeAway || ""} vs ${match.opposition || ""}</strong>
                <span>${match.competition || ""} · ${safeNumber(match.goalsFor)}–${safeNumber(match.goalsAgainst)} ${match.result || ""}</span>
              </div>
              <h3>Game Timeline</h3>
              ${information.length
                ? `<ol class="match-timeline">${information.join("")}</ol>`
                : `<p class="timeline-muted">No detailed match events were recorded for this fixture.</p>`}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  };

  const style = document.createElement("style");
  style.textContent = `
    #visitCounter,
    #overview .card.executive {
      display:none !important;
    }
    .match-info-heading {
      display:flex;
      flex-wrap:wrap;
      justify-content:space-between;
      gap:8px 18px;
      margin-bottom:16px;
    }
    .match-info-heading span,
    .timeline-muted {
      color:var(--muted);
    }
    .opponent-goal-icon {
      filter:hue-rotate(145deg) saturate(4.5) brightness(.9);
    }
    .timeline-score {
      margin-left:8px;
      font-weight:900;
      padding:2px 7px;
      border-radius:999px;
    }
    .timeline-score.losing {
      color:#fecaca;
      background:rgba(220,38,38,.18);
    }
    .timeline-score.drawing {
      color:#fdba74;
      background:rgba(249,115,22,.16);
    }
    .timeline-score.winning {
      color:#86efac;
      background:rgba(34,197,94,.16);
    }
    .match-info-box h3 {
      margin:0 0 10px;
    }
    .match-timeline {
      margin:0;
      padding-left:24px;
    }
    .match-timeline li {
      padding:7px 0;
      line-height:1.45;
      border-bottom:1px solid var(--line);
    }
    .match-timeline li:last-child {
      border-bottom:0;
    }
  `;
  document.head.appendChild(style);

  fetch("data/timeline.json", { cache: "no-store" })
    .then(response => response.ok ? response.json() : [])
    .then(rows => {
      store.timeline = Array.isArray(rows) ? rows : [];
      reconcileMatchdayTimelineData();

      // Refresh any already-rendered views now that authoritative Matchday stats
      // have been rebuilt from the timeline.
      if (typeof renderOverview === "function") renderOverview();
      if (typeof renderGoals === "function" && document.getElementById("goals")?.classList.contains("active")) renderGoals();
      if (document.getElementById("results")?.classList.contains("active")) renderResults();
    })
    .catch(() => {
      store.timeline = [];
    });
})();
