const EXPORT_REQUEST_SIZE = 200;
const MAX_TOTAL_PGN_BYTES = 20 * 1024 * 1024;
const SEARCH_PAGE_SIZE = 100;

const elements = {
  hostBadge: document.querySelector("#hostBadge"),
  settings: document.querySelector("#settings"),
  settingsForm: document.querySelector("#settingsForm"),
  scidExecutable: document.querySelector("#scidExecutable"),
  databaseBase: document.querySelector("#databaseBase"),
  saveSettings: document.querySelector("#saveSettings"),
  searchForm: document.querySelector("#searchForm"),
  player: document.querySelector("#player"),
  search: document.querySelector("#search"),
  status: document.querySelector("#status"),
  candidateSection: document.querySelector("#candidateSection"),
  candidates: document.querySelector("#candidates"),
  resultsSection: document.querySelector("#resultsSection"),
  games: document.querySelector("#games"),
  selectAll: document.querySelector("#selectAll"),
  selectNone: document.querySelector("#selectNone"),
  loadMore: document.querySelector("#loadMore"),
  downloadPgn: document.querySelector("#downloadPgn"),
  copyPgn: document.querySelector("#copyPgn")
};

const state = {
  ready: false,
  busy: false,
  // The active search as classified by ChessGenieQuery. "Load more" reuses
  // this object, so a FIDE-ID search keeps paging by ID.
  query: null,
  // The stored player name shown in results and used for file names.
  player: "",
  total: 0,
  nextCursor: null,
  games: [],
  // Every matching game number, not only the rendered page, so an export can
  // cover the whole result set.
  resultNumbers: [],
  selected: new Set()
};

async function nativeRequest(command, payload = {}) {
  const response = await chrome.runtime.sendMessage({
    type: "native-request",
    command,
    payload
  });
  if (!response?.ok) {
    const error = new Error(response?.error?.message ?? "The native helper did not respond.");
    error.code = response?.error?.code ?? "NATIVE_HOST_ERROR";
    throw error;
  }
  return response;
}

function setStatus(message) {
  elements.status.textContent = message;
}

function setBusy(busy) {
  state.busy = busy;
  elements.saveSettings.disabled = busy;
  elements.search.disabled = busy || !state.ready;
  elements.loadMore.disabled = busy;
  updateExportButtons();
}

function setHostBadge(label, kind = "") {
  elements.hostBadge.textContent = label;
  elements.hostBadge.className = `badge ${kind}`.trim();
}

function updateExportButtons() {
  const disabled = state.busy || state.selected.size === 0;
  elements.downloadPgn.disabled = disabled;
  elements.copyPgn.disabled = disabled;
}

function resetResults() {
  state.total = 0;
  state.nextCursor = null;
  state.games = [];
  state.resultNumbers = [];
  state.selected.clear();
  elements.games.replaceChildren();
  elements.resultsSection.classList.add("hidden");
  elements.loadMore.classList.add("hidden");
  updateExportButtons();
}

function renderCandidates(candidates) {
  elements.candidates.replaceChildren();
  elements.candidateSection.classList.toggle("hidden", candidates.length === 0);

  for (const candidate of candidates) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${candidate.name} (${candidate.frequency})`;
    button.addEventListener("click", () => {
      elements.player.value = candidate.name;
      void runSearch({ kind: "player", player: candidate.name }, false);
    });
    elements.candidates.append(button);
  }
}

function appendGames(games) {
  for (const game of games) {
    if (state.games.some((existing) => existing.gameNumber === game.gameNumber)) {
      continue;
    }
    state.games.push(game);

    const row = document.createElement("tr");
    const selectedCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "game-check";
    checkbox.checked = state.selected.has(game.gameNumber);
    checkbox.dataset.gameNumber = String(game.gameNumber);
    checkbox.setAttribute("aria-label", `Select game ${game.gameNumber}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.selected.add(game.gameNumber);
      } else {
        state.selected.delete(game.gameNumber);
      }
      updateExportButtons();
    });
    selectedCell.append(checkbox);
    row.append(selectedCell);

    for (const value of [
      game.date ?? "—",
      playerWithElo(game.white, game.whiteElo),
      playerWithElo(game.black, game.blackElo),
      game.result ?? "—",
      game.event ?? "—"
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    elements.games.append(row);
  }
  elements.resultsSection.classList.toggle("hidden", state.games.length === 0);
  updateExportButtons();
}

// Prefer the full result set; fall back to rendered rows if the helper did
// not report one.
function exportableNumbers() {
  return state.resultNumbers.length > 0
    ? state.resultNumbers
    : state.games.map((game) => game.gameNumber);
}

function playerWithElo(name, elo) {
  if (!name) return "—";
  return elo ? `${name} (${elo})` : name;
}

async function refreshStatus() {
  try {
    const response = await nativeRequest("status");
    state.ready = response.ready === true;
    if (response.scidExecutable) elements.scidExecutable.value = response.scidExecutable;
    if (response.databaseBase) elements.databaseBase.value = response.databaseBase;

    if (state.ready) {
      setHostBadge("Ready", "ready");
      setStatus(`Using ${response.databaseLabel}.`);
      elements.settings.open = false;
    } else {
      setHostBadge(response.configured ? "Needs attention" : "Setup required", "error");
      setStatus("Configure the Scid executable and database before searching.");
      elements.settings.open = true;
    }
  } catch {
    state.ready = false;
    setHostBadge("Helper unavailable", "error");
    setStatus("Install and register the native helper, then reopen Chrome.");
    elements.settings.open = true;
  }
  elements.search.disabled = state.busy || !state.ready;
}

function searchRequest(query, cursor) {
  if (query.kind === "fideId") {
    return ["searchFideId", { fideId: query.fideId, limit: SEARCH_PAGE_SIZE, cursor }];
  }
  return ["searchPlayer", { player: query.player, limit: SEARCH_PAGE_SIZE, cursor }];
}

function resultLabel() {
  const query = state.query;
  const fallback = ChessGenieQuery.label(query);
  if (query.kind === "fideId" && state.player && state.player !== fallback) {
    return `${state.player} (FIDE ID ${query.fideId})`;
  }
  return state.player || fallback;
}

function submitSearch(rawValue) {
  if (!state.ready || state.busy) return;
  const query = ChessGenieQuery.classify(rawValue);
  if (query.kind !== "player" && query.kind !== "fideId") {
    setStatus(ChessGenieQuery.validationMessage(query));
    return;
  }
  void runSearch(query, false);
}

async function runSearch(query, append) {
  if (!state.ready || state.busy) return;

  if (!append) {
    resetResults();
    renderCandidates([]);
    state.query = query;
    state.player = "";
  }

  setBusy(true);
  setStatus(append ? "Loading more games…" : ChessGenieQuery.searchingMessage(query));
  try {
    const [command, payload] = searchRequest(query, append ? state.nextCursor : 0);
    const response = await nativeRequest(command, payload);

    if (response.playerNotFound) {
      setStatus(ChessGenieQuery.notFoundMessage(query));
      return;
    }
    if (response.requiresPlayerChoice) {
      renderCandidates(response.candidates ?? []);
      setStatus("Choose the exact player before searching games.");
      return;
    }

    renderCandidates([]);
    if (!state.player) {
      state.player = response.selectedPlayer ?? ChessGenieQuery.label(query);
    }
    state.total = response.total ?? 0;
    state.nextCursor = response.nextCursor ?? null;
    if (!append) {
      state.resultNumbers = response.gameNumbers ?? [];
      // Every match starts selected, including pages not rendered yet.
      state.selected = new Set(exportableNumbers());
    }
    appendGames(response.games ?? []);
    elements.loadMore.classList.toggle("hidden", state.nextCursor === null);
    let message =
      `Showing ${state.games.length} of ${state.total} games for ${resultLabel()}. ` +
      `${state.selected.size} selected for export.`;
    if (state.resultNumbers.length > 0 && state.resultNumbers.length < state.total) {
      message += ` Export covers the newest ${state.resultNumbers.length} games.`;
    }
    setStatus(message);
    await chrome.storage.local.set({
      player: query.kind === "fideId" ? query.fideId : state.player
    });
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function collectSelectedPgn() {
  let pending = exportableNumbers().filter((number) => state.selected.has(number));
  if (pending.length === 0) {
    throw new Error("Select at least one game to export.");
  }
  const total = pending.length;
  const chunks = [];
  let bytes = 0;

  while (pending.length > 0) {
    const requestBatch = pending.slice(0, EXPORT_REQUEST_SIZE);
    const untouched = pending.slice(EXPORT_REQUEST_SIZE);
    const response = await nativeRequest("getPgn", { gameNumbers: requestBatch });
    if (!Array.isArray(response.games) || response.games.length === 0) {
      throw new Error("The helper returned no PGN data.");
    }

    for (const game of response.games) {
      const text = `${game.pgn.trim()}\n`;
      bytes += new TextEncoder().encode(text).byteLength;
      if (bytes > MAX_TOTAL_PGN_BYTES) {
        throw new Error("The selected PGN export is larger than 20 MB. Select fewer games.");
      }
      chunks.push(text);
    }

    pending = [...(response.remainingGameNumbers ?? []), ...untouched];
    setStatus(`Exporting PGN… ${total - pending.length}/${total}`);
  }

  return `${chunks.join("\n").trim()}\n`;
}

function exportFilename() {
  const safePlayer = (state.player || "chess-games")
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase()
    .slice(0, 60) || "chess-games";
  return `${safePlayer}-${new Date().toISOString().slice(0, 10)}.pgn`;
}

async function downloadPgn(pgn) {
  const url = URL.createObjectURL(new Blob([pgn], { type: "application/x-chess-pgn" }));
  try {
    await chrome.downloads.download({ url, filename: exportFilename(), saveAs: true });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }
}

elements.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  setStatus("Verifying local paths…");
  try {
    const response = await nativeRequest("configure", {
      scidExecutable: elements.scidExecutable.value.trim(),
      databaseBase: elements.databaseBase.value.trim()
    });
    state.ready = response.ready === true;
    setHostBadge(state.ready ? "Ready" : "Needs attention", state.ready ? "ready" : "error");
    setStatus(state.ready ? `Using ${response.databaseLabel}.` : "The configuration is not ready.");
    elements.settings.open = !state.ready;
  } catch (error) {
    state.ready = false;
    setHostBadge("Needs attention", "error");
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
});

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitSearch(elements.player.value);
});

elements.loadMore.addEventListener("click", () => {
  if (state.nextCursor !== null && state.query) void runSearch(state.query, true);
});

elements.selectAll.addEventListener("click", () => {
  state.selected = new Set(exportableNumbers());
  document.querySelectorAll(".game-check").forEach((checkbox) => {
    checkbox.checked = true;
  });
  updateExportButtons();
});

elements.selectNone.addEventListener("click", () => {
  state.selected.clear();
  document.querySelectorAll(".game-check").forEach((checkbox) => {
    checkbox.checked = false;
  });
  updateExportButtons();
});

elements.downloadPgn.addEventListener("click", async () => {
  setBusy(true);
  try {
    const pgn = await collectSelectedPgn();
    await downloadPgn(pgn);
    setStatus(`Prepared ${state.selected.size} games as ${exportFilename()}.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
});

elements.copyPgn.addEventListener("click", async () => {
  setBusy(true);
  try {
    const pgn = await collectSelectedPgn();
    await navigator.clipboard.writeText(pgn);
    setStatus(`Copied ${state.selected.size} games as PGN.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
});

chrome.storage.local.get(["player"], (saved) => {
  elements.player.value = saved.player ?? "";
});

updateExportButtons();
void refreshStatus();
