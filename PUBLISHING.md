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

Порядок, после того как пакет появился на PyPI:

1. Поставить издателя: `brew install mcp-publisher`, либо бинарник со страницы
   релизов https://github.com/modelcontextprotocol/registry/releases.
2. Из корня репозитория: `mcp-publisher login github` (откроется браузер,
   войти в аккаунт ilyautov: пространство имён `io.github.ilyautov/*`
   выдаётся владельцу этого логина).
3. `mcp-publisher publish`. Издатель берёт `server.json`, сверяет версию с PyPI
   и строку `mcp-name` в README пакета.
4. Проверка: `curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=humanizer-ru"`.

На каждый следующий релиз `scripts/bump_release.py --apply vX.Y.Z` двигает
версию в `pyproject.toml` и `server.json`; после публикации на PyPI повторить
`mcp-publisher publish`.

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
