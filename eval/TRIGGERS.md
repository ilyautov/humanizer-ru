# Trigger-eval humanizer-ru

Автогенерируемый отчёт (`eval/run_triggers.py`). Проверяет НЕ качество очеловечивания (это `RESULTS.md`), а **границу активации**: должен ли скилл срабатывать на запросе. Лёгкий детерминированный слой без LLM — guard scope-фраз в описании из `SKILL.md` + модальность запроса (русский / английский / код). Полное решение «по смыслу» в бою принимает сам ассистент по описанию; здесь страхуем поверхностную границу.

## Guard описания (scope-граница)

✓ Scope-фразы на месте (`ТОЛЬКО русский`, `Для английского — оригинальный humanizer`, `НЕ используй для: код`). Граница активации в описании цела.

## Сводка

- Кейсов: **18** (should-trigger **10**, near-miss **8**).
- Точность гейта: **100%** (18/18); ложных срабатываний **0**, пропусков триггера **0**.

> **Ложное срабатывание** (near-miss принят за триггер) — опасное направление для «pushy» описания: скилл полез бы в код или английский. Это жёсткий гейт CI. Пропуск триггера — мягкое предупреждение (провал только с `--strict`).

## Кейсы

| id | категория | ждём | модальность | вердикт |
|---|---|---|---|---|
| `trig_ochelovech_01` | explicit_request | trigger | ru | trigger ✓ |
| `trig_sledy_neyroseti_02` | explicit_request | trigger | ru | trigger ✓ |
| `trig_zhivoy_estestvenny_03` | explicit_request | trigger | ru | trigger ✓ |
| `trig_kak_chelovek_04` | explicit_request | trigger | ru | trigger ✓ |
| `trig_humanize_ru_05` | explicit_request | trigger | ru | trigger ✓ |
| `trig_kancelyarit_06` | explicit_request | trigger | ru | trigger ✓ |
| `trig_vodyanistost_formal_07` | explicit_request | trigger | ru | trigger ✓ |
| `trig_paste_perepishi_08` | paste_vague | trigger | ru | trigger ✓ |
| `trig_paste_robot_09` | paste_vague | trigger | ru | trigger ✓ |
| `trig_sdelay_luchshe_10` | paste_vague | trigger | ru | trigger ✓ |
| `near_code_refactor_py_01` | code | no-trigger | code | no-trigger ✓ |
| `near_code_explain_js_02` | code | no-trigger | code | no-trigger ✓ |
| `near_code_bug_py_03` | code | no-trigger | code | no-trigger ✓ |
| `near_code_sql_04` | code | no-trigger | code | no-trigger ✓ |
| `near_en_humanize_01` | english | no-trigger | en | no-trigger ✓ |
| `near_en_rewrite_02` | english | no-trigger | en | no-trigger ✓ |
| `near_en_remove_tells_03` | english | no-trigger | en | no-trigger ✓ |
| `near_en_robotic_04` | english | no-trigger | en | no-trigger ✓ |

## Near-miss по категориям (скилл НЕ должен лезть)

| категория | кейсов | гейт держит |
|---|---|---|
| code | 4 | 4/4 |
| english | 4 | 4/4 |

---

Слой детерминированный: без ключей, сети и LLM — гоняется в CI. Проверяет ту часть решения о вызове, что видна на поверхности (язык и модальность), и что scope-граница в описании цела. Описание берётся живьём из `SKILL.md`.
