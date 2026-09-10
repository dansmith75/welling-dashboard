// Final UI refinements: Fixtures naming and compact player profiles.
(() => {
  store.bios = store.bios || [];

  function playerRecord(displayName) {
    return (store.players || []).find(player =>
      String(player?.displayName || "").trim() === String(displayName || "").trim()
    ) || null;
  }

  function bioRecord(displayName) {
    return (store.bios || []).find(player =>
      String(player?.displayName || "").trim() === String(displayName || "").trim()
    ) || null;
  }

  // The page contains both upcoming fixtures and completed results, so the
  // top-level destination is simply Fixtures.
  const coreRenderResults = renderResults;
  renderResults = function () {
    coreRenderResults();
    const title = document.getElementById("resultsTitle");
    if (title && !activeResultsFilter?.label) title.textContent = "Fixtures";
  };

  // Player buttons act as toggles: click to open, click the selected player
  // again to close, or click another player to switch profiles.
  renderPlayerButtons = function () {
    const grid = document.getElementById("playerGrid");
    if (!grid) return;

    const players = dashboardPlayers();
    grid.innerHTML = players.map(player => `
      <button class="player-button${selectedPlayer === player ? " active" : ""}" data-player="${player}">${player}</button>
    `).join("");

    grid.querySelectorAll(".player-button").forEach(button => {
      button.addEventListener("click", () => {
        const player = button.dataset.player;
        const profile = document.getElementById("playerProfile");

        if (selectedPlayer === player) {
          selectedPlayer = null;
          grid.querySelectorAll(".player-button").forEach(item => item.classList.remove("active"));
          if (profile) profile.innerHTML = "";
          return;
        }

        selectedPlayer = player;
        grid.querySelectorAll(".player-button").forEach(item => {
          item.classList.toggle("active", item.dataset.player === player);
        });
        renderPlayerProfile(player);
      });
    });
  };

  // Profiles remain hidden until somebody deliberately selects a player.
  renderPlayers = function () {
    renderPlayerButtons();
    const profile = document.getElementById("playerProfile");
    if (!profile) return;

    if (!selectedPlayer) {
      profile.innerHTML = "";
      return;
    }

    renderPlayerProfile(selectedPlayer);
  };

  const coreRenderPlayerProfile = renderPlayerProfile;
  renderPlayerProfile = function (player) {
    coreRenderPlayerProfile(player);

    const profileHeader = document.querySelector("#playerProfile .profile-header");
    if (!profileHeader) return;

    const squad = playerRecord(player) || {};
    const bio = bioRecord(player) || {};
    const position = bio.position || squad.position || "Squad Player";
    const strapLine = String(squad.strapLine || "").trim();

    const oldSubtitle = profileHeader.querySelector(".profile-subtitle");
    if (oldSubtitle) oldSubtitle.remove();

    const heading = profileHeader.querySelector("h2");
    if (heading) {
      heading.classList.add("player-name-row");
      heading.innerHTML = `<span>${player}</span><span class="player-position">${position}</span>`;
    }

    if (strapLine) {
      profileHeader.insertAdjacentHTML("beforeend", `
        <div class="player-strapline">“${strapLine}”</div>
      `);
    }
  };

  const style = document.createElement("style");
  style.textContent = `
    .player-name-row {
      display:flex;
      align-items:center;
      flex-wrap:wrap;
      gap:10px;
    }
    .player-position {
      display:inline-flex;
      align-items:center;
      padding:5px 10px;
      border-radius:999px;
      background:rgba(56,189,248,.12);
      border:1px solid var(--line);
      color:var(--text);
      font-size:12px;
      font-weight:bold;
      line-height:1;
    }
    .player-strapline {
      margin-top:10px;
      color:var(--text);
      font-weight:bold;
      font-style:italic;
      line-height:1.45;
    }
  `;
  document.head.appendChild(style);

  fetch("data/bios.json", { cache: "no-store" })
    .then(response => response.ok ? response.json() : [])
    .then(rows => {
      store.bios = Array.isArray(rows) ? rows : [];
      if (selectedPlayer && document.getElementById("players")?.classList.contains("active")) {
        renderPlayerProfile(selectedPlayer);
      }
    })
    .catch(() => {
      store.bios = [];
    });
})();
