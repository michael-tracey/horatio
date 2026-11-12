// Run after `vite build` (#706): fails the build if d3, which only staff's charts
// use, has reached the app's first chunk, index.html, or the service worker's
// offline cache. The Play View has to open with no signal and nothing extra.
// Prints the sizes, so a pull request can say what a change cost.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const dist = join(import.meta.dirname, "..", "dist");
const manifest = JSON.parse(readFileSync(join(dist, ".vite", "manifest.json"), "utf8"));
const isD3 = (file) => /(^|\/)d3-[^/]*\.js$/.test(file);

const failures = [];
const entry = manifest["index.html"];
if (!entry) failures.push("dist/.vite/manifest.json has no index.html entry");

// Everything the first page load fetches: the entry and its static imports, all the way down.
const first = new Set();
const visit = (key) => {
  const chunk = manifest[key];
  if (!chunk || first.has(chunk.file)) return;
  first.add(chunk.file);
  for (const next of chunk.imports ?? []) visit(next);
};
if (entry) visit("index.html");
for (const file of first) if (isD3(file)) failures.push(`the first page load imports ${file}`);

const d3Files = [...new Set(Object.values(manifest).map((c) => c.file))].filter(isD3);
const html = readFileSync(join(dist, "index.html"), "utf8");
const sw = readFileSync(join(dist, "sw.js"), "utf8");
for (const file of d3Files) {
  const name = file.split("/").pop();
  if (html.includes(name)) failures.push(`index.html loads ${file}`);
  if (sw.includes(name)) failures.push(`the service worker keeps ${file} for offline use`);
}

const kb = (bytes) => `${(bytes / 1000).toFixed(2)} kB`;
const size = (file) => {
  const body = readFileSync(join(dist, file));
  return `${kb(body.length)} (gzip ${kb(gzipSync(body).length)})`;
};
if (entry) console.log(`first chunk: ${entry.file} ${size(entry.file)}`);
for (const file of d3Files) console.log(`d3 chunk:    ${file} ${size(file)}`);

if (failures.length) {
  console.error(`\nd3 must load only with the pages that draw charts:\n- ${failures.join("\n- ")}`);
  process.exit(1);
}
console.log(d3Files.length ? "d3 stays out of the first load and the offline cache." : "No d3 chunk in this build.");
