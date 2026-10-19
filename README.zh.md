# humanizer-ru

> [Русская версия: основная и полная](README.md) · [English](README.en.md)

面向 Claude Code、Cursor、Codex、Gemini CLI 等智能体的开源 Skill：编辑俄语文本，去掉机器腔、公文体和模板套话，同时不改变事实和作者的声音。MIT 许可，无订阅，无 API Key，在你已经在用的智能体里直接运行。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.32.0-blueviolet)](CHANGELOG.md)
[![Stars](https://img.shields.io/github/stars/ilyautov/humanizer-ru?style=social)](https://github.com/ilyautov/humanizer-ru/stargazers)
[![skills.sh](https://skills.sh/b/ilyautov/humanizer-ru)](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru)

🧪 **在线试用，无需安装：** [humanizer-ru.aifrontier.tech](https://humanizer-ru.aifrontier.tech/#audit)。粘贴一段俄语，得到 0 到 100 的「干净度」评分和被标出的套话。扫描器在浏览器里运行，文本不会上传。

## 核心原则：删除，不要补写

这个 Skill 做的是局部编辑，不是整篇重写。它标出具体位置（引文、为什么妨碍读者、该怎么处理），删掉空洞的开场和包装在论断外面的套话，把绕口的名词链改回动词，然后逐条核对改后的文本与原文。

- 只用原文里已有的词。不为了「生动」而添加原文没有的事实、数字、情绪、语气词或比喻。
- 事实锁：`--before` 会比较改写前后的文本，列出凭空出现或丢失的数字、日期、人名、链接和断言。编造的数据比任何套话都糟糕。
- 不改变作者的声音：给几段你自己写的俄语，Skill 会把改动限制在你的节奏和用词之内。
- 其他场景同样适用：商品详情、官网和新闻稿的俄语版、机器翻译后的润色、邮件和报告。

## 为什么俄语需要单独的工具

大模型常常「经由英语」生成俄语，破绽也和英语不同：英语句法的直译（калька）、一句一个「является」、堆叠的名词链公文体（канцелярит）、丢失的语气小词「же」「ведь」「вот」、满篇的长破折号。通用的英语工具看不到这些，中文的「去 AI 味」工具也不处理俄语。

目录收录了 **67 个俄语 AI 特征**（分 16 类）和 **21 条硬性禁用结构**，每一条都写成编辑规则，而不是简单的词表。

## 扫描器

Skill 自带一个确定性的扫描器 `scripts/scan.py`，把修改变成可度量的事：「原来 N 分，现在 M 分」。

- 0 到 100 的干净度评分，按类别列出命中，句长节奏、名词动词比、Markdown 感知（代码块和引用不计入）。
- 体裁模式 `--genre academic|legal|fiction|news`：在学术、法律、文学、新闻文本里，某些结构是正常的，开启后不再当作问题。
- 评分是修改的依据，不是「这是 AI 写的」的裁决，也不判定作者身份。

```
python3 skills/humanizer-ru/scripts/scan.py текст.txt
python3 skills/humanizer-ru/scripts/scan.py текст.txt --genre academic
python3 skills/humanizer-ru/scripts/scan.py после.txt --before до.txt
```

需要 `razdel` 和 `pymorphy3`。在 macOS（Homebrew）和 Debian/Ubuntu 上，直接 `pip install` 会因 PEP 668 报 `externally-managed-environment`，请改用下面任意一种：

```
uvx ru-humanizer текст.txt          # 无需安装，需要 uv
pipx install ru-humanizer           # 命令 ru-humanizer 进入 PATH
python3 -m venv ~/.humanizer-ru && ~/.humanizer-ru/bin/pip install razdel pymorphy3
```

## 一分钟安装

任何智能体一条命令（Claude Code、Cursor、Codex、Copilot、Cline 等几十种）：

```
npx skills add ilyautov/humanizer-ru
```

Claude Code 也可以作为插件安装，之后通过 `/plugin` 更新：

```
/plugin marketplace add ilyautov/humanizer-ru
/plugin install humanizer-ru@ilyautov-plugins
```

Gemini CLI：

```
gemini extensions install https://github.com/ilyautov/humanizer-ru
```

DeepSeek Harness：

```
dsh plugin --profile web add humanizer-ru
```

Claude.ai 网页版：下载 [humanizer-ru.zip](https://github.com/ilyautov/humanizer-ru/releases/latest/download/humanizer-ru.zip)，在 Settings → Capabilities → Skills 里上传。Codex CLI、组织部署、其他智能体、独立扫描器（pip、MCP 服务器、GitHub Action）见[俄语 README](README.md#установка)。

## 怎么用

装好之后，对智能体说（俄语或中文都可以，但文本本身必须是俄语）：

- 「очеловечь этот текст」或「把这段俄语编辑得自然一点」：局部编辑，保留原文事实。
- 「проверь текст на следы нейросети」或「检查这段俄语的 AI 痕迹」：只做审计，列出发现的问题，不改写。
- 「убери канцелярит」：只处理指定的一类问题。

在 Claude Code 里装了插件后还有斜杠命令：`/humanize <文本或文件路径>`（局部编辑）和 `/audit <文本或文件路径>`（只审计）。

## 数据校准

规则不是凭感觉定的。目录在三个公开语料上校准过，合计 35 158 + 5 759 + 14 763 = 55 680 篇带人机标注的俄语文本（约 5.6 万），包括 GigaChat 和 YandexGPT 的输出。校准脚本和报告在 `eval/` 目录，语料是公开的，数字可以复现：[AINL](eval/AINL-CALIBRATION.md)、[M4](eval/M4-CALIBRATION.md)、[LLMTrace](eval/LLMTRACE-CALIBRATION.md)。

## 它不做什么

- 不是「绕过 AI 检测器」的工具。不插入错别字，不用拉丁字母替换西里尔字母。为了通过检测而损坏文本，是在欺骗读者。目标只有一个：写出俄罗斯人真的会写的文本。
- 不编造细节。原文没有数字和案例，Skill 就不补，需要的话会向你要材料。
- 不判定作者身份。

## 链接

- 源码：[github.com/ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru)
- 网站与在线扫描：[humanizer-ru.aifrontier.tech](https://humanizer-ru.aifrontier.tech/)
- 更新日志：[CHANGELOG.md](CHANGELOG.md)
- 引用的研究来源：[SOURCES.md](SOURCES.md)
- 完整文档（FAQ、对比、校准细节）：[README.md](README.md)

作者：Ilya Utov（[GitHub](https://github.com/ilyautov)）。欢迎 issue 和 PR，包括中文的。
