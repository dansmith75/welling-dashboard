// Show the next unplayed fixture alongside the form guide.
(() => {
  function normaliseTeam(value) {
    return String(value || "").toLowerCase().replace(/\b(f\.?c\.?)\b/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  }

  function oppositionRecord(opposition) {
    const wanted = normaliseTeam(opposition);
    return (store.leagueTable || []).find(row => normaliseTeam(row.team) === wanted) || null;
  }

  function venueRecord(match) {
    const venueName = String(match.venue || "").trim();
    const key = venueName.toLowerCase();
    return store.venues?.[key] || { name: venueName || "Venue to be confirmed", address: "" };
  }

  function mapLink(provider, query) {
    const encoded = encodeURIComponent(query);
    return provider === "apple"
      ? `https://maps.apple.com/?q=${encoded}`
      : `https://www.google.com/maps/search/?api=1&query=${encoded}`;
  }

  function renderNextMatchDetails(match) {
    const target = document.getElementById("nextMatchDetails");
    if (!target) return;
    const venue = venueRecord(match);
    const query = venue.address || `${venue.name}, ${match.opposition || ""}`;
    const record = oppositionRecord(match.opposition);
    const played = Number(record?.played || 0);
    const formMessage = record
      ? (played ? `${record.won || 0} won · ${record.drawn || 0} drawn · ${record.lost || 0} lost` : "No league results yet")
      : "League record is not available yet";

    target.innerHTML = `
      <div class="next-match-page-heading">
        <div class="next-detail-label">Next Match</div>
        <h1>${match.opposition || "Opposition TBC"}</h1>
        <p>${formatDateUK(match.date)}${match.kickoff ? ` · ${match.kickoff}` : ""}${match.competition ? ` · ${match.competition}` : ""}${match.homeAway ? ` · ${match.homeAway}` : ""}</p>
      </div>
      <div class="next-match-details-grid">
        <section class="card next-match-detail-card">
          <div class="next-detail-label">Venue</div>
          <h2>${venue.name}</h2>
          <p>${venue.address || "Address not yet recorded"}</p>
          <div class="map-actions">
            <a href="${mapLink("apple", query)}" target="_blank" rel="noopener noreferrer">Open in Apple Maps</a>
            <a href="${mapLink("google", query)}" target="_blank" rel="noopener noreferrer">Open in Google Maps</a>
          </div>
        </section>
        <section class="card next-match-detail-card">
          <div class="next-detail-label">Opposition form</div>
          <h2>${match.opposition || "Opposition"}</h2>
          <p class="opposition-summary">${formMessage}</p>
          ${record ? `<div class="opposition-record"><span><b>${played ? (record.position ?? "–") : "–"}</b>Position</span><span><b>${played}</b>Played</span><span><b>${record.goalsFor ?? 0}</b>GF</span><span><b>${record.goalsAgainst ?? 0}</b>GA</span><span><b>${record.points ?? 0}</b>Points</span></div>` : ""}
        </section>
      </div>`;
  }

  function nextFixture() {
    return (store.matches || [])
      .filter(match => !match.postponed)
      .filter(match => match.goalsFor == null && match.goalsAgainst == null && !match.result)
      .slice()
      .sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")))[0] || null;
  }

  function renderNextMatch() {
    const formGuide = document.getElementById("formGuide");
    const card = formGuide?.closest(".card");
    if (!formGuide || !card) return;

    let layout = card.querySelector(".form-next-layout");
    if (!layout) {
      const intro = card.querySelector(".executive");
      layout = document.createElement("div");
      layout.className = "form-next-layout";

      const formSide = document.createElement("div");
      formSide.className = "form-side";
      if (intro) formSide.appendChild(intro);
      formSide.appendChild(formGuide);

      const nextSide = document.createElement("div");
      nextSide.className = "next-match-side";
      nextSide.id = "nextMatchCard";

      layout.appendChild(formSide);
      layout.appendChild(nextSide);
      card.appendChild(layout);
    }

    const target = document.getElementById("nextMatchCard");
    if (!target) return;

    const match = nextFixture();
    if (!match) {
      target.innerHTML = `<div class="next-match-label">Next Match</div><div class="next-match-none">No upcoming fixture</div>`;
      target.onclick = null;
      return;
    }

    const venue = match.venue || match.homeAway || "";
    const competition = match.competition || "";
    target.innerHTML = `
      <div class="next-match-label">Next Match</div>
      <div class="next-match-opposition">${match.opposition || "TBC"}</div>
      <div class="next-match-meta">${formatDateUK(match.date)}${match.kickoff ? ` · ${match.kickoff}` : ""}${venue ? ` · ${venue}` : ""}</div>
      ${competition ? `<div class="next-match-competition">${competition}</div>` : ""}
      <div class="next-match-hint">View fixture →</div>
    `;
    target.onclick = () => {
      drillToResults(
        `Next Match — ${formatDateUK(match.date)} vs ${match.opposition}`,
        m => m.id === match.id
      );
      renderNextMatchDetails(match);
    };
  }

  const coreRenderOverviewNextMatch = renderOverview;
  renderOverview = function () {
    coreRenderOverviewNextMatch();
    renderNextMatch();
  };

  const style = document.createElement("style");
  style.textContent = `
    .form-next-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,.85fr);gap:28px;align-items:center}
    .form-side{min-width:0}
    .next-match-side{border-left:1px solid var(--line);padding:8px 8px 8px 28px;cursor:pointer;min-height:108px;display:flex;flex-direction:column;justify-content:center}
    .next-match-side:hover .next-match-opposition{color:#38bdf8}
    .next-match-label{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:800;margin-bottom:6px}
    .next-match-opposition{font-size:24px;font-weight:800;line-height:1.15;color:var(--text);transition:color .15s ease}
    .next-match-meta{font-size:15px;color:var(--text);margin-top:7px}
    .next-match-competition{font-size:13px;color:var(--muted);margin-top:4px}
    .next-match-hint{font-size:12px;color:#38bdf8;margin-top:9px;font-weight:700}
    .next-match-none{font-size:16px;color:var(--muted)}
    .next-match-details-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-bottom:18px}
    .next-match-page-heading{margin:4px 0 18px}
    .next-match-page-heading h1{margin:4px 0 5px;font-size:30px;line-height:1.15}
    .next-match-page-heading p{margin:0;color:var(--muted)}
    .next-match-detail-card{margin:0;min-width:0}
    .next-match-detail-card h2{margin:5px 0 7px;font-size:22px}
    .next-match-detail-card p{margin:0;color:var(--muted);line-height:1.45}
    .next-detail-label{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#38bdf8;font-weight:800}
    .map-actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
    .map-actions a{display:inline-flex;padding:10px 13px;border-radius:10px;background:#2563eb;color:white;text-decoration:none;font-weight:800;font-size:13px}
    .map-actions a:last-child{background:transparent;border:1px solid var(--line);color:var(--text)}
    .opposition-summary{margin-bottom:15px!important}
    .opposition-record{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
    .opposition-record span{display:flex;flex-direction:column;gap:3px;color:var(--muted);font-size:11px;text-align:center;text-transform:uppercase}
    .opposition-record b{font-size:20px;color:var(--text)}
    @media(max-width:650px){
      .form-next-layout{grid-template-columns:1fr;gap:18px}
      .next-match-side{border-left:0;border-top:1px solid var(--line);padding:18px 0 0;min-height:0}
      .next-match-opposition{font-size:21px}
      .next-match-details-grid{grid-template-columns:1fr;gap:12px}
      .map-actions{display:grid;grid-template-columns:1fr 1fr}
      .map-actions a{justify-content:center;text-align:center}
    }
  `;
  document.head.appendChild(style);
})();
