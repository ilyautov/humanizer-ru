// humanizer-ru: браузерный сканер. Зеркало humanizer_metrics (Python) на
// правилах из scan-rules.js, которые экспортирует scripts/export_web_rules.py.
// Паритет с scan.py проверяет scripts/test_web_parity.py: баны, маркеры и
// полоса вердикта совпадают точно, score в допуске. Расхождение у счёта одно и
// известное: без pymorphy3 браузер не считает штраф за номинальность (до −8),
// поэтому его счёт может быть ВЫШЕ питоновского. Этот пропуск объявляется в
// отчёте (поле unmeasured), а не замалчивается. razdel (делитель предложений
// и счёт слов) перенесён в JS правило в правило, ритм совпадает точно.
// Лексическое разнообразие (MATTR) и повтор фраз между абзацами от razdel не
// зависят и совпадают с Python точно: MATTR до бита, фразы дословно.
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

  // --- Ритм: порт razdel 0.5 (sentenize + tokenize) -------------------------
  // Не упрощение, а перенос правил razdel/segmenters/sentenize.py и tokenize.py
  // один к одному: упрощённый делитель расходился с движком на свежих текстах
  // моделей (аббревиатура «НДФЛ.» как инициал, пункт «2.» отдельным
  // предложением, URL в markdown-ссылке одним словом, «князь? — спросила»
  // разрезано, «рабочий/учебный» и «Уважаемый(ая)» одним словом). Окно в 10
  // символов, сокращения и порядок правил как у razdel; срезы по кодовым
  // точкам, как в Python. Перевод строки сам по себе границей не считается.
  const RZ_ENDINGS = ".?!…", RZ_DASHES = "‑–—−-";
  const RZ_CLOSE_QUOTES = "»”’", RZ_GENERIC_QUOTES = "\"„'";
  const RZ_QUOTES = "«“‘" + RZ_CLOSE_QUOTES + RZ_GENERIC_QUOTES;
  const RZ_CLOSE_BRACKETS = ")]}";
  const RZ_DELIMITERS = RZ_ENDINGS + ";" + RZ_GENERIC_QUOTES + RZ_CLOSE_QUOTES + RZ_CLOSE_BRACKETS;
  const rzSet = (s) => new Set(s.split(" "));
  // razdel/segmenters/sokr.py; пара сокращений записана как «т|е».
  const RZ_HEAD_SOKRS = rzSet("букв ст трад лат венг исп кат укр нем англ фр итал греч евр араб яп слав кит " +
    "рус русск латв словацк хорв mr mrs ms dr vs св арх зав зам проф акад кн корр ред гр ср чл им тов нач пол " +
    "chap п пп ч чч гл стр абз пт no просп пр ул ш г гор д к корп пер обл эт пом ауд оф ком комн каб " +
    "домовлад лит т рп пос с х пл bd о оз р а обр ум ок откр пс ps upd см напр доп юр физ тел сб внутр дифф гос отм");
  const RZ_SOKRS = rzSet("дес тыс млн млрд дол долл коп руб р проц га барр куб кв км см час мин сек в вв г гг с стр " +
    "co corp inc изд ed др al сокр рис искл прим яз устар шутл");
  for (const w of RZ_HEAD_SOKRS) RZ_SOKRS.add(w);
  const RZ_HEAD_PAIR_SOKRS = rzSet("т|е т|к т|н и|о к|н к|п п|н к|т л|д");
  const RZ_PAIR_SOKRS = rzSet("т|п т|д у|е н|э p|m a|m с|г р|х с|ш з|д л|с ч|т ед|ч мн|ч повел|накл");
  for (const p of RZ_HEAD_PAIR_SOKRS) RZ_PAIR_SOKRS.add(p);
  const RZ_INITIALS = rzSet("дж ed вс");
  // Классы Python re: \w = буква, цифра или «_»; \d = десятичная цифра.
  const RZ_TOK = "([\\p{L}\\p{Nl}\\p{No}_]+|\\p{Nd}+|[^\\p{L}\\p{N}_\\s])";
  const RZ_TOKEN = new RegExp(RZ_TOK, "gu");
  const RZ_FIRST_TOKEN = new RegExp("^\\s*" + RZ_TOK, "u");
  const RZ_LAST_TOKEN = new RegExp(RZ_TOK + "\\s*$", "u");
  const RZ_WORD = /([\p{L}\p{Nl}\p{No}_]+|\p{Nd}+)/u;
  const RZ_PAIR_SOKR = /([\p{L}\p{N}_])\s*\.\s*([\p{L}\p{N}_])\s*$/u;
  const RZ_SMILE_PREFIX = /^\s*[=:;]-?[)(]{1,3}/u;
  const isAlpha = (t) => /^\p{L}+$/u.test(t);
  // str.isdigit(): десятичные цифры плюс надстрочные, подстрочные и в кружках («²», «①»).
  const isDigit = (t) => /^[\p{Nd}²³¹፩-፱᧚⁰⁴-⁹₀-₉①-⑨⑴-⑼⒈-⒐⓪⓵-⓽⓿❶-❾➀-➈➊-➒\u{10A40}-\u{10A43}\u{10E60}-\u{10E68}\u{11052}-\u{1105A}\u{1F100}-\u{1F10A}]+$/u.test(t);
  const isLower = (t) => t !== t.toUpperCase() && t === t.toLowerCase();
  const isUpper = (t) => t !== t.toLowerCase() && t === t.toUpperCase();
  const isLowerAlpha = (t) => isAlpha(t) && isLower(t);
  const isSokr = (t) => isDigit(t) || !isAlpha(t) || isLower(t);
  const isBullet = (t) => isDigit(t) || ".)".includes(t) || "§абвгдеabcdef".includes(t.toLowerCase()) || /^[IVXML]+$/.test(t);
  const closeBound = (sp) => (RZ_ENDINGS.includes(sp.leftToken) ? undefined : true);

  // Правила в порядке razdel: true склеивает, undefined передаёт следующему;
  // если никто не склеил, здесь граница предложения.
  const RZ_RULES = [
    (sp) => (!sp.leftToken || !sp.rightToken ? true : undefined),             // empty_side
    (sp) => (/^\s/u.test(sp.right) ? undefined : true),                        // no_space_prefix
    (sp) => (isLowerAlpha(sp.rightToken) ? true : undefined),                  // lower_right
    (sp) => {                                                                  // delimiter_right
      if (RZ_GENERIC_QUOTES.includes(sp.rightToken)) return undefined;
      return RZ_DELIMITERS.includes(sp.rightToken) || RZ_SMILE_PREFIX.test(sp.right) ? true : undefined;
    },
    (sp) => {                                                                  // sokr_left
      if (sp.delimiter !== ".") return undefined;
      const m = sp.left.match(RZ_PAIR_SOKR);
      if (m) {
        const pair = m[1].toLowerCase() + "|" + m[2].toLowerCase();
        if (RZ_HEAD_PAIR_SOKRS.has(pair)) return true;
        if (RZ_PAIR_SOKRS.has(pair)) return isSokr(sp.rightToken) ? true : undefined;
      }
      const left = sp.leftToken.toLowerCase();
      return RZ_HEAD_SOKRS.has(left) || (RZ_SOKRS.has(left) && isSokr(sp.rightToken)) ? true : undefined;
    },
    (sp) => (sp.delimiter === "." &&                                           // inside_pair_sokr
      RZ_PAIR_SOKRS.has(sp.leftToken.toLowerCase() + "|" + sp.rightToken.toLowerCase()) ? true : undefined),
    (sp) => {                                                                  // initials_left
      if (sp.delimiter !== ".") return undefined;
      // Инициал = одна заглавная буква («А.»), аббревиатура «НДФЛ.» им не считается.
      const t = sp.leftToken;
      return (isUpper(t) && Array.from(t).length === 1) || RZ_INITIALS.has(t.toLowerCase()) ? true : undefined;
    },
    (sp) => {                                                                  // list_item: «2.», «8.1.», «б)»
      if (!".)".includes(sp.delimiter) || Array.from(sp.buffer).length > 20) return undefined;
      return (sp.buffer.match(RZ_TOKEN) || []).every(isBullet) ? true : undefined;
    },
    (sp) => {                                                                  // close_quote
      if (!RZ_QUOTES.includes(sp.delimiter)) return undefined;
      if (RZ_CLOSE_QUOTES.includes(sp.delimiter)) return closeBound(sp);
      if (RZ_GENERIC_QUOTES.includes(sp.delimiter)) return /\s$/u.test(sp.left) ? true : closeBound(sp);
      return undefined;
    },
    (sp) => (RZ_CLOSE_BRACKETS.includes(sp.delimiter) ? closeBound(sp) : undefined), // close_bracket
    (sp) => {                                                                  // dash_right: «князь? — спросила»
      if (!RZ_DASHES.includes(sp.rightToken)) return undefined;
      const w = sp.right.match(RZ_WORD);
      return w && isLowerAlpha(w[1]) ? true : undefined;
    },
  ];

  function sentences(text) {
    const cps = Array.from(text);
    const cut = (a, b) => cps.slice(Math.max(0, a), b).join("");
    const out = [];
    let buffer = null, prev = 0, sp = null;
    const step = (right) => {                    // Segmenter.segment из razdel/segmenters/base.py
      if (buffer === null) { buffer = right; return; }
      sp.buffer = buffer;
      if (RZ_RULES.some((rule) => rule(sp))) buffer += sp.delimiter + right;
      else { out.push(buffer + sp.delimiter); buffer = right; }
    };
    for (let i = 0; i < cps.length;) {
      let len = 0;
      if ("=:;".includes(cps[i])) {              // смайл «:-)» тоже разделитель
        const j = cps[i + 1] === "-" ? i + 2 : i + 1;
        let k = 0;
        while (k < 3 && (cps[j + k] === ")" || cps[j + k] === "(")) k++;
        if (k) len = j + k - i;
      }
      if (!len && RZ_DELIMITERS.includes(cps[i])) len = 1;
      if (!len) { i++; continue; }
      step(cut(prev, i));
      sp = { left: cut(i - 10, i), delimiter: cut(i, i + len), right: cut(i + len, i + len + 10) };
      const ft = sp.right.match(RZ_FIRST_TOKEN), lt = sp.left.match(RZ_LAST_TOKEN);
      sp.rightToken = ft ? ft[1] : null;
      sp.leftToken = lt ? lt[1] : null;
      prev = i += len;
    }
    step(cut(prev, cps.length));
    out.push(buffer);
    return out.map((s) => s.trim());
  }

  // Слова по razdel.tokenize: атомы RU/LAT/INT/PUNCT/OTHER без пробела между
  // ними склеиваются по правилам дефиса, «_», дробей и чисел; словом считается
  // токен с кириллицей, латиницей или цифрой (burstiness._word_count). Поэтому
  // «рабочий/учебный» это два слова, «IT-хаба» одно, URL несколько.
  const RZ_PUNCTS = "\\/!#$%&*+,.:;<=>?@^_`|~№…" + RZ_DASHES + RZ_QUOTES + "([}" + RZ_CLOSE_BRACKETS;
  const RZ_ATOM = /([а-яё]+)|([a-z]+)|(\p{Nd}+)|(\S)/giu;
  const RZ_SMILE = /^[=:;]-?[)(]{1,3}$/u;
  const WORD_CHAR = /[А-Яа-яЁёA-Za-z0-9]/;
  const atomType = (m) => (m[1] ? "RU" : m[2] ? "LAT" : m[3] ? "INT" : RZ_PUNCTS.includes(m[4]) ? "PUNCT" : "OTHER");
  function rzJoin(atoms, k, buffer) {             // правила tokenize.py на стыке атомов k-1 | k
    const L1 = atoms[k - 1], L2 = atoms[k - 2], R1 = atoms[k], R2 = atoms[k + 1];
    const rule2112 = (isDelim, ok) => {
      let l, r;
      if (isDelim(L1.text)) [l, r] = [L2, R1];
      else if (isDelim(R1.text)) [l, r] = [L1, R2];
      else return false;
      return Boolean(l && r && ok(l, r));
    };
    const noPunct = (l, r) => l.type !== "PUNCT" && r.type !== "PUNCT";
    const ints = (l, r) => l.type === "INT" && r.type === "INT";
    if (rule2112((d) => RZ_DASHES.includes(d), noPunct)) return true;        // dash
    if (rule2112((d) => d === "_", noPunct)) return true;                     // underscore
    if (rule2112((d) => ".,".includes(d), ints)) return true;                 // float
    if (rule2112((d) => "/\\".includes(d), ints)) return true;                // fraction
    if (L1.type === "PUNCT" && R1.type === "PUNCT") {                         // punct
      if (RZ_SMILE.test(buffer + R1.text)) return true;
      if (RZ_ENDINGS.includes(L1.text) && RZ_ENDINGS.includes(R1.text)) return true;
      if (["--", "**"].includes(L1.text + R1.text)) return true;
    }
    const word = (t) => t === "OTHER" || t === "RU" || t === "LAT";           // other
    if (L1.type === "OTHER" && word(R1.type)) return true;
    if (word(L1.type) && R1.type === "OTHER") return true;
    return L1.text.toLowerCase() === "yahoo" && R1.text === "!";              // yahoo
  }

  function countWords(s) {
    const atoms = [...s.matchAll(RZ_ATOM)].map((m) => ({ text: m[0], type: atomType(m), start: m.index }));
    let words = 0, buffer = "";
    atoms.forEach((a, k) => {
      const glued = k > 0 && atoms[k - 1].start + atoms[k - 1].text.length === a.start;
      if (glued && rzJoin(atoms, k, buffer)) { buffer += a.text; return; }
      if (WORD_CHAR.test(buffer)) words++;
      buffer = a.text;
    });
    return words + (WORD_CHAR.test(buffer) ? 1 : 0);
  }

  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const pstdev = (a) => { if (a.length < 2) return 0; const mu = mean(a); return Math.sqrt(mean(a.map((x) => (x - mu) ** 2))); };
  // Как round() в Python: точная половина (13.25 при d=1) к чётному, иначе по
  // точному двоичному значению (toFixed), без ошибки умножения на 10^d.
  const round = (x, d) => {
    const k = 10 ** d, y = x * k;
    if (Math.abs(y % 1) === 0.5 && y / k === x) { const f = Math.floor(y); return (f % 2 ? f + 1 : f) / k; }
    return Number(x.toFixed(d));
  };

  // Рваная медитативность (каталог #49): цепочка из 3+ утверждений по 1-3 слова
  // подряд в одной строке. Реплики диалога, восклицания, вопросы, подводки с
  // двоеточием, пункты списков и заголовки не считаются. Порт burstiness.staccato_runs.
  const DIALOG_RE = /^\s*[-–—«"']/;
  const SKIP_LINE_RE = /^\s*(?:(?:[-*•]|\d+[.)])\s+|#)/;
  function staccatoRuns(text) {
    const S = R.score, runs = [];
    for (const line of text.replace(/\\/g, "").split("\n")) {
      if (!line.trim() || SKIP_LINE_RE.test(line)) continue;
      let cur = 0;
      for (const s of sentences(line)) {
        const st = s.trim(), n = countWords(st);
        if (!n) continue;
        if (n <= S.staccato_max_words && !DIALOG_RE.test(st) && !"?!:;".includes(st[st.length - 1])) cur += 1;
        else { if (cur >= S.staccato_min_run) runs.push(cur); cur = 0; }
      }
      if (cur >= S.staccato_min_run) runs.push(cur);
    }
    return [runs.length, runs.length ? Math.max(...runs) : 0];
  }

  function rhythm(text) {
    const sents = sentences(text);
    const lengths = sents.map(countWords).filter((n) => n > 0);
    const mu = mean(lengths), sd = pstdev(lengths);
    const [staccatoCount, staccatoMax] = staccatoRuns(text);
    return {
      sentences: lengths.length,
      words: lengths.reduce((x, y) => x + y, 0),
      mean_len: round(mu, 1),
      cv_len: round(mu ? sd / mu : 0, 3),
      min_len: lengths.length ? Math.min(...lengths) : 0,
      max_len: lengths.length ? Math.max(...lengths) : 0,
      em_dash: (text.match(/—/g) || []).length,
      questions: sents.filter((s) => s.trimEnd().endsWith("?")).length,
      staccato_runs: staccatoCount,
      staccato_max: staccatoMax,
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

  // --- Лексическое разнообразие: порт humanizer_metrics/lexical.py ----------
  // Токенизация обязана совпасть с Python байт в байт: нижний регистр, ё → е,
  // слово это кириллица с внутренними дефисами. Паритет MATTR проверяется
  // точным равенством (scripts/test_web_parity.py).
  const LEX_TOKEN = /[а-яё]+(?:-[а-яё]+)*/g;
  function lexicalTokens(text) {
    return (text.toLowerCase().match(LEX_TOKEN) || []).map((t) => t.replace(/ё/g, "е"));
  }
  // MATTR: среднее по окнам доли разных словоформ. Сумма копится в целых и
  // делится один раз, как в Python, поэтому число совпадает до бита.
  function mattr(tokens, window) {
    const n = tokens.length;
    if (n < window) return 0;
    const counts = new Map();
    for (const t of tokens.slice(0, window)) counts.set(t, (counts.get(t) || 0) + 1);
    let distinct = counts.size, total = distinct;
    for (let i = window; i < n; i++) {
      const nw = tokens[i], old = tokens[i - window];
      const c = (counts.get(nw) || 0) + 1;
      counts.set(nw, c);
      if (c === 1) distinct += 1;
      const o = counts.get(old) - 1;
      counts.set(old, o);
      if (o === 0) distinct -= 1;
      total += distinct;
    }
    return total / ((n - window + 1) * window);
  }
  function lexicalStats(text) {
    const toks = lexicalTokens(text);
    return { tokens: toks.length, mattr: mattr(toks.slice(0, R.score.lex_max_tokens), R.score.lex_window) };
  }

  // --- Повтор фразы между абзацами: порт humanizer_metrics/repeats.py -------
  // Абзац это непустая строка, заголовки Markdown и цитаты в кавычках не
  // считаются, латиница, цифры и знаки конца предложения рвут цепочку. Список
  // фраз обязан совпасть с Python дословно (scripts/test_web_parity.py). В счёт
  // признак не входит, это заметка для правки.
  const RP = R.repeats;
  const RP_FUNCTION = new Set(RP.function_words);
  const RP_TOKEN = /[а-яё]+(?:-[а-яё]+)*|[a-z0-9]+|[.!?…;:()[\]"«»“”„]/g;
  const RP_QUOTE = /«[^«»\n]*»|„[^„“\n]*“|"[^"\n]*"/g;
  const RP_HEADING = /^[ \t]*#{1,6}[ \t]/;
  function repeatRuns(line) {
    const runs = [];
    let cur = [];
    for (const tok of line.toLowerCase().match(RP_TOKEN) || []) {
      if ((tok[0] >= "а" && tok[0] <= "я") || tok[0] === "ё") cur.push(tok.replace(/ё/g, "е"));
      else { if (cur.length) runs.push(cur); cur = []; }
    }
    if (cur.length) runs.push(cur);
    return runs;
  }
  function repeatStats(text) {
    const n = RP.n;
    let budget = RP.max_tokens, pos = 0;
    const where = new Map(), order = [];
    const lines = text.replace(RP_QUOTE, " . ").split("\n");
    for (let li = 0; li < lines.length && budget > 0; li++) {
      if (RP_HEADING.test(lines[li])) continue;
      for (let run of repeatRuns(lines[li])) {
        run = run.slice(0, budget);
        budget -= run.length;
        for (let i = 0; i + n <= run.length; i++) {
          const words = run.slice(i, i + n), key = words.join(" ");
          if (!where.has(key)) where.set(key, new Set());
          where.get(key).add(li);
          order.push([li, pos + i, words]);
        }
        pos += run.length + 1;
        if (budget <= 0) break;
      }
    }
    const repeated = (words) => where.get(words.join(" ")).size >= 2 &&
      words.filter((w) => !RP_FUNCTION.has(w)).length >= RP.min_content;
    const phrases = [], keys = new Set();
    let cur = [], curKey = "", prev = [-1, -2];
    for (const [li, p, words] of order) {
      if (!repeated(words)) continue;
      if (prev[0] === li && prev[1] === p - 1 && cur.length) cur.push(words[words.length - 1]);
      else {
        if (cur.length && !keys.has(curKey)) { keys.add(curKey); phrases.push(cur.join(" ")); }
        cur = words.slice(); curKey = words.join(" ");
      }
      prev = [li, p];
    }
    if (cur.length && !keys.has(curKey)) phrases.push(cur.join(" "));
    return { tokens: RP.max_tokens - Math.max(budget, 0), phrases };
  }

  // --- Score: порт score.cleanliness_score без пункта 6 (морфология) ---------
  const per100 = (count, words) => (words ? (count / words) * 100 : 0);
  const plural = (n, one, few, many) =>
    n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? few : many;
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

    const distinctCats = [S.signature_category, S.chat_wrap_category];
    const soft = markers.filter((h) => h.category !== S.copy_paste_category && !distinctCats.includes(h.category))
      .reduce((n, h) => n + h.count, 0);
    if (soft) {
      const pen = Math.min(30, Math.round(2 * per100(soft, words)));
      if (pen) { score -= pen; penalties.push({ reason: `маркеры: ${soft} (${per100(soft, words).toFixed(1)}/100 слов)`, points: -pen }); }
    }

    // Почерк модели и обвязка чата: по числу разных оборотов, не по плотности.
    const distinct = (cat) => new Set(markers.filter((h) => h.category === cat).map((h) => h.name)).size;
    const sig = distinct(S.signature_category);
    if (sig) {
      const pen = Math.min(S.signature_max, S.signature_first + S.signature_next * (sig - 1));
      score -= pen;
      penalties.push({ reason: `почерк модели: ${sig} ${plural(sig, "оборот", "оборота", "оборотов")}`, points: -pen });
    }
    const wrap = distinct(S.chat_wrap_category);
    if (wrap) {
      const pen = Math.min(S.chat_wrap_max, S.chat_wrap_each * wrap);
      score -= pen;
      penalties.push({ reason: `обвязка чата: ${wrap} ${plural(wrap, "след", "следа", "следов")}`, points: -pen });
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

    const runs = rep.rhythm.staccato_runs;
    if (runs) {
      const pen = Math.min(S.staccato_penalty_max, S.staccato_penalty * runs);
      const word = plural(runs, "цепочка", "цепочки", "цепочек");
      score -= pen;
      penalties.push({ reason: `рваная медитативность: ${runs} ${word} обрывков по ${S.staccato_min_run}+ подряд (самая длинная ${rep.rhythm.staccato_max})`, points: -pen });
    }

    // Лексическое разнообразие: floor, а не round, чтобы целое совпало с Python.
    const lex = rep.lexical;
    if (!S.lex_muted_genres.includes(genre) && lex.tokens >= S.lex_min_tokens && lex.mattr > S.lex_threshold) {
      const pen = Math.min(S.lex_penalty_max, Math.floor((lex.mattr - S.lex_threshold) * S.lex_slope));
      if (pen) { score -= pen; penalties.push({ reason: `лексическое разнообразие (MATTR=${lex.mattr.toFixed(3)}, порог ${S.lex_threshold})`, points: -pen }); }
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

    if (!(hardPhrase || copyPaste || soft || sig || wrap) && words >= S.sterile_min_words) {
      const row = S.human_zero_share.find(([limit]) => words < limit) || S.human_zero_share[S.human_zero_share.length - 1];
      const share = Math.round(row[1]);
      notes.push(`стерильно: ни одного маркера. Так пишет ${share}% людей на тексте в ${words} слов, остальные ${100 - share}% что-нибудь да используют. Цель не ноль, а типичная для жанра частота: вычищать дальше незачем`);
    }

    // Повтор фраз между абзацами: заметка без штрафа, как в score.py.
    const phrases = rep.repeats.phrases;
    if (phrases.length >= R.repeats.min_phrases) {
      const show = R.repeats.show;
      const shown = phrases.slice(0, show).map((p) => `«${p}»`).join(", ");
      const more = phrases.length > show ? ` и ещё ${phrases.length - show}` : "";
      notes.push(`повтор фраз между абзацами: ${shown}${more}. В счёт не входит: у людей так бывает в новостях и справках. Если повтор не нарочный, оставьте фразу в одном месте`);
    }

    // Чего браузер не измерил. Морфологии здесь нет, значит нет и штрафа за
    // номинальность (сущ./глаг., до −8 в scan.py). Молча выдавать более высокий
    // счёт нельзя: пусть читатель видит границу измерения.
    const unmeasured = [{
      name: "номинальность (сущ./глаг.)",
      max_points: S.nv_max_penalty,
      why: "в браузере нет морфологического разбора",
    }];

    const final = Math.max(0, Math.min(100, Math.round(score)));
    return { score: final, band: band(final), penalties, notes, unmeasured, effectiveBans: effBans, mutedMarkers: markers };
  }

  function humanizerScan(text, genre) {
    genre = genre || null;
    const lexical = maskForeign(text);
    const prose = stripForeign(text);
    const rh = rhythm(prose);
    rh.em_dash = (lexical.match(/—/g) || []).length;
    const rep = { hardBans: scanHardBans(lexical), markers: scanMarkers(lexical), rhythm: rh, structure: structureStats(prose), lexical: lexicalStats(prose), repeats: repeatStats(prose) };
    const sc = cleanlinessScore(rep, genre);
    return {
      score: sc.score, band: sc.band, penalties: sc.penalties, notes: sc.notes,
      unmeasured: sc.unmeasured,
      hard_bans: rep.hardBans, effective_bans: sc.effectiveBans, markers: rep.markers, muted_markers: sc.mutedMarkers,
      rhythm: rh, structure: rep.structure, lexical: rep.lexical, repeats: rep.repeats, words: rh.words, genre,
    };
  }

  globalThis.humanizerScan = humanizerScan;
  globalThis.humanizerScanInternals = { maskForeign, stripForeign, sentences, countWords, lexicalTokens, mattr, repeatStats };
})();
