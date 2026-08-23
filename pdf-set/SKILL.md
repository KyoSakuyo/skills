---
name: pdf-set
description: Process scanned PDF books through image splitting, OCR, typesetting, translation, EPUB export, cover generation, and Calibre metadata embedding.
---
# pdf-set

Use the correct subtask file based on the user's request. Each subtask is a standalone procedure; do not mix steps across tasks unless asked.

## Task Map
- **Install prerequisites** → read `references/安装前置组件.md`
- **Split PDF to images** → read `references/分图.md`
- **OCR from images** → read `references/OCR.md`
- **Fix cross-page footnotes before typesetting** → read `references/跨页脚注.md`
- **Typeset OCR pages into the final book** → read `references/排版成书.md`
- **Classify headings in the typeset book** → read `references/标题分类.md`
- **Replace image placeholders in the typeset book** → read `references/图片替换.md`
- **Split for translation** → read `references/翻译分割.md`
- **Typeset translation** → read `references/翻译排版.md`
- **Translate formatted files** → read `references/翻译.md`
- **Merge translations** → read `references/翻译合并.md`
- **Export Markdown to EPUB** → read `references/导出EPUB.md`
- **Generate a default cover and write EPUB metadata** → read `references/制作封面与元信息.md`

## Usage Rules
1. Identify the user's target stage (分图/OCR/跨页脚注/排版成书/标题分类/图片替换/翻译/导出EPUB/封面与元信息).
2. Open only the matching subtask file(s).
3. Follow the steps in order; do not skip CRITICAL phases.
4. Keep outputs in the specified folders and naming formats.

## Notes
- Do not add extra guidance beyond the selected subtask.
