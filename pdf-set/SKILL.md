---
name: pdf-set
description: OCR-to-markdown pipeline for book/PDF image workflows: OCR images, rough merge, split by一级标题/目录, format/layout cleanup, merge formatted chapters, translate with paragraph/quote rules, and merge translations. Use when handling OCR图片、合并结果、排版结果、翻译结果 or book reconstruction tasks.
metadata:
  short-description: OCR-to-markdown workflow for book/PDF image pipelines
---

# PDF OCR Workflow

Use the correct subtask file based on the user's request. Each subtask is a standalone procedure; do not mix steps across tasks unless asked.

## Task Map
- **OCR from images** → read `references/OCR.md`
- **Rough merge pages** → read `references/粗合并.md`
- **Split by一级标题/目录** → read `references/分割.md`
- **Layout cleanup** → read `references/排版.md`
- **Merge formatted files** → read `references/排版合并.md`
- **Translate formatted files** → read `references/翻译.md`
- **Merge translations** → read `references/翻译合并.md`

## Usage Rules
1. Identify the user's target stage (OCR/合并/分割/排版/翻译).
2. Open only the matching subtask file(s).
3. Follow the steps in order; do not skip CRITICAL phases.
4. Keep outputs in the specified folders and naming formats.

## Notes
- Do not add extra guidance beyond the selected subtask.
- Preserve special markers (e.g., `🀄，页码`) when the subtask requires it.
