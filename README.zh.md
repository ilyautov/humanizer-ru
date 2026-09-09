# humanizer-ru

> [Русская версия: основная](README.md) · [English](README.en.md)

面向 Claude Code、Cursor、Codex、Gemini CLI 等编程智能体的开源 Skill：去除俄语文本中的 AI 痕迹，让机器生成的俄语读起来像俄罗斯人写的。MIT 许可，无订阅，无 API Key，在你已经在用的智能体里直接运行。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ilyautov/humanizer-ru?style=social)](https://github.com/ilyautov/humanizer-ru/stargazers)
[![skills.sh](https://skills.sh/b/ilyautov/humanizer-ru)](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru)

🧪 **在线试用，无需安装：** [humanizer-ru.aifrontier.tech](https://humanizer-ru.aifrontier.tech/#audit)。粘贴一段俄语，得到 0 到 100 的「干净度」评分和被标出的 AI 套话。扫描器在浏览器里运行，文本不会上传。

## 给谁用

- 跨境电商团队：Ozon、Wildberries、Yandex Market、速卖通俄区的商品详情、店铺公告、客服回复。用 DeepSeek、豆包、GPT 生成的俄语文案，俄罗斯买家一眼就看出是机器写的，转化和评分都会受影响。
- 出海企业的市场和公关：官网、新闻稿、宣传册、社媒帖子的俄语版本。
- 本地化和翻译团队：机器翻译或 LLM 初稿之后的润色，让文本符合俄语母语者的阅读习惯。
- 用俄语写邮件、报告、论文的任何人。

## 为什么俄语需要单独的工具

所有大模型都是「经由英语」生成俄语的。于是俄语 AI 文本的破绽和英语的不一样：英语式句法的直译（калька）、一句一个「является」、堆叠的名词链公文体（канцелярит）、丢失的语气小词「же」「ведь」「вот」、每隔一句一个长破折号。英语的 humanizer 看不到这些，中文的「去 AI 味」工具也不处理俄语。

这个 Skill 收录了 **64 个俄语 AI 特征**（分 14 类）和 **21 条硬性禁用结构**，每一条都写成编辑规则，而不是简单的词表。附带一个确定性的扫描器，把修改变成可度量的事：「原来 9 分，现在 82 分」。

## 一分钟安装

任何智能体一条命令（Claude Code、Cursor、Codex、Copilot、Cline 等几十种）：

```
npx skills add ilyautov/humanizer-ru
```

CLI 会检测本机已安装的智能体并询问装到哪里。Claude Code 也可以作为插件安装，之后通过 `/plugin` 更新：

```
/plugin marketplace add ilyautov/humanizer-ru
/plugin install humanizer-ru@ilyautov-plugins
```

DeepSeek Harness：

```
dsh plugin --profile web add humanizer-ru
```

Claude.ai 网页版：下载 [humanizer-ru.zip](https://github.com/ilyautov/humanizer-ru/releases/latest/download/humanizer-ru.zip)，在 Settings → Capabilities → Skills 里上传。其他安装方式见[俄语 README](README.md#установка)。

## 怎么用

装好之后，对智能体说（俄语或中文都可以，但文本本身必须是俄语）：

- 「очеловечь этот текст」或「把这段俄语改得像人写的」：完整改写，五步流程，保留原文事实。
- 「проверь текст на следы нейросети」或「检查这段俄语的 AI 痕迹」：只做审计，列出发现的特征和优先级，不改写。
- 「убери канцелярит」：只处理指定的一类问题。

也可以在命令行直接跑扫描器（需要 Python 3 和 `pip install razdel pymorphy3`）：

```
python3 skills/humanizer-ru/scripts/scan.py текст.txt
python3 skills/humanizer-ru/scripts/scan.py после.txt --before до.txt
```

第二条命令是「事实锁」：比较改写前后的文本，列出凭空出现或丢失的数字、日期、人名、链接和断言。编造的数据比任何套话都糟糕。

## 里面有什么

- 64 个特征、14 个类别：公文体、英语直译、情感空洞、说服套路、信息节奏、模糊限定词，以及 2025 到 2026 年新出现的模型指纹（单词成句的「碎片式冥想」、伪苏格拉底式自问自答、每个列表项一个装饰性 emoji、伪心理治疗口吻、无生命主语、结尾说教等）。
- 21 条硬性禁用：出现即删除的结构，包括长破折号、「не просто X, а Y」、「в современном мире」、「играет ключевую роль」。
- 扫描器：0 到 100 的干净度评分，按类别列出命中，句长节奏、名词动词比、Markdown 感知（代码块和引用不计入）。学术、法律、文学文本有单独的体裁模式 `--genre`，否则正式文本会被误判。
- 作者声音校准：给几篇你自己写的俄语文本，Skill 会按你的节奏和用词改写，而不是改成千篇一律的「人味」。
- 四轮审计：检测器视角、路人视角、句子「心电图」、列表「骨架」。

## 数据校准

规则不是凭感觉定的。目录在三个公开语料上校准过，共 **5.5 万篇**带人机标注的俄语文本，包括 GigaChat 和 YandexGPT 的输出：

| 语料 | 规模 | 发现 |
|---|---|---|
| AINL-Eval 2025 | 35 158 篇学术摘要 | 严格模式下规则命中人类作者的比例不低于模型，「является」和「данный」在学术体裁里是正常用法，因此加入了体裁过滤 |
| M4 | 5 759 对 | 社交媒体和百科文本，gpt-3.5 时代的指纹 |
| LLMTrace | 14 763 篇，30 个生成器 | 长破折号更取决于体裁而非作者；俄罗斯模型（GigaChat-Max 77%、YandexGPT-5 74%）比 GPT 更爱用破折号；人类每百词 0.29 个特征，模型 0.67 个 |

所有数字可以复现：校准脚本和报告在 `eval/` 目录，语料是公开的。

## 它不做什么

- 不用来骗过 AI 检测器。不插入错别字，不用拉丁字母替换西里尔字母。为了通过检测而损坏文本，是在欺骗读者。目标只有一个：写出俄罗斯人真的会写的文本。
- 不编造细节。原文没有数字和案例，Skill 就用节奏、语气和结构让文本活起来，或者问你要材料。
- 不判定作者身份。扫描器的分数是修改的依据，不是「这是 AI 写的」的裁决。

## 链接

- 源码：[github.com/ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru)
- 网站与在线扫描：[humanizer-ru.aifrontier.tech](https://humanizer-ru.aifrontier.tech/)
- 更新日志：[CHANGELOG.md](CHANGELOG.md)
- 引用的研究来源：[SOURCES.md](SOURCES.md)

作者：Ilya Utov（[GitHub](https://github.com/ilyautov)）。欢迎 issue 和 PR，包括中文的。
