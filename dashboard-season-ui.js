// Season-ready UI: completed competitive stats, attendance toggle, focused player view,
// Excel-driven Useful Links and League Table tabs.
(() => {
  let attendanceMode = "match";
  store.links = store.links || [];
  store.leagueTable = store.leagueTable || [];
  store.venues = store.venues || {};

  function completed(match) { return ["Win", "Draw", "Loss"].includes(match?.result); }
  function mobile() { return window.matchMedia("(max-width:650px)").matches; }

  function horizontalBar(name, canvasId, labels, data, colour) {
    destroyChart(name);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const box = canvas.closest(".chart-box");
    if (box) { box.style.height = `${Math.max(420, labels.length * 30 + 70)}px`; box.style.minWidth = "0"; }
    const maxValue = Math.max(...data, 0);
    charts[name] = new Chart(canvas, {
      type: "bar",
      data: { labels, datasets: [{ data, backgroundColor: colour, borderRadius: 8 }] },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } }, layout: { padding: { right: 26, top: 8, bottom: 8 } },
        scales: {
          x: { beginAtZero: true, suggestedMax: maxValue + 1, ticks: { color: chartTextColour(), precision: 0 }, grid: { color: chartGridColour() } },
          y: { ticks: { color: chartTextColour(), autoSkip: false, font: { size: 11 } }, grid: { display: false } }
        }
      }
    });
  }

  const coreRenderOverview = renderOverview;
  renderOverview = function () {
    coreRenderOverview();
    const matches = (store.matches || []).filter(match => isCompetitive(match) && completed(match));
    const stats = matchStats(matches);
    const container = document.getElementById("competitiveSummary");
    if (!container) return;
    const cards = [[stats.games,"Competitive Games","all"],[stats.wins,"Wins","win"],[stats.draws,"Draws","draw"],[stats.losses,"Losses","loss"],[stats.goalsFor,"Goals For","gf"],[stats.goalsAgainst,"Goals Against","ga"]];
    container.innerHTML = cards.map(([value,label,key]) => `<div class="stat drill" data-season-competitive="${key}"><b>${value}</b><span>${label}</span></div>`).join("");
    container.querySelectorAll("[data-season-competitive]").forEach(card => card.addEventListener("click", () => {
      const key = card.dataset.seasonCompetitive;
      const base = m => isCompetitive(m) && completed(m);
      if (key === "all") drillToResults("Competitive Games Played", base);
      if (key === "win") drillToResults("Competitive Wins", m => base(m) && m.result === "Win");
      if (key === "draw") drillToResults("Competitive Draws", m => base(m) && m.result === "Draw");
      if (key === "loss") drillToResults("Competitive Losses", m => base(m) && m.result === "Loss");
      if (key === "gf") drillToResults("Competitive Games — Welling Scored", m => base(m) && safeNumber(m.goalsFor) > 0);
      if (key === "ga") drillToResults("Competitive Games — Opposition Scored", m => base(m) && safeNumber(m.goalsAgainst) > 0);
    }));
  };

  function setAttendanceMode(mode, render = true) {
    attendanceMode = mode === "training" ? "training" : "match";
    document.querySelectorAll(".attendance-mode").forEach(button => button.classList.toggle("active", button.dataset.attendanceMode === attendanceMode));
    const matchContainer = document.getElementById("matchAttendanceContainer");
    const trainingContainer = document.getElementById("trainingAttendanceContainer");
    if (matchContainer) matchContainer.style.display = attendanceMode === "match" ? "block" : "none";
    if (trainingContainer) trainingContainer.style.display = attendanceMode === "training" ? "block" : "none";
    if (render) renderAttendance();
  }

  const coreDrillToAttendance = drillToAttendance;
  drillToAttendance = function (label) {
    setAttendanceMode(String(label || "").toLowerCase().includes("training") ? "training" : "match", false);
    coreDrillToAttendance(label);
  };

  renderAttendance = function () {
    setDrillLabel("attendanceDrillLabel", activeAttendanceDrillLabel);
    const isMatch = attendanceMode === "match";
    const chartName = isMatch ? "matchAttendance" : "trainingAttendance";
    const canvasId = isMatch ? "matchAttendanceChart" : "trainingAttendanceChart";
    const rows = isMatch ? store.matchAttendance : store.trainingAttendance;
    const colour = isMatch ? "rgba(37,99,235,.78)" : "rgba(16,185,129,.82)";
    destroyChart(isMatch ? "trainingAttendance" : "matchAttendance");
    const labels = dashboardPlayers();
    const data = attendanceTotals(rows);
    if (mobile()) horizontalBar(chartName, canvasId, labels, data, colour); else drawBar(chartName, canvasId, labels, data, colour);
  };

  document.querySelectorAll(".attendance-mode").forEach(button => button.addEventListener("click", () => setAttendanceMode(button.dataset.attendanceMode)));
  setAttendanceMode("match", false);

  renderPlayerButtons = function () {
    const grid = document.getElementById("playerGrid");
    if (!grid) return;
    const allPlayers = dashboardPlayers();
    const visiblePlayers = selectedPlayer ? allPlayers.filter(player => player === selectedPlayer) : allPlayers;
    grid.innerHTML = visiblePlayers.map(player => `<button class="player-button${selectedPlayer === player ? " active" : ""}" data-player="${player}">${player}</button>`).join("");
    grid.querySelectorAll(".player-button").forEach(button => button.addEventListener("click", () => {
      const player = button.dataset.player;
      const profile = document.getElementById("playerProfile");
      if (selectedPlayer === player) { selectedPlayer = null; if (profile) profile.innerHTML = ""; renderPlayerButtons(); return; }
      selectedPlayer = player; renderPlayerButtons(); renderPlayerProfile(player);
    }));
  };

  function renderLinks() {
    const target = document.getElementById("usefulLinks"); const empty = document.getElementById("linksEmpty");
    if (!target || !empty) return;
    const rows = store.links || []; empty.style.display = rows.length ? "none" : "block";
    if (!rows.length) { target.innerHTML = ""; return; }
    const groups = new Map();
    rows.forEach(row => { const category = String(row.category || "").trim(); if (!groups.has(category)) groups.set(category, []); groups.get(category).push(row); });
    target.innerHTML = [...groups.entries()].map(([category, items]) => `<div class="link-group">${category && category.toLowerCase() !== "useful links" ? `<h3>${category}</h3>` : ""}<div class="useful-links-grid">${items.map(item => `<a class="useful-link-card" href="${item.url}" target="_blank" rel="noopener noreferrer"><strong>${item.name}</strong>${item.description ? `<span>${item.description}</span>` : ""}</a>`).join("")}</div></div>`).join("");
  }

  function renderLeagueTable() {
    const body = document.getElementById("leagueTableBody"); const empty = document.getElementById("leagueTableEmpty");
    if (!body || !empty) return;
    const rows = store.leagueTable || []; empty.style.display = rows.length ? "none" : "block";
    body.innerHTML = rows.map(row => `<tr class="${/welling united/i.test(String(row.team || "")) ? "our-team-row" : ""}"><td>${row.position ?? ""}</td><td>${row.team || ""}</td><td>${row.played ?? 0}</td><td>${row.won ?? 0}</td><td>${row.drawn ?? 0}</td><td>${row.lost ?? 0}</td><td>${row.goalsFor ?? 0}</td><td>${row.goalsAgainst ?? 0}</td><td>${row.goalDifference ?? 0}</td><td><strong>${row.points ?? 0}</strong></td></tr>`).join("");
  }

  const coreRenderCurrentPage = renderCurrentPage;
  renderCurrentPage = function () {
    const activePage = document.querySelector(".page.active")?.id;
    if (activePage === "links") return renderLinks();
    if (activePage === "league") return renderLeagueTable();
    return coreRenderCurrentPage();
  };

  Promise.all([
    fetch("data/links.json", { cache: "no-store" }).then(r => r.ok ? r.json() : []),
    fetch("data/league-table.json", { cache: "no-store" }).then(r => r.ok ? r.json() : []),
    fetch("data/venues.json", { cache: "no-store" }).then(r => r.ok ? r.json() : {})
  ]).then(([links, league, venues]) => {
    store.links = Array.isArray(links) ? links : []; store.leagueTable = Array.isArray(league) ? league : [];
    store.venues = venues && typeof venues === "object" ? venues : {};
    const activePage = document.querySelector(".page.active")?.id; if (activePage === "links") renderLinks(); if (activePage === "league") renderLeagueTable();
  }).catch(() => { store.links = []; store.leagueTable = []; store.venues = {}; });

  const style = document.createElement("style");
  style.textContent = `.attendance-toggle-card{padding:10px;margin-bottom:18px}.attendance-toggle{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.attendance-mode{border:1px solid var(--line);border-radius:12px;padding:11px 16px;background:transparent;color:var(--text);font-weight:bold;cursor:pointer}.attendance-mode.active{background:linear-gradient(135deg,#1e3a8a,#2563eb);border-color:#2563eb;color:white}.link-group+.link-group{margin-top:24px}.useful-links-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.useful-link-card{display:flex;flex-direction:column;gap:6px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--text);text-decoration:none}.useful-link-card:hover{transform:translateY(-1px);border-color:#38bdf8}.useful-link-card span{color:var(--muted);font-size:13px;line-height:1.4}.our-team-row td{font-weight:bold;background:rgba(37,99,235,.14)}@media(max-width:650px){#attendance .chart-scroll{overflow-x:visible}#attendance .chart-box{width:100%;min-width:0!important}.useful-links-grid{grid-template-columns:1fr}.league-table-wrap{border-right:2px solid rgba(56,189,248,.45);-webkit-overflow-scrolling:touch}}`;
  document.head.appendChild(style);
})();
