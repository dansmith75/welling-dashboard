const DATA = "data/";
const GITHUB_GALLERY_API = "https://api.github.com/repos/dansmith75/welling-utd-red-obdsfl/contents/gallery";

let store = {};
let charts = {};
let galleryImages = [];
let currentGalleryIndex = 0;
let selectedPlayer = null;

let activeResultsFilter = null;
let activeGoalsDrillLabel = "";
let activeAttendanceDrillLabel = "";

const valueLabelsPlugin = {
  id: "valueLabelsPlugin",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    const colour = chartTextColour();

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex);

      meta.data.forEach((bar, index) => {
        const value = dataset.data[index];
        if (!value || value === 0) return;

        ctx.save();
        ctx.fillStyle = colour;
        ctx.font = "bold 12px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(value, bar.x, bar.y - 6);
        ctx.restore();
      });
    });
  }
};

Chart.register(valueLabelsPlugin);

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function playerName(player) {
  if (typeof player === "string") return player;
  return player?.displayName || player?.name || player?.firstName || player?.id || "";
}

function dashboardPlayers() {
  return (store.players || [])
    .map(playerName)
    .filter(Boolean);
}

function formatDateUK(dateValue) {
  if (!dateValue) return "";

  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return dateValue;
  }

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();

  return `${day}-${month}-${year}`;
}

function selected(name) {
  return document.querySelector(`input[name="${name}"]:checked`).value;
}

async function getJson(file) {
  const response = await fetch(`${DATA}${file}.json`);
  if (!response.ok) throw new Error(`${file}.json not found`);
  return response.json();
}

async function loadGalleryImages() {
  const response = await fetch(GITHUB_GALLERY_API);

  if (!response.ok) {
    galleryImages = [];
    return;
  }

  const files = await response.json();

  galleryImages = files
    .filter(file => file.type === "file" && /\.(jpg|jpeg|png|gif|webp)$/i.test(file.name))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    .map(file => file.download_url);
}


async function loadData() {
  store.matches = await getJson("matches");
  store.goals = await getJson("goals");
  store.assists = await getJson("assists");
  store.events = await getJson("events");
  store.players = await getJson("players");

  // New combined attendance export from Excel AttendanceRecords table.
  // This replaces the older match-attendance.json and training-attendance.json files.
  store.attendance = await getJson("attendance");
  store.matchAttendance = legacyAttendanceRows("Match");
  store.trainingAttendance = legacyAttendanceRows("Training");

  await loadGalleryImages();
}


function isCompetitive(match) {
  const competition = String(match?.competition || "").trim().toLowerCase();
  return competition === "league" || competition.includes("cup") || competition.includes("shield");
}

function chartTextColour() {
  return document.body.classList.contains("light") ? "#0f172a" : "#e5e7eb";
}

function chartGridColour() {
  return document.body.classList.contains("light")
    ? "rgba(15,23,42,.08)"
    : "rgba(255,255,255,.08)";
}

function destroyChart(name) {
  if (charts[name]) charts[name].destroy();
}

function chartXTickOptions(autoSkip = false) {
  return {
    color: chartTextColour(),
    autoSkip,
    maxRotation: 45,
    minRotation: 45,
    padding: 12
  };
}

function drawBar(name, canvasId, labels, data, colour) {
  destroyChart(name);

  const maxValue = Math.max(...data, 0);

  charts[name] = new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colour,
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 900,
        easing: "easeOutQuart"
      },
      layout: {
        padding: {
          top: 28,
          bottom: 60
        }
      },
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          ticks: chartXTickOptions(false),
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          suggestedMax: maxValue + 2,
          ticks: {
            color: chartTextColour(),
            precision: 0
          },
          grid: {
            color: chartGridColour()
          }
        }
      }
    }
  });
}

function drawLine(name, canvasId, labels, data) {
  destroyChart(name);

  charts[name] = new Chart(document.getElementById(canvasId), {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Goals",
        data,
        borderColor: "#38bdf8",
        backgroundColor: "rgba(56,189,248,.16)",
        fill: true,
        tension: .35,
        pointRadius: 4,
        pointHoverRadius: 7
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 900,
        easing: "easeOutQuart"
      },
      layout: {
        padding: {
          top: 28,
          bottom: 70
        }
      },
      plugins: {
        valueLabelsPlugin: false
      },
      scales: {
        x: {
          ticks: chartXTickOptions(false),
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: chartTextColour(),
            precision: 0
          },
          grid: {
            color: chartGridColour()
          }
        }
      }
    }
  });
}

function goalTotals(rows) {
  return dashboardPlayers().map(player =>
    rows.reduce((sum, row) => sum + safeNumber(row.goals?.[player]), 0)
  );
}

function assistTotals(rows) {
  return dashboardPlayers().map(player =>
    rows.reduce((sum, row) => sum + safeNumber(row.assists?.[player]), 0)
  );
}

function attendanceTotals(rows) {
  return dashboardPlayers().map(player =>
    rows.reduce((sum, row) => {
      const value = String(row.attendance?.[player] || "").toUpperCase();
      return sum + (value === "Y" ? 1 : 0);
    }, 0)
  );
}


function normaliseText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function isAttendancePresent(status) {
  const value = normaliseText(status);
  return value === "present" || value === "late";
}

function isAttendanceInjured(status) {
  return normaliseText(status) === "injured";
}

function attendanceSessions(type = null) {
  const sessions = store.attendance?.sessions || [];

  if (!type) return sessions;

  return sessions.filter(session =>
    normaliseText(session.type) === normaliseText(type)
  );
}

function attendancePlayerMatches(record, player) {
  const playerText = normaliseText(player);
  return (
    normaliseText(record.displayName) === playerText ||
    normaliseText(record.playerName) === playerText ||
    normaliseText(record.playerId) === playerText
  );
}

function legacyStatusCode(status) {
  if (isAttendancePresent(status)) return "Y";
  if (isAttendanceInjured(status)) return "I";
  return "";
}

function legacyAttendanceRows(type) {
  return attendanceSessions(type).map(session => {
    const attendance = {};
    let count = 0;

    (session.records || []).forEach(record => {
      const playerName = record.displayName || record.playerName || record.playerId;
      const code = legacyStatusCode(record.status);

      if (playerName) attendance[playerName] = code;
      if (isAttendancePresent(record.status)) count += 1;
    });

    return {
      date: session.date,
      sessionKey: session.sessionKey,
      sessionId: session.sessionId,
      type: session.type,
      venue: session.venue,
      submittedBy: session.submittedBy,
      submittedAt: session.submittedAt,
      count,
      attendance
    };
  });
}

function attendanceRecordsForPlayer(player, type = null) {
  const records = [];

  attendanceSessions(type).forEach(session => {
    (session.records || []).forEach(record => {
      if (!attendancePlayerMatches(record, player)) return;

      records.push({
        ...record,
        date: session.date,
        sessionKey: session.sessionKey,
        sessionId: session.sessionId,
        type: session.type,
        venue: session.venue,
        submittedBy: session.submittedBy,
        submittedAt: session.submittedAt
      });
    });
  });

  return records.sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function matchStats(matches) {
  return {
    games: matches.length,
    wins: matches.filter(m => m.result === "Win").length,
    draws: matches.filter(m => m.result === "Draw").length,
    losses: matches.filter(m => m.result === "Loss").length,
    goalsFor: matches.reduce((s, m) => s + safeNumber(m.goalsFor), 0),
    goalsAgainst: matches.reduce((s, m) => s + safeNumber(m.goalsAgainst), 0)
  };
}

function resultClass(result) {
  if (result === "Win") return "badge-win";
  if (result === "Draw") return "badge-draw";
  if (result === "Loss") return "badge-loss";
  return "";
}

function showPage(pageId, updateHistory = true) {
  const currentPage = document.querySelector(".page.active")?.id || "overview";

  document.querySelectorAll(".tab-btn").forEach(button => {
    button.classList.toggle("active", button.dataset.page === pageId);
  });

  document.querySelectorAll(".page").forEach(page => {
    page.classList.toggle("active", page.id === pageId);
  });

  if (updateHistory && currentPage !== pageId) {
    const url = new URL(window.location.href);
    url.hash = pageId === "overview" ? "" : pageId;
    window.history.pushState({ dashboardPage: pageId }, "", url);
  }

  setTimeout(renderCurrentPage, 80);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setupDashboardHistory() {
  const hashPage = window.location.hash.replace(/^#/, "");
  const validPages = new Set(Array.from(document.querySelectorAll(".page")).map(page => page.id));
  const initialPage = validPages.has(hashPage) ? hashPage : "overview";

  window.history.replaceState({ dashboardPage: initialPage }, "", window.location.href);
  if (initialPage !== "overview") showPage(initialPage, false);

  window.addEventListener("popstate", event => {
    const pageId = event.state?.dashboardPage || "overview";
    showPage(validPages.has(pageId) ? pageId : "overview", false);
  });
}

function setDrillLabel(elementId, text) {
  const label = document.getElementById(elementId);
  if (!label) return;

  if (text) {
    label.textContent = `Showing: ${text}`;
    label.classList.add("active");
  } else {
    label.textContent = "";
    label.classList.remove("active");
  }
}

function drillToResults(label, filterFn) {
  activeResultsFilter = { label, filterFn };
  activeGoalsDrillLabel = "";
  activeAttendanceDrillLabel = "";
  showPage("results");
}

function drillToGoals(label, competition = "All", homeAway = "Both") {
  activeResultsFilter = null;
  activeGoalsDrillLabel = label;
  activeAttendanceDrillLabel = "";

  const compInput = document.querySelector(`input[name="goalComp"][value="${competition}"]`);
  const haInput = document.querySelector(`input[name="goalHA"][value="${homeAway}"]`);

  if (compInput) compInput.checked = true;
  if (haInput) haInput.checked = true;

  showPage("goals");
}

function drillToAttendance(label) {
  activeResultsFilter = null;
  activeGoalsDrillLabel = "";
  activeAttendanceDrillLabel = label;
  showPage("attendance");
}

function renderFormGuide() {
  const lastFive = store.matches
    .filter(isCompetitive)
    .filter(m => ["Win", "Draw", "Loss"].includes(m.result))
    .slice(-5);

  document.getElementById("formGuide").innerHTML = lastFive.map((match, index) => {
    const letter = match.result === "Win" ? "W" : match.result === "Draw" ? "D" : "L";
    const cls = match.result === "Win" ? "form-win" : match.result === "Draw" ? "form-draw" : "form-loss";

    return `
      <div 
        class="form-pill ${cls}" 
        title="${formatDateUK(match.date)} v ${match.opposition}"
        onclick="drillToResults('${formatDateUK(match.date)} vs ${match.opposition}', m => m.date === '${match.date}' && m.opposition === '${match.opposition}')"
      >
        ${letter}
      </div>
    `;
  }).join("");
}

function renderOverview() {
  renderFormGuide();

  const competitiveMatches = store.matches.filter(isCompetitive);
  const friendlyMatches = store.matches.filter(m => m.competition === "Friendly");

  const competitive = matchStats(competitiveMatches);
  const friendly = matchStats(friendlyMatches);

  const trainingSessions = store.trainingAttendance.length;
  const trainingAttendances = store.trainingAttendance.reduce((s, a) => s + safeNumber(a.count), 0);
  const averageTrainingFigure = trainingSessions > 0 ? trainingAttendances / trainingSessions : 0;

  const squadSize = dashboardPlayers().length;
  const averageTrainingPercentage = trainingSessions > 0 && squadSize > 0
    ? (trainingAttendances / (trainingSessions * squadSize)) * 100
    : 0;

  document.getElementById("competitiveSummary").innerHTML = `
    <div class="stat drill" data-drill="competitive-all"><b>${competitive.games}</b><span>Competitive Games</span></div>
    <div class="stat drill" data-drill="competitive-win"><b>${competitive.wins}</b><span>Wins</span></div>
    <div class="stat drill" data-drill="competitive-draw"><b>${competitive.draws}</b><span>Draws</span></div>
    <div class="stat drill" data-drill="competitive-loss"><b>${competitive.losses}</b><span>Losses</span></div>
    <div class="stat drill" data-drill="competitive-goals-for"><b>${competitive.goalsFor}</b><span>Goals For</span></div>
    <div class="stat drill" data-drill="competitive-goals-against"><b>${competitive.goalsAgainst}</b><span>Goals Against</span></div>
  `;

  document.getElementById("friendlySummary").innerHTML = `
    <div class="stat friendly drill" data-drill="friendly-all"><b>${friendly.games}</b><span>Friendly Games</span></div>
    <div class="stat friendly drill" data-drill="friendly-win"><b>${friendly.wins}</b><span>Wins</span></div>
    <div class="stat friendly drill" data-drill="friendly-draw"><b>${friendly.draws}</b><span>Draws</span></div>
    <div class="stat friendly drill" data-drill="friendly-loss"><b>${friendly.losses}</b><span>Losses</span></div>
    <div class="stat friendly drill" data-drill="friendly-goals-for"><b>${friendly.goalsFor}</b><span>Goals For</span></div>
    <div class="stat friendly drill" data-drill="friendly-goals-against"><b>${friendly.goalsAgainst}</b><span>Goals Against</span></div>
  `;

  document.getElementById("trainingSummary").innerHTML = `
    <div class="stat training drill" data-drill="training-sessions"><b>${trainingSessions}</b><span>Training Sessions</span></div>
    <div class="stat training drill" data-drill="training-attendances"><b>${trainingAttendances}</b><span>Total Attendances</span></div>
    <div class="stat training drill" data-drill="training-average"><b>${averageTrainingFigure.toFixed(1)}</b><span>Average Attendance</span></div>
    <div class="stat training drill" data-drill="training-percent"><b>${averageTrainingPercentage.toFixed(1)}%</b><span>Average Attendance %</span></div>
  `;

  document.getElementById("executiveSummary").innerText =
    `Danson U21 have recorded ${competitive.games} competitive fixtures, with ${competitive.wins} wins, ${competitive.draws} draws and ${competitive.losses} losses. In competitive games, the team has scored ${competitive.goalsFor} and conceded ${competitive.goalsAgainst}. Friendlies are tracked separately, with ${friendly.games} friendly fixtures. Training is separated from matches, with ${trainingSessions} sessions, ${trainingAttendances} total attendances, an average of ${averageTrainingFigure.toFixed(1)} players per session and an average attendance rate of ${averageTrainingPercentage.toFixed(1)}%.`;

  attachOverviewDrillHandlers();
}

function attachOverviewDrillHandlers() {
  document.querySelectorAll("[data-drill]").forEach(card => {
    card.addEventListener("click", () => {
      const drill = card.dataset.drill;

      if (drill === "competitive-all") {
        drillToResults("Competitive Games", m => isCompetitive(m));
      }

      if (drill === "competitive-win") {
        drillToResults("Competitive Wins", m => isCompetitive(m) && m.result === "Win");
      }

      if (drill === "competitive-draw") {
        drillToResults("Competitive Draws", m => isCompetitive(m) && m.result === "Draw");
      }

      if (drill === "competitive-loss") {
        drillToResults("Competitive Losses", m => isCompetitive(m) && m.result === "Loss");
      }

      
if (drill === "competitive-goals-for") {
  drillToResults(
    "Competitive Games — Danson Scored",
    m => isCompetitive(m) && safeNumber(m.goalsFor) > 0
  );
}


      if (drill === "competitive-goals-against") {
        drillToResults(
          "Competitive Games — Opposition Scored",
          m => isCompetitive(m) && safeNumber(m.goalsAgainst) > 0
        );
      }

      if (drill === "friendly-all") {
        drillToResults("Friendly Games", m => m.competition === "Friendly");
      }

      if (drill === "friendly-win") {
        drillToResults("Friendly Wins", m => m.competition === "Friendly" && m.result === "Win");
      }

      if (drill === "friendly-draw") {
        drillToResults("Friendly Draws", m => m.competition === "Friendly" && m.result === "Draw");
      }

      if (drill === "friendly-loss") {
        drillToResults("Friendly Losses", m => m.competition === "Friendly" && m.result === "Loss");
      }

      
if (drill === "friendly-goals-for") {
  drillToResults(
    "Friendly Games — Danson Scored",
    m => m.competition === "Friendly" && safeNumber(m.goalsFor) > 0
  );
}


      if (drill === "friendly-goals-against") {
        drillToResults(
          "Friendly Games — Opposition Scored",
          m => m.competition === "Friendly" && safeNumber(m.goalsAgainst) > 0
        );
      }

      if (
        drill === "training-sessions" ||
        drill === "training-attendances" ||
        drill === "training-average" ||
        drill === "training-percent"
      ) {
        drillToAttendance("Training Attendance");
      }
    });
  });
}

function getScorersForMatch(match) {
  const goalRow = store.goals.find(g =>
    g.date === match.date &&
    g.opposition === match.opposition
  );

  if (!goalRow || !goalRow.goals) return [];

  return Object.entries(goalRow.goals)
    .filter(([player, goals]) => safeNumber(goals) > 0)
    .map(([player, goals]) => ({
      player,
      goals: safeNumber(goals)
    }));
}

function getAssistsForMatch(match) {
  const assistRow = store.assists.find(a =>
    a.date === match.date &&
    a.opposition === match.opposition
  );

  if (!assistRow || !assistRow.assists) return [];

  return Object.entries(assistRow.assists)
    .filter(([player, assists]) => safeNumber(assists) > 0)
    .map(([player, assists]) => ({
      player,
      assists: safeNumber(assists)
    }));
}

function toggleScorers(index) {
  const row = document.getElementById(`scorers-row-${index}`);
  if (row) row.classList.toggle("active");
}

function renderResults() {
  const label = activeResultsFilter?.label || "";
  const rows = activeResultsFilter
    ? store.matches.filter(activeResultsFilter.filterFn)
    : store.matches;

  setDrillLabel("resultsDrillLabel", label);

  document.getElementById("resultsTitle").textContent = label || "Match Results";

  document.getElementById("resultsTable").innerHTML = rows.map((match, index) => {
    const scorers = getScorersForMatch(match);
const assists = getAssistsForMatch(match);

const scorersText = scorers.length
  ? scorers.map(s => `${s.player} (${s.goals})`).join(", ")
  : "No scorers recorded";

const assistsText = assists.length
  ? assists.map(a => `${a.player} (${a.assists})`).join(", ")
  : "No assists recorded";

    return `
      <tr>
        <td>${formatDateUK(match.date)}</td>
        <td>${match.opposition || ""}</td>
        <td>${match.homeAway || ""}</td>
        <td>${match.competition || ""}</td>
        <td>${safeNumber(match.goalsFor)}</td>
        <td>${safeNumber(match.goalsAgainst)}</td>
        <td><span class="result-badge ${resultClass(match.result)}">${match.result || ""}</span></td>
        <td>
          <button class="scorers-btn" onclick="toggleScorers(${index})">Scorers</button>
        </td>
      </tr>

      <tr class="scorers-row" id="scorers-row-${index}">
        <td colspan="8">
          <div class="scorers-box">
           <strong>Scorers vs ${match.opposition}:</strong><br>
${scorersText}
<br><br>
<strong>Assists:</strong><br>
${assistsText}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function goalFilters(row) {
  const comp = selected("goalComp");
  const ha = selected("goalHA");
  const competition = String(row.competition || "").trim().toLowerCase();
  const matchesCompetition = comp === "All" ||
    (comp === "Cup" ? competition.includes("cup") || competition.includes("shield") : competition === comp.toLowerCase());

  return matchesCompetition &&
         (ha === "Both" || row.homeAway === ha);
}

function renderGoals() {
  setDrillLabel("goalsDrillLabel", activeGoalsDrillLabel);

  const filteredGoals = store.goals.filter(goalFilters);
  const filteredAssists = store.assists.filter(goalFilters);

  drawBar(
    "goalsByPlayer",
    "goalsByPlayerChart",
    dashboardPlayers(),
    goalTotals(filteredGoals),
    "rgba(37,99,235,.78)"
  );

  drawBar(
    "assistsByPlayer",
    "assistsByPlayerChart",
    dashboardPlayers(),
    assistTotals(filteredAssists),
    "rgba(56,189,248,.82)"
  );
}

function renderAttendance() {
  setDrillLabel("attendanceDrillLabel", activeAttendanceDrillLabel);

  drawBar(
    "matchAttendance",
    "matchAttendanceChart",
    dashboardPlayers(),
    attendanceTotals(store.matchAttendance),
    "rgba(37,99,235,.78)"
  );

  drawBar(
    "trainingAttendance",
    "trainingAttendanceChart",
    dashboardPlayers(),
    attendanceTotals(store.trainingAttendance),
    "rgba(16,185,129,.82)"
  );
}

function isRealEvent(value) {
  const text = String(value ?? "").trim();
  return text !== "" && text !== "0" && text !== "-" && text.toLowerCase() !== "null";
}

function isYellowCardEvent(value) {
  return /\byellow(?:\s+card)?\b/i.test(String(value ?? ""));
}

function isRedCardEvent(value) {
  return /\bred(?:\s+card)?\b/i.test(String(value ?? ""));
}

function eventTone(eventText) {
  const text = eventText.toLowerCase();

  if (text.includes("double hat trick")) return "🎩🎩 Double hat-trick alert";
  if (text.includes("hat trick")) return "🎩 Hat-trick watch";
  if (text.includes("pen")) return "⚽ Penalty";
  if (isYellowCardEvent(text)) return "🟨 Into the book";
  if (isRedCardEvent(text)) return "🟥 Early shower";
  if (text.includes("injur") || text.includes("split") || text.includes("shoulder")) return "🩹 Treatment room note";
  if (text.includes("fell")) return "🫣 One for the blooper reel";
  if (text.includes("last game") || text.includes("joined")) return "📌 Squad note";
  return "📋 Notable moment";
}

function buildEventsTimeline() {
  const timeline = [];

  store.events.forEach(row => {
    Object.entries(row.events || {}).forEach(([player, eventText]) => {
      if (!isRealEvent(eventText)) return;

      timeline.push({
        date: row.date,
        opposition: row.opposition,
        player,
        event: String(eventText).trim(),
        tag: eventTone(String(eventText))
      });
    });
  });

  return timeline.sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function renderEvents() {
  const timeline = buildEventsTimeline();
  const container = document.getElementById("eventsTimeline");

  container.innerHTML = timeline.map(item => `
    <article class="event-card">
      <div class="event-date">${formatDateUK(item.date)}</div>
      <div class="event-main">
        <h3>${item.player}</h3>
        <p><strong>Fixture:</strong> ${item.opposition}</p>
        <p><strong>Event:</strong> ${item.event}</p>
        <span class="event-badge">${item.tag}</span>
      </div>
    </article>
  `).join("");
}

function getPlayerGoals(player) {
  return store.goals.reduce((sum, row) => sum + safeNumber(row.goals?.[player]), 0);
}

function getPlayerAssists(player) {
  return store.assists.reduce((sum, row) => sum + safeNumber(row.assists?.[player]), 0);
}

function countAttendanceForPlayer(rows, player) {
  return rows.reduce((sum, row) => {
    const value = String(row.attendance?.[player] || "").toUpperCase();
    return sum + (value === "Y" ? 1 : 0);
  }, 0);
}

function getPlayerEvents(player) {
  const events = [];

  store.events.forEach(row => {
    const eventText = row.events?.[player];

    if (!isRealEvent(eventText)) return;

    events.push({
      date: row.date,
      opposition: row.opposition,
      event: String(eventText).trim(),
      tag: eventTone(String(eventText))
    });
  });

  return events.sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function getCardCounts(player) {
  const events = getPlayerEvents(player);

  return {
    yellow: events.filter(e => isYellowCardEvent(e.event)).length,
    red: events.filter(e => isRedCardEvent(e.event)).length
  };
}

function getInjuryDates(player) {
  const dates = new Set();

  attendanceRecordsForPlayer(player).forEach(record => {
    if (isAttendanceInjured(record.status)) dates.add(record.date);
  });

  return Array.from(dates).sort();
}

function renderPlayerButtons() {
  const grid = document.getElementById("playerGrid");
  const players = dashboardPlayers();

  grid.innerHTML = players.map(player => `
    <button class="player-button" data-player="${player}">${player}</button>
  `).join("");

  document.querySelectorAll(".player-button").forEach(button => {
    button.addEventListener("click", () => {
      selectedPlayer = button.dataset.player;
      renderPlayerProfile(selectedPlayer);
    });
  });
}

function renderPlayerProfile(player) {
  document.querySelectorAll(".player-button").forEach(button => {
    button.classList.toggle("active", button.dataset.player === player);
  });

  const goals = getPlayerGoals(player);
  const assists = getPlayerAssists(player);
  const matchAttendance = countAttendanceForPlayer(store.matchAttendance, player);
  const trainingAttendance = countAttendanceForPlayer(store.trainingAttendance, player);
  const cards = getCardCounts(player);
  const injuryDates = getInjuryDates(player);
  const playerEvents = getPlayerEvents(player);

  document.getElementById("playerProfile").innerHTML = `
    <div class="card">
      <div class="profile-header">
        <h2>${player}</h2>
        <div class="profile-subtitle">Player profile summary</div>
      </div>
    </div>

    <div class="summary">
      <div class="stat clickable" onclick="showPlayerDetail('${player}', 'goals')"><b>${goals}</b><span>Goals</span></div>
      <div class="stat clickable" onclick="showPlayerDetail('${player}', 'assists')"><b>${assists}</b><span>Assists</span></div>
      <div class="stat clickable" onclick="showPlayerDetail('${player}', 'matchAttendance')"><b>${matchAttendance}</b><span>Match Attendances</span></div>
      <div class="stat training clickable" onclick="showPlayerDetail('${player}', 'trainingAttendance')"><b>${trainingAttendance}</b><span>Training Attendances</span></div>
      <div class="stat warning clickable" onclick="showPlayerDetail('${player}', 'yellowCards')"><b>${cards.yellow}</b><span>Yellow Cards</span></div>
      <div class="stat danger clickable" onclick="showPlayerDetail('${player}', 'redCards')"><b>${cards.red}</b><span>Red Cards</span></div>
      <div class="stat clickable" onclick="showPlayerDetail('${player}', 'injuries')"><b>${injuryDates.length}</b><span>Weeks Injured</span></div>
    </div>

    <div id="playerDetailBox"></div>

    <div class="card">
      <h2>Events</h2>
      ${
        playerEvents.length
          ? `<ul class="player-event-list">
              ${playerEvents.map(e => `
                <li><strong>${formatDateUK(e.date)}</strong> — ${e.opposition}: ${e.event}
                <span class="event-badge">${e.tag}</span></li>
              `).join("")}
            </ul>`
          : `<p class="executive">No events recorded for ${player}.</p>`
      }
    </div>
  `;
}

function showPlayerDetail(player, type) {
  const box = document.getElementById("playerDetailBox");
  if (!box) return;

  let title = "";
  let content = "";

  if (type === "goals") {
    title = `${player} — Goals`;

    const games = store.goals
      .filter(row => safeNumber(row.goals?.[player]) > 0)
      .map(row => `<li>${formatDateUK(row.date)} vs ${row.opposition}: ${safeNumber(row.goals?.[player])}</li>`);

    content = games.length ? `<ul>${games.join("")}</ul>` : `<p>No goals recorded for ${player}.</p>`;
  }
  
if (type === "assists") {
  title = `${player} — Assists`;

  const assists = store.assists
    .filter(row => safeNumber(row.assists?.[player]) > 0)
    .map(row => `<li>${formatDateUK(row.date)} vs ${row.opposition}: ${safeNumber(row.assists?.[player])}</li>`);

  content = assists.length
    ? `<ul>${assists.join("")}</ul>`
    : `<p>No assists recorded for ${player}.</p>`;
}
  if (type === "matchAttendance") {
    title = `${player} — Match Attendance`;

    const games = attendanceRecordsForPlayer(player, "Match")
      .filter(record => isAttendancePresent(record.status))
      .map(record => `
        <li>
          ${formatDateUK(record.date)}
          ${record.venue ? ` — ${record.venue}` : ""}
          ${record.status ? ` — ${record.status}` : ""}
        </li>
      `);

    content = games.length ? `<ul>${games.join("")}</ul>` : `<p>No match attendances recorded for ${player}.</p>`;
  }

  if (type === "trainingAttendance") {
    title = `${player} — Training Attendance`;

    const sessions = attendanceRecordsForPlayer(player, "Training")
      .filter(record => isAttendancePresent(record.status))
      .map(record => `<li>${formatDateUK(record.date)}${record.status ? ` — ${record.status}` : ""}</li>`);

    content = sessions.length ? `<ul>${sessions.join("")}</ul>` : `<p>No training attendances recorded for ${player}.</p>`;
  }

  if (type === "yellowCards") {
    title = `${player} — Yellow Cards`;

    const yellows = getPlayerEvents(player)
      .filter(e => isYellowCardEvent(e.event))
      .map(e => `<li>${formatDateUK(e.date)} vs ${e.opposition}: ${e.event}</li>`);

    content = yellows.length ? `<ul>${yellows.join("")}</ul>` : `<p>No yellow cards recorded for ${player}.</p>`;
  }

  if (type === "redCards") {
    title = `${player} — Red Cards`;

    const reds = getPlayerEvents(player)
      .filter(e => isRedCardEvent(e.event))
      .map(e => `<li>${formatDateUK(e.date)} vs ${e.opposition}: ${e.event}</li>`);

    content = reds.length ? `<ul>${reds.join("")}</ul>` : `<p>No red cards recorded for ${player}.</p>`;
  }

  if (type === "injuries") {
    title = `${player} — Injury Weeks`;

    const injuries = getInjuryDates(player)
      .map(date => `<li>${formatDateUK(date)}</li>`);

    content = injuries.length ? `<ul>${injuries.join("")}</ul>` : `<p>No injured weeks recorded for ${player}.</p>`;
  }

  box.innerHTML = `
    <div class="player-detail-box">
      <h2>${title}</h2>
      ${content}
    </div>
  `;
}

function renderPlayers() {
  renderPlayerButtons();

  if (!selectedPlayer) selectedPlayer = dashboardPlayers()[0];

  renderPlayerProfile(selectedPlayer);
}

function showGalleryImage(index) {
  const mainImage = document.getElementById("galleryMainImage");

  if (!galleryImages.length) {
    mainImage.removeAttribute("src");
    document.getElementById("thumbnailStrip").innerHTML = "";
    return;
  }

  currentGalleryIndex = (index + galleryImages.length) % galleryImages.length;
  mainImage.src = galleryImages[currentGalleryIndex];

  document.querySelectorAll(".thumbnail").forEach((thumb, i) => {
    thumb.classList.toggle("active", i === currentGalleryIndex);
  });

  const activeThumb = document.querySelector(`.thumbnail[data-index="${currentGalleryIndex}"]`);

  if (activeThumb) {
    activeThumb.scrollIntoView({
      behavior: "smooth",
      inline: "center",
      block: "nearest"
    });
  }
}

function renderGallery() {
  const strip = document.getElementById("thumbnailStrip");

  if (!galleryImages.length) {
    strip.innerHTML = `<div class="card"><h2>No gallery images found</h2></div>`;
    showGalleryImage(0);
    return;
  }

  strip.innerHTML = galleryImages.map((src, index) => `
    <div class="thumbnail" data-index="${index}">
      <img src="${src}" alt="Gallery thumbnail ${index + 1}" loading="lazy">
    </div>
  `).join("");

  document.querySelectorAll(".thumbnail").forEach(thumb => {
    thumb.addEventListener("click", () => showGalleryImage(Number(thumb.dataset.index)));
  });

  document.getElementById("galleryPrev").onclick = () => showGalleryImage(currentGalleryIndex - 1);
  document.getElementById("galleryNext").onclick = () => showGalleryImage(currentGalleryIndex + 1);

  showGalleryImage(currentGalleryIndex);
}

function setupFullscreenGallery() {
  document.getElementById("galleryImageWrap").addEventListener("click", () => {
    if (!galleryImages.length) return;

    document.getElementById("fullscreenImage").src = galleryImages[currentGalleryIndex];
    document.getElementById("fullscreen").classList.add("active");
  });

  document.getElementById("fullscreenClose").addEventListener("click", () => {
    document.getElementById("fullscreen").classList.remove("active");
  });

  document.getElementById("fullscreen").addEventListener("click", event => {
    if (event.target.id === "fullscreen") {
      document.getElementById("fullscreen").classList.remove("active");
    }
  });
}

function setupVisitCounter() {
  const current = safeNumber(localStorage.getItem("dashboardVisits")) + 1;
  localStorage.setItem("dashboardVisits", current);
  document.getElementById("visitCounter").innerText = `Visits: ${current}`;
}

function renderCurrentPage() {
  const activePage = document.querySelector(".page.active").id;

  if (activePage === "overview") renderOverview();
  if (activePage === "results") renderResults();
  if (activePage === "goals") renderGoals();
  if (activePage === "attendance") renderAttendance();
  if (activePage === "events") renderEvents();
  if (activePage === "players") renderPlayers();
  if (activePage === "gallery") renderGallery();
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(button => {
    button.addEventListener("click", () => {
      activeResultsFilter = null;
      activeGoalsDrillLabel = "";
      activeAttendanceDrillLabel = "";

      showPage(button.dataset.page);
    });
  });
}

function setupThemeToggle() {
  const toggle = document.getElementById("themeToggle");
  const savedTheme = localStorage.getItem("theme");

  if (savedTheme === "light") {
    document.body.classList.add("light");
    toggle.textContent = "Dark Mode";
  } else {
    document.body.classList.remove("light");
    toggle.textContent = "Light Mode";
    localStorage.setItem("theme", "dark");
  }

  toggle.addEventListener("click", () => {
    document.body.classList.toggle("light");

    const isLight = document.body.classList.contains("light");
    localStorage.setItem("theme", isLight ? "light" : "dark");
    toggle.textContent = isLight ? "Dark Mode" : "Light Mode";

    setTimeout(renderCurrentPage, 80);
  });
}

document.addEventListener("keydown", event => {
  const galleryActive = document.getElementById("gallery").classList.contains("active");

  if (!galleryActive) return;

  if (event.key === "ArrowLeft") showGalleryImage(currentGalleryIndex - 1);
  if (event.key === "ArrowRight") showGalleryImage(currentGalleryIndex + 1);
  if (event.key === "Escape") document.getElementById("fullscreen").classList.remove("active");
});

loadData()
  .then(() => {
    setupTabs();
    setupDashboardHistory();
    setupThemeToggle();
    setupFullscreenGallery();
    setupVisitCounter();

    document.querySelectorAll("input[type='radio']").forEach(input => {
      input.addEventListener("change", () => {
        activeGoalsDrillLabel = "";
        setTimeout(renderCurrentPage, 80);
      });
    });

    renderOverview();
  })
  .catch(error => {
    document.querySelector("main").innerHTML = `
      <div class="card" style="border-left:6px solid red;">
        <h2>Stats failed to load</h2>
        <p><code>${error.message}</code></p>
      </div>
    `;
  });
