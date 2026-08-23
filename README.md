<img width="1791" height="690" alt="github-header-banner" src="https://github.com/user-attachments/assets/cbfb5301-9609-4939-929d-e36a98bbb119" />

<div align="center">

# pdf-set

> 面向 AI Agent 的 PDF 书籍 OCR、排版、翻译与 EPUB 导出工具集

### 从扫描版 PDF 到可编辑 Markdown / EPUB 的半自动书籍处理流程

不绑定特定 AI 客户端，不依赖额外管理工具。推荐使用 **Codex**，也可以使用 Claude Code、Cursor Agent、Gemini CLI、Qwen Code 等能读取本地文件并运行命令的 Agent。

[适合做什么](#适合做什么) • [使用门槛](#使用门槛) • [安装依赖](#安装依赖) • [安装-skill](#安装-skill) • [配置 API](#配置-api) • [基本流程](#基本流程) • [翻译流程](#翻译流程) • [常见问题](#常见问题) • [版本演进](#版本演进-changelog)

</div>

---

`pdf-set` 是一个给 AI Agent 使用的 PDF 书籍处理 skill，主要用于把扫描版 PDF 逐页转成图片、OCR 为 Markdown、整理标题层级、排版成书，并可继续进行翻译和 EPUB 导出。

## 适合做什么

- 将扫描版 PDF 书籍 OCR 成可编辑的 Markdown。
- 为低清晰度、不可复制文字的 PDF 提取正文。
- 将竖排、繁体、旧式排版书籍整理成更适合现代阅读的文本。
- 对 OCR 后的 Markdown 做标题整理、断行处理、注释修复和成书排版。
- 将整理后的文本翻译成中文、外文或双语对照版本。
- 将最终 Markdown 导出为 EPUB，方便在电纸书或移动设备上阅读。

## 使用门槛

你需要准备：

- 一个能执行本地命令的 AI Agent，推荐 Codex。
- Python 环境。
- Pandoc，用于导出 EPUB。
- Typora、Obsidian 或其他 Markdown 编辑器，用于人工检查和微调。
- 你自己的 OpenAI 兼容 API。

注意：本项目不会提供 API Key。OCR 和翻译都需要调用模型接口，请自行准备可用的 `base_url`、`api_key` 和 `model`。

如果你没有直接可用的 API，可以考虑使用 [ProxyPal](https://github.com/heyhuynhgiabuu/proxypal) 等反代或本地 API 网关项目，把你已有的模型订阅转换为 OpenAI 兼容接口。无论使用哪种方式，都请确认它符合你的服务条款、隐私要求和当地法律法规。

## 推荐模型

推荐使用最新的 `gpt-5.5` 模型，尤其是 OCR、复杂排版、标题层级判断和翻译任务。

如果你的 API 服务暂时没有开放 `gpt-5.5`，可以退而使用该服务中最新、最强的 GPT-5 系列视觉/多模态模型。OCR 阶段必须选择支持图片输入的模型。

## 安装依赖

### 1. 安装基础软件

- [Python](https://www.python.org/downloads/)：运行处理脚本。
- [Pandoc](https://github.com/jgm/pandoc/releases)：将 Markdown 导出为 EPUB。
- Markdown 编辑器：推荐 Typora 或 Obsidian。
- AI Agent：推荐 Codex，也可以使用其他能运行本地命令的 Agent。

### 2. 安装 Python 包

进入你的工作环境后安装：

```bash
pip install pypdfium2 openai
```

如果你使用 Codex，也可以直接让它执行：

```text
使用 pdf-set 安装前置组件
```

## 安装 skill

### Codex 推荐方式

把本仓库中的 `pdf-set` 文件夹复制到 Codex 的 skills 目录：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -r pdf-set "${CODEX_HOME:-$HOME/.codex}/skills/pdf-set"
```

Windows 用户可以放到：

```text
%USERPROFILE%\.codex\skills\pdf-set
```

也可以直接把整个仓库作为工作区打开，然后要求 Codex 使用当前仓库里的 `pdf-set`。

### 其他 Agent

如果你的 Agent 不支持自动发现 skill，请让它先阅读：

```text
pdf-set/SKILL.md
```

然后按 `SKILL.md` 中的 Task Map 选择对应 reference 文件执行。

## 配置 API

打开：

```text
pdf-set/assets/secrets_openai.txt
```

写入你自己的 OpenAI 兼容 API 配置：

```text
base_url = "https://api.openai.com/v1"
api_key = "你的_API_KEY"
model = "gpt-5.5"
```

如果你使用反代服务，例如本地网关或 ProxyPal，一般会类似这样：

```text
base_url = "http://127.0.0.1:8317/v1"
api_key = "你的本地或反代 API Key"
model = "gpt-5.5"
```

请不要把填好密钥的 `secrets_openai.txt` 上传到公开仓库。这个文件在项目中只应作为空占位文件存在。

如果你在 Git 仓库里使用本项目，并且希望本地密钥不被误提交，可以执行：

```bash
git update-index --skip-worktree pdf-set/assets/secrets_openai.txt
```

## 建议目录结构

建议为每本书单独建立一个目录：

```text
工作区/
├── pdf-set/
└── 书籍名/
    └── 原书.pdf
```

实际处理过程中会逐步生成：

```text
书籍名/
├── images/
├── ocr-result/
├── merge-result/
├── translate-result/
├── 原书.pdf
├── 书籍名.md
└── 书籍名.epub
```

路径最好尽量避免奇怪符号。Windows 下如果遇到编码或命令行问题，优先使用纯英文工作区路径。

## 基本流程

下面的示例都可以直接交给 Codex 或其他 Agent 执行。把 `【书籍名】` 替换成你的实际目录名。

### 1. PDF 分图

```text
使用 pdf-set 对【书籍名】分图
```

输出目录：

```text
【书籍名】/images/
```

### 2. OCR

```text
使用 pdf-set 对【书籍名】开始 OCR
```

输出目录：

```text
【书籍名】/ocr-result/
```

OCR 会逐页调用你在 `secrets_openai.txt` 中配置的模型。大书会消耗较多 token 和时间，建议先拿少量页测试配置是否正常。

### 3. 粗合并

```text
使用 pdf-set 对【书籍名】的全部 OCR 结果粗合并
```

输出文件：

```text
【书籍名】/merge-result/0.rough.md
```

### 4. 标题分类

```text
使用 pdf-set 对【书籍名】标题分类
```

这一步用于整理 `0.rough.md` 中的标题层级。建议完成后人工检查一次目录结构，尤其是章、节、附录、译后记等边界。

### 5. 排版成书

```text
使用 pdf-set 对【书籍名】排版成书
```

输出文件：

```text
【书籍名】/【书籍名】.md
```

这一步会处理硬断行、注释空行、章节拼接等问题。最终结果仍建议人工快速检查，特别是脚注、图片占位、表格和公式。

### 6. 导出 EPUB

```text
使用 pdf-set 对【书籍名】导出 EPUB
```

输出文件：

```text
【书籍名】/【书籍名】.epub
```

导出依赖 Pandoc。若文档中包含图片，请确认图片文件仍在书籍目录中，并且 Markdown 中的路径可以正常访问。

## 翻译流程

如果需要翻译，建议先完成 OCR、粗合并、标题分类和排版成书，再进入翻译流程。

### 1. 翻译分割

```text
使用 pdf-set 对【书籍名】翻译分割
```

### 2. 翻译

```text
使用 pdf-set 对【书籍名】翻译
```

翻译会消耗大量 API 额度。长章节建议分批处理，避免单次上下文过大导致模型遗漏、截断或格式混乱。

### 3. 翻译排版

```text
使用 pdf-set 对【书籍名】翻译排版
```

### 4. 翻译合并

```text
使用 pdf-set 对【书籍名】翻译合并
```

最终会得到合并后的译文或对照译文，具体输出以 Agent 执行时读取的 reference 说明为准。

## 直接运行脚本

如果你不想让 Agent 自动执行，也可以手动运行脚本。下面是几个常见例子。

PDF 分图：

```bash
python pdf-set/scripts/convert_pdf_to_images.py --base-dir "书籍名"
```

OCR：

```bash
python pdf-set/scripts/ocr.py --base-dir "书籍名"
```

粗合并：

```bash
python pdf-set/scripts/merge_rough.py --base-dir "书籍名"
```

排版成书：

```bash
python pdf-set/scripts/typeset_book.py --base-dir "书籍名"
```

不同脚本支持的参数略有差异，最稳妥的方式仍然是让 Agent 先阅读 `pdf-set/SKILL.md` 和对应的 `pdf-set/references/*.md`。

## 常见问题

### Q：为什么必须自己提供 API？

A：因为 OCR 和翻译都需要调用大模型。本项目只提供处理流程、脚本和 prompt，不提供模型服务，也不内置任何密钥。

### Q：可以不用 OpenAI 官方接口吗？

A：可以。脚本使用 OpenAI Python SDK，但只要求接口兼容 OpenAI API 格式。你可以使用官方 API，也可以使用支持 OpenAI 兼容格式的第三方服务、本地网关或反代服务。

### Q：没有 API 怎么办？

A：可以考虑使用 ProxyPal 等项目，将你已有的模型订阅或本地服务转换为 OpenAI 兼容接口。请自行确认安全性、稳定性、隐私策略和服务条款。

### Q：为什么 OCR 结果会有错误？

A：扫描质量、字体、竖排、繁体、旧字形、图片压缩、页面倾斜、页眉页脚和复杂注释都会影响 OCR。建议先用少量页测试 prompt 和模型，再处理整本书。

### Q：为什么翻译结果会漏段或格式乱？

A：通常是单次输入太长、章节结构太复杂，或模型上下文压力过大。建议先分割，再分批翻译，并在翻译后进行人工检查。

### Q：Typora 必须买吗？

A：不是。Typora 只是比较方便的 Markdown 编辑器。你也可以使用 Obsidian、VS Code 或其他编辑器；导出 EPUB 的关键依赖是 Pandoc。

## 注意事项

- 请只处理你有权处理的文档。
- 不要把自己的 API Key、反代密钥或本地网关凭据提交到仓库。
- 大规模 OCR 和翻译前，先用 5-10 页测试模型、费用和输出质量。
- 最终成书前务必人工检查标题层级、注释、图片、表格和公式。
- 如果 Agent 执行失败，把完整报错发给它，让它根据当前目录和 reference 文件继续排查。

## 版本演进 (Changelog)

### 2.2.0

- 重组 `pdf-set` 处理流程：支持从 OCR 分页直接排版成书，并将标题分类调整到排版之后，移除已废弃的粗合并脚本与说明。
- 新增跨页脚注修复流程，包含专用 prompt、批量处理脚本、本地验证和失败重试。
- 新增图片占位符替换指南与边界检查脚本，用于定位、裁切并验证书中插图。
- 新增默认封面生成和 Calibre EPUB 元信息写入流程。
- 增强 OCR：支持并发批处理、页面范围、断点续传、单图模式和模型回退。
- 新增快速翻译脚本与回退 prompt，支持多文件并发、超时回退、限流等待、断点续传和双语格式校验。
- 扩展凭据与 Python 缓存忽略规则：本地 `secrets_openai.txt*`、`__pycache__` 和字节码文件不会进入仓库。

### 2.1.2

- 同步 `pdf-set` skill 的 playground 更新，优化翻译排版脚本的分句逻辑。
- 翻译排版现在会保留短括号内的问句，不再因 `(…?)`、`（…？）`、`[…]` 或 `【…？】` 内部问号提前拆段。
- 保持 `pdf-set/assets/secrets_openai.txt` 为空占位文件，避免真实 API 配置进入仓库。

### 2.1.1

- 同步 `pdf-set` skill 的 playground 更新，调整 OCR、粗合并、标题分类和翻译排版相关说明。
- 将 Agent 执行示例中的脚本路径更新为 `.agent/skills/pdf-set/...`，适配 Antigravity 场景。
- 更新 OCR 后台任务提示：Antigravity 中运行命令后交由 Background Steps 查看进度。
- 简化粗合并脚本：移除自动 Markdown 标题去重逻辑，仅清理空白页标记和连续空行，避免误删正文标题。
- 调整翻译排版默认分段参数：目标字符数从 500 改为 250，分割阈值从 700 改为 450。
- 保持 `pdf-set/assets/secrets_openai.txt` 为空占位文件，避免真实 API 配置进入仓库。

### 2.1

- 重写 README：项目说明改为 Codex / 通用 AI Agent 工作流，不再绑定特定 AI 客户端或额外管理工具。
- 新增 API 配置说明：强调用户需要自行提供 OpenAI 兼容 API，并说明 `base_url`、`api_key`、`model` 的填写方式。
- 新增反代建议：没有直接 API 时，可考虑使用 ProxyPal 等本地反代或 API 网关项目。
- 更新模型建议：推荐使用最新的 `gpt-5.5`；若接口暂未开放，则使用服务中最新、最强的 GPT-5 系列视觉/多模态模型。
- 清理旧工作流残留：移除文档和脚本提示中对旧客户端结构的依赖，统一改为通用 `skills/pdf-set` 路径和通用 API 配置提示。

### 2.0

- 用新版 `pdf-set` 替换旧版工作流。
- 新增翻译分割、翻译、翻译排版、翻译合并等翻译处理流程。
- 将 prompt、样式和 API 配置占位文件移动到 `pdf-set/assets/`。
- 新增标题分类、排版成书和 EPUB 导出相关 reference。
- 将 `pdf-set/assets/secrets_openai.txt` 作为空占位文件保留，避免真实密钥进入仓库。
