const state = { accounts: [], selectedAccounts: new Set(), accountsInitialized: false, color: "white", path: [] };
const ALL_GAMES_START = "2010-01-01";

function qs(id) { return document.getElementById(id); }
function formatPercent(value) { return `${Number(value || 0).toFixed(1)}%`; }
function localToday() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function setAllGamesDates(prefix) {
  qs(`${prefix}-start`).value = ALL_GAMES_START;
  qs(`${prefix}-end`).value = localToday();
}

function setAnalysisPeriod(mode) {
  const allGames = mode === "all";
  if (allGames) setAllGamesDates("filter");
  qs("filter-start").readOnly = allGames;
  qs("filter-end").readOnly = allGames;
}

function setSyncPeriod(allGames) {
  const row = qs("sync-start").closest(".date-row");
  if (allGames) setAllGamesDates("sync");
  qs("sync-start").readOnly = allGames;
  qs("sync-end").readOnly = allGames;
  row.classList.toggle("readonly", allGames);
}

function queryParams(extra = {}) {
  const params = new URLSearchParams();
  params.set("accounts", state.selectedAccounts.size ? [...state.selectedAccounts].join(",") : "0");
  const start = qs("filter-start")?.value;
  const end = qs("filter-end")?.value;
  const speed = qs("filter-speed")?.value;
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  if (speed) params.set("time_classes", speed);
  Object.entries(extra).forEach(([key, value]) => params.set(key, value));
  return params.toString();
}

async function getJSON(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Something went wrong.");
  return payload;
}

async function loadAccounts() {
  const payload = await getJSON("/api/accounts");
  const previousIds = new Set(state.accounts.map(account => account.id));
  state.accounts = payload.accounts;
  const validIds = new Set(payload.accounts.map(account => account.id));
  state.selectedAccounts = new Set([...state.selectedAccounts].filter(id => validIds.has(id)));
  payload.accounts.forEach(account => {
    if (!state.accountsInitialized || !previousIds.has(account.id)) state.selectedAccounts.add(account.id);
  });
  state.accountsInitialized = true;
  renderAccounts();
}

function renderAccounts() {
  const holder = qs("account-chips");
  const totalGames = state.accounts.reduce((sum, account) => sum + account.game_count, 0);
  qs("sidebar-game-count").textContent = totalGames ? `${totalGames.toLocaleString()} saved games` : "No games yet";
  qs("account-summary").textContent = state.accounts.length ? `${state.accounts.length} account${state.accounts.length === 1 ? "" : "s"} connected` : "Local database";
  if (!holder) return;
  if (!state.accounts.length) {
    holder.innerHTML = '<span class="muted">No accounts imported</span>';
    return;
  }
  holder.innerHTML = state.accounts.map(account => `<button class="chip account-card ${state.selectedAccounts.has(account.id) ? "selected" : ""}" data-account="${account.id}" aria-pressed="${state.selectedAccounts.has(account.id)}" title="${state.selectedAccounts.has(account.id) ? "Included in analysis" : "Excluded from analysis"}">
    <span class="account-card-top"><span class="account-indicator"></span><strong>${account.display_name}</strong><small>${account.game_count} games</small></span>
    <span class="account-ratings">
      <span><small>Blitz</small><strong>${account.blitz_rating ?? "—"}</strong><em>${account.blitz_rating_date ?? "Not synced"}</em></span>
      <span><small>Rapid</small><strong>${account.rapid_rating ?? "—"}</strong><em>${account.rapid_rating_date ?? "Not synced"}</em></span>
    </span>
  </button>`).join("");
  holder.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", async () => {
    const id = Number(chip.dataset.account);
    state.selectedAccounts.has(id) ? state.selectedAccounts.delete(id) : state.selectedAccounts.add(id);
    state.path = [];
    renderAccounts();
    await refreshPage();
  }));
}

async function loadOverview() {
  const holder = qs("overview-stats");
  if (!holder) return;
  const data = await getJSON(`/api/overview?${queryParams()}`);
  holder.innerHTML = `
    <article><span>Games in view</span><strong>${data.games.toLocaleString()}</strong><small>${data.first_game ? `${data.first_game} → ${data.last_game}` : "Selected filters"}</small></article>
    <article><span>Win rate</span><strong>${formatPercent(data.win_pct)}</strong><small>${data.wins} wins</small></article>
    <article><span>Draw rate</span><strong>${formatPercent(data.draw_pct)}</strong><small>${data.draws} draws</small></article>
    <article class="accent-stat"><span>Expected points</span><strong>${Number(data.expected_score).toFixed(3)}</strong><small>Per game</small></article>`;
}

function renderPath() {
  const holder = qs("move-path");
  if (!holder) return;
  holder.innerHTML = state.path.map((move, index) => `${index % 2 === 0 ? `<span class="path-number">${Math.floor(index / 2) + 1}.</span>` : ""}<button type="button" class="path-move" data-ply="${index}" title="Go back to the position after ${move}">${move}</button>`).join("");
  holder.querySelectorAll(".path-move").forEach(button => button.addEventListener("click", () => {
    state.path = state.path.slice(0, Number(button.dataset.ply) + 1);
    loadExplorer();
  }));
  qs("position-title").textContent = state.path.length ? state.path.join(" ") : "Starting position";
  qs("reset-path").disabled = !state.path.length;
}

function renderBoard(fen, lastMove) {
  const board = qs("chess-board");
  if (!board || !fen) return;
  const pieceImages = { K: "wK", Q: "wQ", R: "wR", B: "wB", N: "wN", P: "wP", k: "bK", q: "bQ", r: "bR", b: "bB", n: "bN", p: "bP" };
  const position = {};
  fen.split(" ")[0].split("/").forEach((row, rowIndex) => {
    let fileIndex = 0;
    for (const token of row) {
      if (/\d/.test(token)) {
        fileIndex += Number(token);
      } else {
        position[`${"abcdefgh"[fileIndex]}${8 - rowIndex}`] = token;
        fileIndex += 1;
      }
    }
  });

  const whiteView = state.color === "white";
  const files = whiteView ? [..."abcdefgh"] : [..."hgfedcba"];
  const ranks = whiteView ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
  const highlighted = new Set(lastMove ? [lastMove.slice(0, 2), lastMove.slice(2, 4)] : []);
  board.innerHTML = ranks.flatMap((rank, rowIndex) => files.map((file, columnIndex) => {
    const square = `${file}${rank}`;
    const piece = position[square];
    const naturalFile = "abcdefgh".indexOf(file);
    const light = (naturalFile + rank) % 2 === 0;
    const pieceColor = piece ? (piece === piece.toUpperCase() ? "white" : "black") : "";
    const rankLabel = columnIndex === 0 ? `<span class="coordinate rank">${rank}</span>` : "";
    const fileLabel = rowIndex === 7 ? `<span class="coordinate file">${file}</span>` : "";
    return `<div class="board-square ${light ? "light" : "dark"} ${highlighted.has(square) ? "last-move" : ""}" data-square="${square}">${rankLabel}${fileLabel}${piece ? `<img class="board-piece ${pieceColor}" src="/pieces/${pieceImages[piece]}.svg" alt="" draggable="false">` : ""}</div>`;
  })).join("");
  board.setAttribute("aria-label", `${state.color === "white" ? "White" : "Black"} perspective. ${state.path.length ? `Position after ${state.path.join(" ")}` : "Starting position"}.`);
}

async function loadExplorer() {
  const body = qs("moves-body");
  if (!body) return;
  body.classList.add("loading");
  const data = await getJSON(`/api/explorer?${queryParams({ color: state.color, path: state.path.join("|") })}`);
  qs("turn-label").textContent = data.actor === "you" ? "Your move" : "Opponent response";
  renderPath();
  renderBoard(data.fen, data.last_move);
  qs("board-title").textContent = data.turn === "white" ? "White to move" : "Black to move";
  if (!data.moves.length) {
    body.innerHTML = `<tr><td colspan="4" class="empty-cell">${state.accounts.length ? "No games reach this position with the selected filters." : "Import an account to begin exploring."}</td></tr>`;
  } else {
    body.innerHTML = data.moves.map((move, index) => `<tr class="move-row" data-move="${move.san}">
      <td><span class="move-name"><span class="move-rank">${index + 1}</span>${move.san}</span></td>
      <td>${move.games}</td>
      <td><div class="result-visual">
        <span class="result-bar" aria-hidden="true"><i class="win" style="width:${move.win_pct}%"></i><i class="draw" style="width:${move.draw_pct}%"></i><i class="loss" style="width:${move.loss_pct}%"></i></span>
        <span class="result-legend" aria-label="Win ${move.win_pct}%, draw ${move.draw_pct}%, loss ${move.loss_pct}%">
          <span class="legend-win"><i></i>Win: ${formatPercent(move.win_pct)}</span>
          <span class="legend-draw"><i></i>Draw: ${formatPercent(move.draw_pct)}</span>
          <span class="legend-loss"><i></i>Loss: ${formatPercent(move.loss_pct)}</span>
        </span>
      </div></td>
      <td class="points">${Number(move.expected_score).toFixed(3)}</td></tr>`).join("");
    body.querySelectorAll(".move-row").forEach(row => row.addEventListener("click", () => {
      state.path.push(row.dataset.move);
      loadExplorer();
    }));
  }
  body.classList.remove("loading");
}

async function refreshPage() {
  if (document.body.dataset.page === "explorer") await Promise.all([loadOverview(), loadExplorer()]);
  if (document.body.dataset.page === "insights") await loadInsights();
}

async function loadInsights() {
  const holder = qs("insights-list");
  if (!holder) return;
  holder.classList.add("loading");
  const depth = qs("depth").value;
  const minimum = qs("minimum").value;
  try {
    const data = await getJSON(`/api/insights?${queryParams({ depth, minimum })}`);
    qs("insight-count").textContent = data.insights.length;
    if (!data.insights.length) {
      holder.innerHTML = `<section class="panel empty-state"><span class="empty-icon">♙</span><h2>No comparisons at this sample size</h2><p>Try lowering the minimum games or importing a wider date range.</p></section>`;
    } else {
      holder.innerHTML = data.insights.map((item, index) => `<article class="panel insight-card">
        <div class="insight-position"><span class="eyebrow">Decision ${String(index + 1).padStart(2, "0")} · after ${item.ply} plies</span><h2>${item.path.length ? item.path.slice(-4).join(" ") : "First move"}</h2>
          <div class="line-notation">${item.path.length ? item.path.map(move => `<span>${move}</span>`).join("") : "<span>Starting position</span>"}</div>
          <span class="spread-badge">${item.spread.toFixed(3)} point gap</span></div>
        <div class="candidate-list">${item.moves.map(move => `<div class="candidate"><strong>${move.san}</strong><span class="score-track"><i style="width:${move.expected_score * 100}%"></i></span><small>${move.games} games</small><span class="candidate-score">${move.expected_score.toFixed(3)}</span></div>`).join("")}</div>
      </article>`).join("");
    }
  } catch (error) {
    holder.innerHTML = `<section class="panel empty-state"><h2>Analysis couldn’t run</h2><p>${error.message}</p></section>`;
  } finally {
    holder.classList.remove("loading");
  }
}

function bindUI() {
  qs("open-sync").addEventListener("click", () => qs("sync-dialog").showModal());
  qs("close-sync").addEventListener("click", () => qs("sync-dialog").close());
  qs("hide-sidebar").addEventListener("click", () => {
    if (window.matchMedia("(max-width: 760px)").matches) {
      document.body.classList.remove("nav-open");
    } else {
      document.body.classList.add("sidebar-collapsed");
      localStorage.setItem("chess-insight-sidebar", "collapsed");
    }
  });
  document.querySelector(".mobile-menu").addEventListener("click", () => {
    if (window.matchMedia("(max-width: 760px)").matches) {
      document.body.classList.toggle("nav-open");
    } else {
      document.body.classList.remove("sidebar-collapsed");
      localStorage.setItem("chess-insight-sidebar", "open");
    }
  });
  qs("apply-filters")?.addEventListener("click", () => { state.path = []; refreshPage(); });
  qs("filter-period")?.addEventListener("change", event => setAnalysisPeriod(event.target.value));
  [qs("filter-start"), qs("filter-end")].forEach(input => input?.addEventListener("change", () => {
    if (!input.readOnly) qs("filter-period").value = "custom";
  }));
  qs("sync-all-games").addEventListener("change", event => setSyncPeriod(event.target.checked));
  qs("reset-path")?.addEventListener("click", () => { state.path = []; loadExplorer(); });
  document.querySelectorAll("[data-color]").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll("[data-color]").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.color = button.dataset.color;
    state.path = [];
    loadExplorer();
  }));
  qs("run-insights")?.addEventListener("click", loadInsights);
  qs("sync-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = qs("sync-message");
    const button = form.querySelector('[type="submit"]');
    const data = Object.fromEntries(new FormData(form));
    message.className = "dialog-message";
    message.textContent = "Checking Chess.com archives…";
    button.disabled = true;
    try {
      const result = await getJSON("/api/accounts/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      message.className = "dialog-message success";
      message.textContent = `${result.games_added} new games saved from ${result.archives_checked} archive${result.archives_checked === 1 ? "" : "s"}.`;
      await loadAccounts();
      await refreshPage();
    } catch (error) {
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  if (localStorage.getItem("chess-insight-sidebar") === "collapsed" && !window.matchMedia("(max-width: 760px)").matches) {
    document.body.classList.add("sidebar-collapsed");
  }
  setAnalysisPeriod("all");
  setSyncPeriod(true);
  bindUI();
  try { await loadAccounts(); await refreshPage(); }
  catch (error) { console.error(error); }
});
