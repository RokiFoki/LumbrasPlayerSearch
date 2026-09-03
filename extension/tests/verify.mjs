import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(fs.readFileSync(path.join(directory, "manifest.json"), "utf8"));
const popupHtml = fs.readFileSync(path.join(directory, "popup.html"), "utf8");
const popupJs = fs.readFileSync(path.join(directory, "popup.js"), "utf8");
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

const runtimeSource = `${popupHtml}\n${popupJs}\n${serviceWorker}`.toLowerCase();
assert.equal(runtimeSource.includes("chessgenie.app"), false);
assert.equal(runtimeSource.includes("content script"), false);

console.log("Extension manifest and source-agnostic boundary verified.");
