import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(fs.readFileSync(path.join(directory, "manifest.json"), "utf8"));
const popupHtml = fs.readFileSync(path.join(directory, "popup.html"), "utf8");
const popupJs = fs.readFileSync(path.join(directory, "popup.js"), "utf8");
const queryJs = fs.readFileSync(path.join(directory, "query.js"), "utf8");
const serviceWorker = fs.readFileSync(path.join(directory, "service-worker.js"), "utf8");

assert.equal(manifest.manifest_version, 3);
assert.deepEqual(
  [...manifest.permissions].sort(),
  ["clipboardWrite", "downloads", "nativeMessaging", "storage"].sort()
);
assert.equal("host_permissions" in manifest, false);
assert.equal("content_scripts" in manifest, false);
assert.equal("externally_connectable" in manifest, false);

for (const id of [
  "settingsForm",
  "scidExecutable",
  "databaseBase",
  "searchForm",
  "player",
  "candidates",
  "games",
  "downloadPgn",
  "copyPgn"
]) {
  assert.match(popupHtml, new RegExp(`id=["']${id}["']`));
  assert.match(popupJs, new RegExp(`#${id}`));
}

assert.match(serviceWorker, /chrome\.runtime\.sendNativeMessage/);
assert.match(popupJs, /chrome\.downloads\.download/);
assert.match(popupJs, /navigator\.clipboard\.writeText/);

const runtimeSource = `${popupHtml}\n${popupJs}\n${queryJs}\n${serviceWorker}`.toLowerCase();
assert.equal(runtimeSource.includes("chessgenie.app"), false);
assert.equal(runtimeSource.includes("content script"), false);

console.log("Extension manifest and source-agnostic boundary verified.");

// --- Name-or-FIDE-ID search ------------------------------------------------

// query.js is a classic script shared by the popup, so evaluate it the same
// way the browser does and pick up the global it defines.
const ChessGenieQuery = vm.runInThisContext(`${queryJs}\nChessGenieQuery;`);

// Existing name search is preserved.
assert.deepEqual(ChessGenieQuery.classify("Carlsen, Magnus"), {
  kind: "player",
  player: "Carlsen, Magnus"
});
assert.deepEqual(ChessGenieQuery.classify("  Carlsen, Magnus  "), {
  kind: "player",
  player: "Carlsen, Magnus"
});
assert.equal(ChessGenieQuery.classify("Carlsen").kind, "player");

// Valid numeric FIDE IDs.
assert.deepEqual(ChessGenieQuery.classify("1503014"), { kind: "fideId", fideId: "1503014" });
assert.deepEqual(ChessGenieQuery.classify(" 1503014 "), { kind: "fideId", fideId: "1503014" });
assert.deepEqual(ChessGenieQuery.classify("001503014"), { kind: "fideId", fideId: "1503014" });
assert.deepEqual(ChessGenieQuery.classify("7"), { kind: "fideId", fideId: "7" });
assert.deepEqual(ChessGenieQuery.classify("123456789012"), {
  kind: "fideId",
  fideId: "123456789012"
});

// Invalid or oversized IDs.
assert.deepEqual(ChessGenieQuery.classify("1234567890123"), { kind: "invalid", reason: "fideId" });
assert.deepEqual(ChessGenieQuery.classify("0"), { kind: "invalid", reason: "fideId" });
assert.deepEqual(ChessGenieQuery.classify("0000"), { kind: "invalid", reason: "fideId" });
assert.deepEqual(ChessGenieQuery.classify("x".repeat(201)), { kind: "invalid", reason: "player" });

// Anything that is not purely ASCII digits is a name, never an ID.
for (const value of ["1503014a", "150 3014", "1.503.014", "-1503014", "+1503014", "١٥٠٣", "１５０３", "1e7"]) {
  assert.equal(ChessGenieQuery.classify(value).kind, "player", value);
}

// Empty input.
for (const value of ["", "   ", "\t\n", undefined, null, 1503014]) {
  assert.deepEqual(ChessGenieQuery.classify(value), { kind: "empty" });
}

// Messages cover both names and FIDE IDs.
const fideQuery = ChessGenieQuery.classify("1503014");
const nameQuery = ChessGenieQuery.classify("Carlsen, Magnus");
assert.equal(ChessGenieQuery.validationMessage({ kind: "empty" }), "Enter a player name or FIDE ID.");
assert.match(ChessGenieQuery.validationMessage({ kind: "invalid", reason: "fideId" }), /FIDE ID.*12 digits/);
assert.match(ChessGenieQuery.validationMessage({ kind: "invalid", reason: "player" }), /player name.*200/);
assert.match(ChessGenieQuery.searchingMessage(fideQuery), /FIDE ID.*longer than a name search/);
assert.equal(ChessGenieQuery.searchingMessage(nameQuery), "Searching the local database…");
assert.equal(ChessGenieQuery.notFoundMessage(fideQuery), "No games were found for FIDE ID 1503014.");
assert.equal(ChessGenieQuery.notFoundMessage(nameQuery), "No matching player name was found.");
assert.equal(ChessGenieQuery.label(fideQuery), "FIDE ID 1503014");
assert.equal(ChessGenieQuery.label(nameQuery), "Carlsen, Magnus");

// The popup wires the classifier to both native commands.
assert.match(popupHtml, /<script src="query\.js"><\/script>\s*<script src="popup\.js"><\/script>/);
assert.match(popupHtml, /placeholder="Surname, Given name or FIDE ID"/);

// Title.
assert.match(popupHtml, /<title>Lumbras &amp; Chess Genie<\/title>/);
assert.match(popupHtml, /<h1>Lumbras &amp; Chess Genie<\/h1>/);
assert.equal(manifest.name, "Lumbras & Chess Genie");
assert.match(popupJs, /ChessGenieQuery\.classify\(/);
assert.match(popupJs, /"searchFideId",\s*\{\s*fideId: query\.fideId/);
assert.match(popupJs, /"searchPlayer",\s*\{\s*player: query\.player/);
assert.match(serviceWorker, /"searchFideId"/);
assert.match(serviceWorker, /"searchPlayer"/);

// The classified query is kept in state, and a search is never re-issued from
// the resolved player name, so a FIDE-ID search never becomes a name search.
assert.match(popupJs, /state\.query = query/);
assert.doesNotMatch(popupJs, /runSearch\(state\.player/);
assert.doesNotMatch(popupJs, /runSearch\(elements\.player/);

// Filling the table reuses the known game numbers instead of repeating the
// search, so it costs the same for a name and a FIDE ID.
assert.match(popupJs, /nativeRequest\("getGames", \{ gameNumbers: batch \}\)/);
assert.match(serviceWorker, /"getGames"/);
assert.doesNotMatch(popupJs, /runSearch\([^)]*,\s*true\)/);

// Download PGN and Copy PGN load the whole result set before exporting.
const exportHandlers = popupJs.match(
  /elements\.(downloadPgn|copyPgn)\.addEventListener\("click"[\s\S]*?collectSelectedPgn\(\)/g
);
assert.equal(exportHandlers.length, 2);
for (const handler of exportHandlers) {
  assert.match(handler, /await loadGamesUntil\(state\.resultNumbers\.length\)/);
}

// PGN export is untouched by the search mode.
assert.match(popupJs, /nativeRequest\("getPgn", \{ gameNumbers: requestBatch \}\)/);

// Export covers every match, not just the rendered page: it draws from the
// helper's full result set and falls back to loaded rows only if absent.
assert.match(popupJs, /state\.resultNumbers = response\.gameNumbers \?\? \[\]/);
assert.match(popupJs, /function exportableNumbers\(\)/);
assert.match(popupJs, /let pending = exportableNumbers\(\)\.filter\(/);
assert.match(popupJs, /state\.selected = new Set\(exportableNumbers\(\)\)/);
assert.doesNotMatch(popupJs, /let pending = state\.games\s*\n?\s*\.filter/);

console.log("Name and FIDE-ID query handling verified.");
