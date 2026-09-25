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
    const starts = sentenceStarts(body);
    for (const m of body.matchAll(TOKEN_RE)) {
      const tok = m[0], at = m.index;
      if (/^\d/.test(tok)) {
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
  function factsDiff(before, after) {
    const a = extractFacts(before), b = extractFacts(after);
    const lost = [...a.hard].filter(([k]) => !b.hard.has(k)).map(([, v]) => v);
    const added = [...b.hard].filter(([k]) => !a.hard.has(k)).map(([, v]) => v);
    const claimsAdded = [...b.claims].filter(([k]) => !a.claims.has(k)).map(([, v]) => v);
    const kept = [...a.hard].filter(([k]) => b.hard.has(k)).length;
    return { lost, added, claimsAdded, kept, total: a.hard.size };
  }

  globalThis.humanizerFacts = { extractFacts, factsDiff };
})();
