// humanizer-ru: браузерный сканер. Зеркало humanizer_metrics (Python) на
// правилах из scan-rules.js, которые экспортирует scripts/export_web_rules.py.
// Паритет с scan.py проверяет scripts/test_web_parity.py: баны и маркеры
// совпадают точно, score в допуске (в браузере нет морфологии pymorphy3 и
// razdel заменён простым делителем предложений).
//
// API: globalThis.humanizerScan(text, genre) -> отчёт (см. конец файла).

(function () {
  "use strict";
  const R = globalThis.HUMANIZER_RULES;
  if (!R) throw new Error("scan-rules.js должен быть подключён раньше scan.js");

  // --- Границы чужого текста: порт humanizer_metrics/markdown.py ------------
  const GAP = R.markdown.gap;
  const QUOTE_MAX_WORDS = R.markdown.quote_max_words;
  const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})(.*)$/;
  const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})\s*$/;
  const QUOTE_LINE = /^ {0,3}>/;
  const BLOCK_START = /^ {0,3}(?:#{1,6}\s|[-*+]\s|\d{1,9}[.)]\s|(?:-{3,}|\*{3,}|_{3,})\s*$|`{3,}|~{3,})/;
  const INLINE_CODE = /(`+)(?!`)([^`\n]+?)\1(?!`)/g;
  const QUOTE_MARKS = /«[^«»]*»/g;

  const blank = (s) => s.replace(/[^\n]/g, GAP);

  function fenceRanges(lines) {
    const ranges = [];
    let i = 0;
    while (i < lines.length) {
      const m = FENCE_OPEN.exec(lines[i]);
      if (!m || (m[1][0] === "`" && m[2].includes("`"))) { i += 1; continue; }
      const ch = m[1][0], need = m[1].length;
      let j = i + 1;
      while (j < lines.length) {
        const c = FENCE_CLOSE.exec(lines[j]);
        if (c && c[1][0] === ch && c[1].length >= need) break;
        j += 1;
      }
      if (j >= lines.length) { i += 1; continue; }
      ranges.push([i, j]);
      i = j + 1;
    }
    return ranges;
  }

  function classify(text) {
    const lines = text.split("\n");
    const inCode = new Set();
    for (const [a, b] of fenceRanges(lines)) for (let k = a; k <= b; k++) inCode.add(k);
    const quoted = new Set();
    let inside = false;
    lines.forEach((line, i) => {
      if (inCode.has(i)) { inside = false; return; }
      if (QUOTE_LINE.test(line)) { inside = true; quoted.add(i); }
      else if (inside && line.trim() && !BLOCK_START.test(line)) quoted.add(i);
      else inside = false;
    });
    return { lines, inCode, quoted };
  }

  function maskForeign(text) {
    const { lines, inCode, quoted } = classify(text);
    const out = lines.map((line, i) =>
      inCode.has(i) || quoted.has(i) ? blank(line) : line.replace(INLINE_CODE, (m) => blank(m)));
    return out.join("\n").replace(QUOTE_MARKS, (m) =>
      m.slice(1, -1).trim().split(/\s+/).filter(Boolean).length <= QUOTE_MAX_WORDS ? blank(m) : m);
  }

  function stripForeign(text) {
    const { lines, inCode, quoted } = classify(text);
    return lines.filter((_, i) => !inCode.has(i) && !quoted.has(i))
      .map((line) => line.replace(INLINE_CODE, "")).join("\n");
  }

  // --- Лексика: баны и маркеры -----------------------------------------------
  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const compiled = new Map();
  function rx(src, isLiteral, flags) {
    flags = flags || "giu";
    const key = (isLiteral ? "L:" : "R:") + flags + ":" + src;
    let r = compiled.get(key);
    if (!r) { r = new RegExp(isLiteral ? escapeRe(src) : src, flags); compiled.set(key, r); }
    r.lastIndex = 0;
    return r;
  }
  function findAll(text, src, isLiteral, flags) {
    const r = rx(src, isLiteral, flags), out = [];
    let m;
    while ((m = r.exec(text)) !== null) {
      out.push([m.index, m.index + Math.max(m[0].length, 1)]);
      if (m[0].length === 0) r.lastIndex += 1;
    }
    return out;
  }

  function scanHardBans(text) {
    const hits = [];
    for (const b of R.hard_bans) {
      const pos = findAll(text, b.re, false, b.flags);
      if (pos.length) hits.push({ category: "HARD BAN", name: b.name, count: pos.length, positions: pos });
    }
    return hits;
  }

  function scanMarkers(text) {
    const hits = [];
    for (const [cat, rows] of Object.entries(R.scanner)) {
      for (const row of rows) {
        const pos = row.lit !== undefined ? findAll(text, row.lit, true) : findAll(text, row.re, false, row.flags);
        if (pos.length) hits.push({ category: cat, name: row.label, count: pos.length, positions: pos });
      }
    }
    return hits;
  }

  function muteByGenre(hits, genre, muted) {
    const names = new Set(muted[genre || ""] || []);
    return hits.filter((h) => !names.has(h.name) && !names.has(h.category));
  }

  function effectiveHardBans(hits, words) {
    return hits.filter((h) => {
      const per = R.freq_bans[h.name];
      return !(per && (h.count < 2 || h.count <= words / per));
    });
  }

  // --- Ритм: делитель предложений вместо razdel ------------------------------
  // razdel режет по [.!?…] с учётом сокращений и инициалов; перевод строки сам
  // по себе границей не считается. Здесь то же правило в упрощённом виде.
  const ABBR = new Set(("т.е т.д т.п т.к т.н др пр см ср г гг в вв ул д стр рис табл им св руб коп тыс млн млрд " +
    "напр англ лат греч проф акад доц ст ч п пп гл изд ред сост пер кв корп обл р с сб вс пн вт чт пт").split(" "));
  const WORD_CHAR = /[\p{L}\p{N}]/u;

  function sentences(text) {
    const out = [];
    let start = 0;
    const re = /[.!?…]+["»)\]]*(?=\s|$)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      const end = m.index + m[0].length;
      const before = text.slice(start, m.index);
      const lastWord = (before.match(/[\p{L}\p{N}.]+$/u) || [""])[0].toLowerCase().replace(/\.+$/, "");
      const next = text.slice(end).match(/^\s*(\S)/);
      const nextCh = next ? next[1] : "";
      const onlyDots = /^\.+$/.test(m[0].replace(/["»)\]]/g, ""));
      const abbr = onlyDots && (ABBR.has(lastWord) || /^\p{Lu}$/u.test(before.slice(-1)) || /^\d+$/.test(lastWord) && /\p{Ll}/u.test(nextCh));
      const lowerNext = onlyDots && /\p{Ll}/u.test(nextCh);
      if (abbr || lowerNext) continue;
      const s = text.slice(start, end).trim();
      if (s) out.push(s);
      start = end;
    }
    const tail = text.slice(start).trim();
    if (tail) out.push(tail);
    return out;
  }

  function countWords(s) {
    return s.split(/\s+/).filter((t) => WORD_CHAR.test(t)).length
      + (s.match(/[\p{L}\p{N}]+(?=[:@/])/gu) || []).length * 0; // hello@x.ru считается одним словом
  }

  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const pstdev = (a) => { if (a.length < 2) return 0; const mu = mean(a); return Math.sqrt(mean(a.map((x) => (x - mu) ** 2))); };
  const round = (x, d) => { const k = 10 ** d; return Math.round(x * k) / k; };

  function rhythm(text) {
    const sents = sentences(text);
    const lengths = sents.map(countWords).filter((n) => n > 0);
    const mu = mean(lengths), sd = pstdev(lengths);
    return {
      sentences: lengths.length,
      words: lengths.reduce((x, y) => x + y, 0),
      mean_len: round(mu, 1),
      cv_len: round(mu ? sd / mu : 0, 3),
      min_len: lengths.length ? Math.min(...lengths) : 0,
      max_len: lengths.length ? Math.max(...lengths) : 0,
      em_dash: (text.match(/—/g) || []).length,
      questions: sents.filter((s) => s.trimEnd().endsWith("?")).length,
    };
  }

  const LIST_RE = /^\s*(?:[-*•]|\d+[.)])\s+\S/;
  function structureStats(text) {
    const paras = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    const lens = paras.map((p) => sentences(p).length).filter((n) => n > 0);
    const mu = mean(lens), sd = pstdev(lens);
    const lines = text.split("\n").filter((l) => l.trim());
    const items = lines.filter((l) => LIST_RE.test(l)).length;
    return {
      paragraphs: lens.length,
      para_cv: round(mu ? sd / mu : 0, 3),
      list_items: items,
      listicle_share: round(lines.length ? items / lines.length : 0, 3),
    };
  }

  // --- Score: порт score.cleanliness_score без пункта 6 (морфология) ---------
  const per100 = (count, words) => (words ? (count / words) * 100 : 0);
  const band = (s) => (s >= R.score.band_clean ? "чисто" : s >= R.score.band_edit ? "правка" : "рерайт");

  function cleanlinessScore(rep, genre) {
    const S = R.score;
    const words = rep.rhythm.words || 1;
    const markers = muteByGenre(rep.markers, genre, R.genre_muted_categories);
    const dashMuted = (R.genre_muted_bans[genre || ""] || []).includes(S.em_dash_name);
    const penalties = [], notes = [];
    let score = 100;

    const effBans = muteByGenre(effectiveHardBans(rep.hardBans, rep.rhythm.words), genre, R.genre_muted_bans);
    const hardPhrase = effBans.filter((h) => h.name !== S.em_dash_name).reduce((n, h) => n + h.count, 0);
    if (hardPhrase) { const pen = Math.min(45, 12 * hardPhrase); score -= pen; penalties.push({ reason: `хард-баны (фразы): ${hardPhrase}`, points: -pen }); }

    const copyPaste = markers.filter((h) => h.category === S.copy_paste_category).reduce((n, h) => n + h.count, 0);
    if (copyPaste) { score -= 60; penalties.push({ reason: `артефакты копипасты: ${copyPaste}`, points: -60 }); }

    const soft = markers.filter((h) => h.category !== S.copy_paste_category).reduce((n, h) => n + h.count, 0);
    if (soft) {
      const pen = Math.min(30, Math.round(2 * per100(soft, words)));
      if (pen) { score -= pen; penalties.push({ reason: `маркеры: ${soft} (${per100(soft, words).toFixed(1)}/100 слов)`, points: -pen }); }
    }

    const dashDensity = dashMuted ? 0 : per100(rep.rhythm.em_dash, words);
    if (dashDensity > 2) {
      const pen = Math.min(8, Math.round(3 * (dashDensity - 2)));
      if (pen) { score -= pen; penalties.push({ reason: `тире: ${rep.rhythm.em_dash} (${dashDensity.toFixed(1)}/100 слов)`, points: -pen }); }
    }

    const cv = rep.rhythm.cv_len;
    if (rep.rhythm.sentences >= 4 && cv < S.cv_human_target) {
      const pen = Math.min(20, Math.round(((S.cv_human_target - cv) / S.cv_human_target) * 30));
      if (pen) { score -= pen; penalties.push({ reason: `ровный ритм (CV=${cv}, цель ≥${S.cv_human_target})`, points: -pen }); }
    }

    const st = rep.structure;
    if (st.paragraphs >= S.para_min_count && st.para_cv < S.para_cv_ai) {
      const pen = Math.min(10, Math.round(((S.para_cv_ai - st.para_cv) / S.para_cv_ai) * 20));
      if (pen) { score -= pen; penalties.push({ reason: `ровные абзацы (CV=${st.para_cv}, цель ≥${S.para_cv_ai})`, points: -pen }); }
    }
    if (st.list_items >= S.listicle_min_items && st.listicle_share > S.listicle_share_ai) {
      const pen = Math.min(12, Math.round((st.listicle_share - S.listicle_share_ai) * 30));
      if (pen) { score -= pen; penalties.push({ reason: `листикл (${st.list_items} пунктов, ${Math.floor(st.listicle_share * 100)}% строк)`, points: -pen }); }
    }

    if (!(hardPhrase || copyPaste || soft) && words >= S.sterile_min_words) {
      const row = S.human_zero_share.find(([limit]) => words < limit) || S.human_zero_share[S.human_zero_share.length - 1];
      const share = Math.round(row[1]);
      notes.push(`стерильно: ни одного маркера. Так пишет ${share}% людей на тексте в ${words} слов, остальные ${100 - share}% что-нибудь да используют. Цель не ноль, а типичная для жанра частота: вычищать дальше незачем`);
    }

    const final = Math.max(0, Math.min(100, Math.round(score)));
    return { score: final, band: band(final), penalties, notes, effectiveBans: effBans, mutedMarkers: markers };
  }

  function humanizerScan(text, genre) {
    genre = genre || null;
    const lexical = maskForeign(text);
    const prose = stripForeign(text);
    const rh = rhythm(prose);
    rh.em_dash = (lexical.match(/—/g) || []).length;
    const rep = { hardBans: scanHardBans(lexical), markers: scanMarkers(lexical), rhythm: rh, structure: structureStats(prose) };
    const sc = cleanlinessScore(rep, genre);
    return {
      score: sc.score, band: sc.band, penalties: sc.penalties, notes: sc.notes,
      hard_bans: rep.hardBans, effective_bans: sc.effectiveBans, markers: rep.markers, muted_markers: sc.mutedMarkers,
      rhythm: rh, structure: rep.structure, words: rh.words, genre,
    };
  }

  globalThis.humanizerScan = humanizerScan;
  globalThis.humanizerScanInternals = { maskForeign, stripForeign, sentences, countWords };
})();
