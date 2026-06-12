# Источники и верификация

Этот файл — честная провенанс-таблица. Скилл про детекцию AI-текста обязан сам не
галлюцинировать ссылки (паттерн #35 в SKILL.md прямо это запрещает). Поэтому каждое
академическое утверждение, которое раньше жило inline в `SKILL.md`, проверено по
arxiv.org и первоисточникам. Непроверяемые точные числа и неверные атрибуции из
рабочего промпта удалены; здесь остаётся то, что подтвердилось, с корректными ID.

Дата верификации: 2026-06. Метод: прямой поиск каждого ID на arxiv, сверка
заявленной темы и чисел с абстрактом.

## Подтверждено (используем уверенно)

| Источник | ID | Что подтверждено |
|---|---|---|
| How Well Do LLMs Imitate Human Writing Style? | 2509.24930 | perplexity gap: человек 29.5 vs LLM 15.2 при 99.9% style match |
| Why AI-Generated Text Detection Fails | 2603.23146 | domain shift, детекторы не обобщаются между доменами |
| LLMs Exhibit Lower Uncertainty in Creative Writing | 2602.16162 | uncertainty gap, человеческий текст менее предсказуем |
| Human-LLM Coevolution | 2502.09606 | эволюция маркеров, «delve» упал после 2024 |
| DependencyAI | 2602.15514 | детекция по dependency-парсингу (Texas A&M) |
| ChatGPT-generated texts show authorship traits | 2508.16385 | номинальный стиль ChatGPT, перекос в существительные |
| Linguistic Characteristics of AI Text: Survey | 2510.05136 | больше номинализаций у AI |
| Fine-Grained Detection (Sentence-Level) | 2509.17830 | sentence-level детекторы |
| DAMAGE | 2501.03437 | детектируемость «гуманизированного» стиля |
| Towards Understanding Sycophancy | 2310.13548 | sycophancy |
| Epistemic Integrity in LLMs | 2411.06528 | чрезмерная уверенность, epistemic miscalibration |
| Sign of the Times (idiomaticity) | 2405.09279 | LLM хуже на идиоматике |
| Revisiting UID Hypothesis in LLM Reasoning | 2510.06953 | Uniform Information Density |
| Detecting Stylistic Fingerprints of LLMs | 2503.01659 | отпечатки моделей, precision 0.9988 |
| Catch Me If You Can? Not Yet | 2509.14543 | 40K+ генераций, 400+ авторов, провал на blogs/forums |
| How LLMs Distort Our Written Language | 2603.18161 | гомогенизация, ~+70% нейтральных эссе |
| Overview of PAN 2026 | 2602.09147 | Reasoning Trajectory Detection |
| DivEye | 2509.18880 | вторые производные surprisal = 39.4% вклада (ID исправлен) |
| Adversarial Paraphrasing (NeurIPS 2025) | 2506.07001 | TPR детекторов падает на 87.88% |
| PIFE | 2510.02319 | сохраняет 82.6% TPR под адверсарными атаками |
| AINL-Eval 2025 | 2508.09622 | 52 305 текстов, 12 доменов, лучший результат 86.35% |
| RuATD-2022 | 2206.01583 | 14 генераторов (1 human + 13 моделей) |
| Antislop | 2510.15061 | паттерны в 1000+ раз чаще, 8000+ паттернов (ICLR 2026) |
| MASH | 2601.08564 | 92% ASR через style humanization |

## Исправлено (атрибуция/ID были неверны)

| Было в SKILL.md | Проблема | Корректно |
|---|---|---|
| DivEye без ID / неверный ID | ID не указан/неверен | 2509.18880 |
| AINL-Eval «RuRoBERTa 86.35%» | 86.35% — лучший результат shared task, не обязательно RuRoBERTa | 2508.09622, модель не атрибутируем |
| strengtheners vs hedges → 2507.10587 | 2507.10587 про verbalized uncertainty в целом | нужная цитата — 2401.06730 «Relying on the Unreliable» |

## Удалено из рабочего промпта (не подтвердилось)

| Утверждение | Вердикт |
|---|---|
| `2502.11806` Biber framework, noun/verb 3:1 | НЕВЕРНАЯ АТРИБУЦИЯ — статья про механизмы перевода. Сам факт noun/verb ~3:1 у AI vs ~2:1 у людей — расхожая эвристика, оставлена в скилле БЕЗ ложной ссылки |
| `CoPA +57.7% улучшения детекции` | CoPA — это АТАКА на детекторы (EMNLP 2025), а не метод улучшения. Цифра +57.7% не подтверждена. Принцип контрастного вычитания оставлен как операционная эвристика без ложной атрибуции |
| `PNAS 2025: мат в 100 раз реже` | Публикация PNAS не найдена. Вероятная галлюцинация. Сам факт (AI реже использует мат/негатив) оставлен качественно |
| `2507.15357 F1=30.4 MIPVU vs RoBERTa 77-79` | Статья есть, но цифры не совпадают (LLM реально 87-95% с CoT). Числа удалены, тезис «LLM хуже с метафорами» оставлен |
| `2603.08450` translationese в русском | Статья про шведский перевод. Удалена. Тезис translationese оставлен качественно |
| `2505.01800` «AI больше радости» | Статья говорит обратное: AI «flat, emotionally uniform». Формулировка исправлена на «эмоционально ровный» |
| `2601.11529` narrative drift | НЕВЕРНАЯ АТРИБУЦИЯ — это фреймворк генерации нарратива. Тезис narrative drift оставлен качественно |
| `2411.02316` лексическая перегрузка в нарративах | Статья про creativity metrics, перегрузку явно не утверждает. Ссылка удалена |
| `2604.04932`, `2510.26124` RST Contrast/Concession | ЧАСТИЧНО: RST используют, но Contrast/Concession не фокус. Ссылки удалены, тезис про дискурсивные связи оставлен качественно |

## Принцип

В рабочем промпте (`SKILL.md`) больше нет inline arxiv-ID и точных процентов: они не
меняют поведение модели, зато при ошибке бьют по кредибилити проекта. Все
операционные правила (контрастное вычитание, burstiness, noun/verb, бан тире,
морфология) верны независимо от цитат и сохранены. Численные доказательства и
ссылки живут здесь и в README, где их можно перепроверить.

## Артефакты копипасты (категория сканера, v3.7)

Каждый маркер категории «Артефакты копипасты» проверен по первоисточнику 12.06.2026:

| Маркер | Первоисточник |
|---|---|
| `:contentReference`, `oaicite:N`, `oai_citation`, `attached_file`, `grok_card`, `turnNsearchN`, `attribution`/`attributableIndex`, `utm_source=` | [enwiki «Signs of AI writing»](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) §6.3-6.5, §7.6 |
| `filecite`/`turnNfileN` (file_search, GPT-5.x) | [Форум разработчиков OpenAI](https://community.openai.com/t/unexpected-citation-markers-appearing-in-text-output-when-using-file-search/1362380) (подтверждено OpenAI Support) |
| `【N†source】`, `【N:M†файл】` | [Доки OpenAI Assistants file search](https://platform.openai.com/docs/assistants/tools/file-search) + [баг-тред про сырые метки](https://community.openai.com/t/citation-format-differs-in-gpt-4-1-mini-file-search-annotations-missing-replaced-with-raw-references/1290591) |
| Невидимые U+E200-E204 | [Разбор приватных управляющих символов в экспортах OpenAI](https://github.com/sanand0/openai-conversations/blob/main/private-unicode-control-characters.md) |
| `](sandbox:/mnt/data/...)` | [OpenAI community: нерабочие download-ссылки](https://community.openai.com/t/error-report-download-link-not-working-for-generated-files-in-chatgpt-code-interpreter/1220959), [Make community](https://community.make.com/t/how-can-i-download-a-file-from-a-sandbox-mnt-data-url-generated-by-chatgpt/77162) |
| `</think>` (DeepSeek R1 и наследники) | [Доки DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode), [Trend Micro про утечки CoT](https://www.trendmicro.com/en_us/research/25/c/exploiting-deepseek-r1.html), [aider#3008](https://github.com/Aider-AI/aider/issues/3008) |
| `[citation:N]` (Perplexity-стиль) | [Perplexity docs: streaming citations](https://docs.perplexity.ai/docs/cookbook/articles/streaming-citations/README) + интеграционные обсуждения (LibreChat#4692) |
| `vertexaisearch.cloud.google.com/grounding-api-redirect` | [Доки Google Gemini: Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search) |

Не прошло верификацию и НЕ включено: копайлот-сноски `[^N^]` — формат не подтверждён
документацией Microsoft (Copilot документирует `[1]`), а FP-риск к Markdown-сноскам высокий.
