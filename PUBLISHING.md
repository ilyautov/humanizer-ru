# Публикация носителей: PyPI и реестр MCP

Оба шага делаются один раз руками владельца репозитория, дальше всё идёт
по релизу само. Папка `dist/` в git не живёт, поэтому инструкция лежит здесь.

## PyPI: пакет `ru-humanizer`

Workflow `.github/workflows/publish-pypi.yml` собирает пакет на каждый
опубликованный GitHub Release и выкладывает через Trusted Publishing: токен в
секретах не нужен, PyPI доверяет OIDC-подписи GitHub Actions.

Разовая настройка, до первого релиза после слияния:

1. Войти на https://pypi.org (аккаунт с включённой двухфакторной защитой).
2. Your account → **Publishing** → **Add a new pending publisher**.
3. Заполнить ровно так:
   - PyPI project name: `ru-humanizer`
   - Owner: `ilyautov`
   - Repository name: `humanizer-ru`
   - Workflow name: `publish-pypi.yml`
   - Environment name: оставить пустым
4. Сохранить. Проект появится на PyPI при первой успешной публикации.

Проверка после релиза: https://pypi.org/project/ru-humanizer/ отдаёт версию тега,
`pip install ru-humanizer && ru-humanizer -` читает текст из stdin. Если релиз
вышел до настройки, workflow запускается руками: Actions → Publish to PyPI →
Run workflow → тег.

Имя `humanizer-ru` на PyPI занято одноимённым проектом Vladimir-Human, поэтому
пакет называется `ru-humanizer`; команды внутри называются `ru-humanizer` и
`ru-humanizer-mcp`.

## Реестр MCP: `io.github.ilyautov/humanizer-ru`

Официальный реестр https://registry.modelcontextprotocol.io читает `server.json`
из корня репозитория и проверяет, что пакет на PyPI принадлежит нам: в README
пакета (`README.pypi.md`) стоит строка `mcp-name: io.github.ilyautov/humanizer-ru`.

**Руками тут делать нечего.** Workflow `.github/workflows/publish-registry.yml`
идёт по тому же событию, что и публикация на PyPI: ждёт, пока PyPI отдаст версию
тега, входит в реестр по OIDC-подписи GitHub Actions и публикует карточку.
Пространство имён `io.github.ilyautov/*` выдаётся владельцу репозитория, поэтому
ни логина в браузере, ни токена в секретах не нужно. Так устроены и девять
остальных наших серверов.

Проверка после релиза:
`curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=humanizer-ru"`.
В выдаче несколько версий, текущая та, у которой
`_meta["io.modelcontextprotocol.registry/official"].isLatest` равно `true`.

На каждый следующий релиз `scripts/bump_release.py --apply vX.Y.Z` двигает версию
сразу в `pyproject.toml` и `server.json`, иначе workflow остановится на сверке
версий и ничего не опубликует.

Запасной путь, если реестр отвалится: поставить издателя
(`brew install mcp-publisher`), из корня репозитория `mcp-publisher login github`
и `mcp-publisher publish`.

## Подключение сервера у клиентов

Claude Desktop, Cursor, Claude Code и другие клиенты MCP:

```json
{
  "mcpServers": {
    "humanizer-ru": {
      "command": "uvx",
      "args": ["--from", "ru-humanizer", "ru-humanizer-mcp"]
    }
  }
}
```

В Claude Code то же одной командой:

```bash
claude mcp add humanizer-ru -- uvx --from ru-humanizer ru-humanizer-mcp
```

Без uv: `pip install ru-humanizer`, затем `"command": "ru-humanizer-mcp"` без
аргументов.
