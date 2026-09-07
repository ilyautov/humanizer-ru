#!/usr/bin/env node
// Запуск браузерного сканера из Node для теста паритета с scan.py.
// Использование: node scripts/web_scan_cli.mjs [--genre g] файл1 файл2 ... -> JSON-массив отчётов.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const docs = join(here, "..", "docs");
// Оба файла из этого репозитория пишут в globalThis; исполняем их как в браузере.
for (const name of ["scan-rules.js", "scan.js"]) {
  vm.runInThisContext(readFileSync(join(docs, name), "utf8"), { filename: name });
}

const args = process.argv.slice(2);
let genre = null;
const files = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--genre") genre = args[++i];
  else files.push(args[i]);
}
const out = files.map((f) => {
  const text = f === "-" ? readFileSync(0, "utf8") : readFileSync(f, "utf8");
  const r = globalThis.humanizerScan(text, genre);
  return {
    file: f, score: r.score, band: r.band,
    hard_bans: r.hard_bans.map((h) => [h.name, h.count]),
    markers: r.markers.map((h) => [h.category, h.name, h.count]),
    rhythm: r.rhythm, structure: r.structure, penalties: r.penalties,
  };
});
process.stdout.write(JSON.stringify(out, null, 1));
