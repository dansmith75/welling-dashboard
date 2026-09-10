// Make player figures in the goals, assists and attendance charts open the
// matching player detail. This works for both desktop and mobile chart layouts.
(() => {
  const detailByCanvas = {
    goalsByPlayerChart: "goals",
    assistsByPlayerChart: "assists",
    matchAttendanceChart: "matchAttendance",
    trainingAttendanceChart: "trainingAttendance"
  };

  function openPlayerDetail(chart, element, detailType) {
    const player = chart.data.labels?.[element.index];
    if (!player) return;

    selectedPlayer = player;
    showPage("players");

    // showPage schedules the page renderer, so add the detail immediately after
    // that render instead of allowing it to replace the expanded information.
    window.setTimeout(() => {
      renderPlayerButtons();
      renderPlayerProfile(player);
      showPlayerDetail(player, detailType);

      document.getElementById("playerDetailBox")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start"
      });
    }, 120);
  }

  Chart.register({
    id: "wellingPlayerDetailDrilldown",
    afterEvent(chart, args) {
      const canvas = chart.canvas;
      const detailType = detailByCanvas[canvas?.id];
      if (!detailType) return;

      const elements = chart.getElementsAtEventForMode(
        args.event.native || args.event,
        "nearest",
        { intersect: true },
        false
      );

      canvas.style.cursor = elements.length ? "pointer" : "default";
      if (args.event.type !== "click" || !elements.length) return;
      openPlayerDetail(chart, elements[0], detailType);
    }
  });

  document.querySelectorAll("#goals .chart-title, #attendance .chart-title").forEach(title => {
    if (title.nextElementSibling?.classList.contains("chart-detail-hint")) return;
    const hint = document.createElement("p");
    hint.className = "chart-detail-hint";
    hint.textContent = "Tap a player’s figure to see the detail";
    title.insertAdjacentElement("afterend", hint);
  });
})();
