// humanizer-ru: браузерный факт-замок, общий для сайта (audit.js) и
// Chrome-расширения (extension/vendor/facts.js, копию кладёт
// scripts/build_extension.py). Без DOM: только извлечение фактов и разница
// «было и стало». Экспорт: globalThis.humanizerFacts = { extractFacts, factsDiff }.
(function () {
  "use strict";
  // --- Факт-замок в браузере ---------------------------------------------------
  // Упрощённый порт humanizer_metrics/facts.py без морфологии: числа, ссылки,
  // месяцы, имена с заглавной не в начале предложения, латиница с заглавной,
  // крупные числительные словами и кванторы-утверждения («единственный»,
  // «впервые»). Сравниваются множества: что пропало и что появилось.
  const URL_RE = /https?:\/\/[^\s)>\]»]+|\b[a-z0-9-]+\.(?:ru|com|org|net|io|tech|dev|ai|su|рф)(?:\/[^\s)>\]»]*)?/gi;
  const CODE_RE = /`([^`\n]+)`/g;
  const MONTH_RE = /\b(январ|феврал|март|апрел|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-яё]*\b/gi;
  const TOKEN_RE = /[A-Za-z][A-Za-z\d-]*|[А-Яа-яЁё][А-Яа-яЁё-]*|\d[\d.,:/-]*/g;
  const CLAIM_PHRASE_RE = /\bдо сих пор\b|\bв мире\b|\bв россии\b/gi;
  const HARD_NUMERALS = new Set(["четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", "одиннадцать", "двенадцать", "пятнадцать", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто", "сто", "двести", "триста", "тысяча", "миллион", "миллиард", "десяток", "сотня", "дюжина"]);
  // Кванторы ловятся по основе с любым окончанием: «первые», «единственная»,
  // «крупнейшим». Полные формы наречий и местоимений перечислены целиком.
  const CLAIM_RE = /^(?:перв(?:ый|ая|ое|ые|ым|ой|ых|ыми|ому|ую|ого)|единственн[а-я]+|впервые|сам(?:ый|ая|ое|ые|ым|ой|ых|ыми|ому|ую|ого)|рекордн[а-я]+|крупнейш[а-я]+|старейш[а-я]+|никогда|никто|навсегда|беспрецедентн[а-я]+)$/;
  const stem = (w) => w.toLowerCase().replace(/ё/g, "е").replace(/-+$/, "").slice(0, 5);
  function sentenceStarts(text) {
    const starts = new Set([0]);
    for (const m of text.matchAll(/[.!?…]\s+|«|\n/g)) starts.add(m.index + m[0].length);
    // Начало строки после маркера списка («-», «1.», «2)»), «>», «#», «**» и
    // эмодзи-буллета: «- Говорить» не имя. Как LINE_LEAD_RE в facts.py.
    for (const m of text.matchAll(/^[ \t]*(?:(?:\d{1,3}[.)]|[^\p{L}\p{N}_\s«"'(\[])[ \t]*)*/gmu)) starts.add(m.index + m[0].length);
    return starts;
  }
  function extractFacts(text) {
    const hard = new Map(), claims = new Map(); // ключ → как показать
    for (const m of text.matchAll(URL_RE)) {
      const url = m[0].replace(/^https?:\/\/(?:www\.)?/, "").replace(/[.,;:]+$/, "").toLowerCase().replace(/\/+$/, "");
      hard.set("ссылка:" + url, url);
    }
    for (const m of text.matchAll(CODE_RE)) hard.set("код:" + m[1].trim(), "`" + m[1].trim() + "`");
    const body = text.replace(CODE_RE, " ").replace(URL_RE, " ");
    for (const m of body.matchAll(MONTH_RE)) hard.set("месяц:" + m[1].toLowerCase(), m[0]);
    for (const m of body.matchAll(CLAIM_PHRASE_RE)) claims.set("утверждение:" + m[0].toLowerCase().replace(/ё/g, "е"), m[0]);
    // Числа целиком, с единицами («1,5» не равно «15», проценты не равны
    // процентным пунктам): humanizerNumericFacts из scan.js, как в facts.py.
    const numeric = globalThis.humanizerNumericFacts;
    if (numeric) for (const [key, value] of numeric(body)) hard.set(key, value);
    const starts = sentenceStarts(body);
    for (const m of body.matchAll(TOKEN_RE)) {
      const tok = m[0], at = m.index;
      if (/^\d/.test(tok)) {
        if (numeric) continue;
        const n = tok.replace(/[.,:/-]+$/, "").replace(/,/g, ".");
        if (n) hard.set("число:" + n, tok.replace(/[.,:/-]+$/, ""));
        continue;
      }
      const low = tok.toLowerCase().replace(/ё/g, "е");
      if (HARD_NUMERALS.has(low)) { hard.set("число:" + low, tok); continue; }
      if (CLAIM_RE.test(low)) { claims.set("утверждение:" + stem(low), tok); continue; }
      if (!/^[A-ZА-ЯЁ]/.test(tok)) continue;
      if (/^[A-Za-z]/.test(tok)) { hard.set("имя:" + low, tok); continue; }
      if (!starts.has(at)) hard.set("имя:" + stem(low), tok);
    }
    return { hard, claims };
  }
  // Цитаты от трёх слов сверяются целиком, как _quotes в facts.py.
  function quotes(text) {
    const result = new Set();
    const body = text.replace(/^[ \t]{0,3}(?:`{3,}|~{3,})[^]*?^[ \t]{0,3}(?:`{3,}|~{3,})[ \t]*$/gm, "").replace(CODE_RE, " ");
    for (const m of body.matchAll(/«([^«»\n]+)»|„([^„“\n]+)“|“([^“”\n]+)”|"([^"\n]+)"/g)) {
      const q = (m[1] || m[2] || m[3] || m[4]).replace(/[*_]/g, "").toLowerCase().replace(/ё/g, "е").trim().replace(/\s+/g, " ").replace(/[.,;:!?…]+$/, "");
      if (q.split(" ").length >= 3) result.add(q);
    }
    return result;
  }
  // Перестановка чисел, как number_swaps в facts.py. Морфологии нет, поэтому
  // опора числа это основы всех слов его части, глаголы тоже: обмен, где вместе
  // с числом переехал глагол («выручка упала на 2%»), здесь не виден.
  const UNIT_STEMS = new Set(["рубль", "рубле", "рубля", "руб", "долла", "евро", "проце", "млн", "млрд", "тыс", "тысяч", "милли", "челов", "штук", "штука", "штуки"]);
  function numberAnchors(text) {
    const numeric = globalThis.humanizerNumericFacts;
    const seen = new Map(), alone = new Map();
    if (!numeric) return alone;
    const lead = /^[ \t]*(?:(?:\d{1,3}[.)]|[^\p{L}\p{N}_\s«"'(\[])[ \t]*)*/gmu;
    const body = text.replace(lead, "").replace(URL_RE, " ").replace(CODE_RE, " ");
    for (const part of body.split(/,(?!\d)|:(?!\d)|;|\n|[.!?…]+(?=\s|$)|\s(?:и|а|но)\s/i)) {
      const numbers = [...numeric(part)].map(([k]) => k).filter((k) => k.startsWith("число:")).map((k) => k.slice(6));
      for (const n of numbers) seen.set(n, (seen.get(n) || 0) + 1);
      if (numbers.length !== 1) continue;
      const anchors = new Set();
      for (const m of part.matchAll(TOKEN_RE)) {
        if (/^\d/.test(m[0]) || m[0].length < 3) continue;
        const s = stem(m[0]);
        if (!UNIT_STEMS.has(s)) anchors.add(s);
      }
      alone.set(numbers[0], anchors);
    }
    for (const n of [...alone.keys()]) if (seen.get(n) !== 1) alone.delete(n);
    return alone;
  }
  function numberSwaps(before, after) {
    const a = numberAnchors(before), b = numberAnchors(after);
    const common = [...a.keys()].filter((n) => b.has(n)).sort();
    const moved = new Map();
    for (const x of common) {
      for (const y of common) {
        if (x === y) continue;
        const own = [...a.get(x)].filter((w) => !a.get(y).has(w));
        const other = [...a.get(y)].filter((w) => !a.get(x).has(w));
        if (own.length && !own.some((w) => b.get(x).has(w)) && other.some((w) => b.get(x).has(w))) {
          moved.set(x, y);
          break;
        }
      }
    }
    const pairs = new Set();
    for (const [x, y] of moved) if (moved.has(y)) pairs.add([x, y].sort().join(" и "));
    return [...pairs].sort();
  }
  function factsDiff(before, after) {
    const a = extractFacts(before), b = extractFacts(after);
    const qa = quotes(before), qb = quotes(after);
    const lost = [...a.hard].filter(([k]) => !b.hard.has(k)).map(([, v]) => v)
      .concat([...qa].filter((q) => !qb.has(q)).map((q) => `цитата «${q}»`));
    const added = [...b.hard].filter(([k]) => !a.hard.has(k)).map(([, v]) => v);
    const claimsAdded = [...b.claims].filter(([k]) => !a.claims.has(k)).map(([, v]) => v)
      .concat([...qb].filter((q) => !qa.has(q)).map((q) => `цитата «${q}»`));
    const kept = [...a.hard].filter(([k]) => b.hard.has(k)).length;
    return { lost, added, claimsAdded, swapped: numberSwaps(before, after), kept, total: a.hard.size };
  }

  globalThis.humanizerFacts = { extractFacts, factsDiff };
})();
