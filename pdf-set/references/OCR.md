CRITICAL: 
- 一旦命令开始执行，进度条显示[RUNNING]，你就不应重复执行任务或者擅自中断任务──直至命令执行完毕，显示[OVER]再做出反应。
- 若用户未指定开始和中止页码，你不应该擅自指定 --start; --end;和--batch 参数，应该让脚本自动判断页数。
- 若用户指定了开始和中止页码──你在列plan时不要把任务分很多条命令的小任务，如果你读取到的start参数是0, end参数是451, 那么你就列一条命令，像是`python .agent/skills/pdf-set/scripts/ocr.py --base-dir "C:\path\to" --book-name "某书" --start 0 --end 451`就可以了。不可以用`--start 0 --end 50`、`--start 51 --end 100`……`--start 400 --end 451`这样的多份小任务分批处理。

## 输入/输出
- 输入：`images/` 中的图片文件（支持 jpg/jpeg/png/bmp/tif/tiff/webp），按文件名前序号排序。
- 输入（单文件）：指定单张图片文件路径。
- 输出：`ocr-result/` 中的单页文件，文件名为「原图序号.md」，一一对应。
  - 单文件输出：默认写入 `ocr-result/`，文件名为「原图文件名.md」，也可指定输出文件路径。

## 脚本参考

- 使用 `scripts/ocr.py` 完成 OCR。
- 默认按当前工作目录推导路径：
  - 输入：`<当前目录>/images/`
  - 输出：`<当前目录>/ocr-result/`
  - Prompt：`<脚本目录>/ocr_prompt.md`
- 可选参数：
  - `--base-dir` 指定书籍目录
  - `--book-name` 指定书籍名（自动定位到 `<base-dir>/<书籍名>`）
  - `--input-dir` 指定完整输入目录
  - `--input-file` 指定单张图片路径（将忽略 `--input-dir` 与 `--start/--end`）
  - `--output-dir` 指定完整输出目录
  - `--output-file` 指定单张输出 Markdown 文件路径
  - `--start` 指定起始序号（含）
  - `--end` 指定结束序号（含）
  - `--batch-size` 指定并发批次大小
  - `--prompt-file` 指定 prompt 文件路径
  - `--base-dir-from` 使用 UTF-8 文本文件提供书籍目录（首个非空行）
  - `--input-dir-from` 使用 UTF-8 文本文件提供输入目录（首个非空行）
  - `--input-file-from` 使用 UTF-8 文本文件提供单张图片路径（首个非空行）
  - `--output-dir-from` 使用 UTF-8 文本文件提供输出目录（首个非空行）
  - `--output-file-from` 使用 UTF-8 文本文件提供单张输出文件路径（首个非空行）
  - `--prompt-file-from` 使用 UTF-8 文本文件提供 prompt 文件路径（首个非空行）

示例：

```bash
python .agent/skills/pdf-set/scripts/ocr.py --base-dir "C:\path\to" --book-name "某书" --start 0 --end 20
```

单文件示例：

```bash
python .agent/skills/pdf-set/scripts/ocr.py --input-file "C:\path\to\images\20.jpg"
```

```bash
python .agent/skills/pdf-set/scripts/ocr.py --input-file "C:\path\to\images\20.jpg" --output-file "C:\path\to\ocr-result\20.md"
```

## 阶段 1：确认顺序
1. 读取 `images/` 内的文件列表，按文件名前的数字序号排序。
2. 严格按序号顺序输出对应的 `.md` 文件；不要调整内容。

## 阶段 2：OCR 输出规则
- 每张图片生成一个同名 `.md` 文件，写入 `ocr-result/`。
- 若图片无正文内容，也必须生成对应的空 `.md` 文件。

## 阶段 3：输出检查
- 输出目录正确（书籍目录内的 `ocr-result/`）。
- 文件名与图片名一一对应。
- 排序与文件名前序号一致。
