# -*- coding: utf-8 -*-
import argparse
import base64
import glob
import os
import re
import shutil
import sys
import time
import unicodedata
from openai import OpenAI

SCRIPT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "assets"))

DEFAULT_INPUT_DIRNAME = "ocr-result"
DEFAULT_IMAGES_DIRNAME = "images"
DEFAULT_FOOTNOTE_PROMPT = "footnote_continuation_prompt.md"
DEFAULT_OCR_PROMPT = "ocr_prompt.md"


def _load_secrets_text(path):
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_secret(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _load_secrets_or_exit(path):
    content = _load_secrets_text(path)
    if not content.strip():
        print("请在Antigravity Tools中复制配置粘贴到secrets_openai.txt中！")
        sys.exit(1)
    return content


def read_single_path(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            value = line.strip()
            if value:
                return value
    return ""


BASE_URL = ""
API_KEY = ""
MODEL = ""
client = None


def _get_client():
    global BASE_URL, API_KEY, MODEL, client
    if client is not None:
        return client

    secrets_path = os.path.join(ASSETS_DIR, "secrets_openai.txt")
    secrets_text = _load_secrets_or_exit(secrets_path)
    BASE_URL = _extract_secret(
        [
            r"base_url\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"['\"]base_url['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
        ],
        secrets_text,
    )
    API_KEY = _extract_secret(
        [
            r"api_key\s*=\s*['\"]([^'\"]+)['\"]",
            r"api_key\s*:\s*['\"]([^'\"]+)['\"]",
        ],
        secrets_text,
    )
    MODEL = _extract_secret(
        [
            r"model\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"['\"]model['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
        ],
        secrets_text,
    )
    if not BASE_URL or not API_KEY or not MODEL:
        print("secrets_openai.txt missing required values: base_url, api_key, or model.")
        sys.exit(1)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    return client


def _read_file(path):
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write((text or "").strip() + "\n")


def _load_prompt(prompt_path, fallback):
    content = _read_file(prompt_path).strip()
    if content:
        return content
    return fallback


def _numeric_md_files(input_dir):
    files = []
    if not os.path.isdir(input_dir):
        return files
    for path in glob.glob(os.path.join(input_dir, "*.md")):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.isdigit():
            files.append((int(stem), path))
    return sorted(files, key=lambda item: item[0])


def _contains_up(text):
    return "⬆️" in text or "⬆" in text


def _contains_down(text):
    return "⬇️" in text or "⬇" in text


def _find_ranges(pages, start_idx=None, end_idx=None):
    selected = []
    for page_num, path in pages:
        if start_idx is not None and page_num < start_idx:
            continue
        if end_idx is not None and page_num > end_idx:
            continue
        selected.append((page_num, path, _read_file(path)))

    if len(selected) < 2:
        return []

    nums = [item[0] for item in selected]
    texts = {item[0]: item[2] for item in selected}
    pos = {num: idx for idx, num in enumerate(nums)}
    ranges = []
    i = 0

    while i < len(nums) - 1:
        page = nums[i]
        next_page = nums[i + 1]
        if next_page != page + 1:
            i += 1
            continue

        if not (_contains_down(texts[page]) or _contains_up(texts[next_page])):
            i += 1
            continue

        start = page
        end = next_page
        scan_page = start
        while scan_page <= end:
            if _contains_down(texts[scan_page]):
                next_up = None
                for candidate in nums[pos[scan_page] + 1 :]:
                    if candidate != nums[pos[candidate] - 1] + 1:
                        break
                    if _contains_up(texts[candidate]):
                        next_up = candidate
                        break
                min_end = scan_page + 1
                if next_up is not None:
                    min_end = max(min_end, next_up)
                if min_end in pos and min_end > end:
                    end = min_end
                    continue
            scan_page += 1

        ranges.append((start, end))
        i = pos[end] + 1

    return ranges


def _image_path_for_page(images_dir, page_num):
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
    for ext in exts:
        path = os.path.join(images_dir, f"{page_num}{ext}")
        if os.path.isfile(path):
            return path
    return None


def _guess_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext in (".tif", ".tiff"):
        return "image/tiff"
    if ext == ".bmp":
        return "image/bmp"
    return "image/jpeg"


def _image_data_url(image_path):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{_guess_mime_type(image_path)};base64,{encoded}"


def _strip_code_fence(text):
    src = (text or "").strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*?)\n```", src, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return src


def _extract_text_from_response(response):
    try:
        content = response.choices[0].message.content
    except Exception:
        return ""
    if isinstance(content, str):
        return _strip_code_fence(content)
    if not content:
        return ""
    parts = []
    for part in content:
        text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
        if text:
            parts.append(text)
    return _strip_code_fence("\n".join(parts))


def _normalize_for_content_match(text):
    src = re.sub(r"</?sup[^>]*>", "", text or "", flags=re.IGNORECASE)
    src = re.sub(r"<[^>]+>", "", src)
    kept = []
    for ch in src:
        cat = unicodedata.category(ch)
        if ch.isspace():
            continue
        if cat.startswith("P") or cat.startswith("M") or cat in {"So", "Sk"}:
            continue
        kept.append(ch)
    return "".join(kept)


def _first_mismatch(a, b, radius=30):
    limit = min(len(a), len(b))
    idx = 0
    while idx < limit and a[idx] == b[idx]:
        idx += 1
    a_part = a[max(0, idx - radius) : idx + radius]
    b_part = b[max(0, idx - radius) : idx + radius]
    return idx, a_part, b_part


def _validate_content_preserved(before_text, after_text):
    before_norm = _normalize_for_content_match(before_text)
    after_norm = _normalize_for_content_match(after_text)
    if before_norm == after_norm:
        return []
    idx, before_part, after_part = _first_mismatch(before_norm, after_norm)
    return [
        f"规范化后字符不一致，首个差异位置 {idx}。",
        f"处理前附近：{before_part}",
        f"处理后附近：{after_part}",
        f"处理前字符数 {len(before_norm)}，处理后字符数 {len(after_norm)}。",
    ]


def _build_request_content(
    start,
    end,
    images_dir,
    input_dir,
    footnote_prompt_text,
    ocr_prompt_text,
    retry_feedback="",
):
    page_range = f"{start}-{end}"
    footnote_instruction = footnote_prompt_text.replace("{page_range}", page_range)
    parts = [
        {"type": "text", "text": footnote_instruction},
        {"type": "text", "text": "OCR 原始规则如下：\n\n" + ocr_prompt_text},
    ]

    if retry_feedback:
        parts.append(
            {
                "type": "text",
                "text": (
                    "你上一次输出没有通过本地校验。请重新输出完整 Markdown，只修正以下问题：\n"
                    + retry_feedback
                ),
            }
        )

    for page_num in range(start, end + 1):
        md_path = os.path.join(input_dir, f"{page_num}.md")
        image_path = _image_path_for_page(images_dir, page_num)
        parts.append(
            {
                "type": "text",
                "text": f"--- 第 {page_num} 页第一次 OCR 结果（{page_num}.md）---\n{_read_file(md_path)}",
            }
        )
        if image_path:
            parts.append({"type": "text", "text": f"--- 第 {page_num} 页图片：{os.path.basename(image_path)} ---"})
            parts.append({"type": "image_url", "image_url": {"url": _image_data_url(image_path)}})
        else:
            parts.append({"type": "text", "text": f"警告：未找到第 {page_num} 页图片。"})
    return parts


def _request_range(
    start,
    end,
    images_dir,
    input_dir,
    footnote_prompt_text,
    ocr_prompt_text,
    retry_feedback="",
):
    messages = [
        {
            "role": "user",
            "content": _build_request_content(
                start,
                end,
                images_dir,
                input_dir,
                footnote_prompt_text,
                ocr_prompt_text,
                retry_feedback=retry_feedback,
            ),
        }
    ]
    openai_client = _get_client()
    response = openai_client.chat.completions.create(model=MODEL, messages=messages)
    text = _extract_text_from_response(response)
    if not text:
        raise RuntimeError(f"{start}-{end}: API 返回空文本")
    return text


def _original_range_text(start, end, input_dir):
    chunks = []
    for page_num in range(start, end + 1):
        chunks.append(_read_file(os.path.join(input_dir, f"{page_num}.md")).strip())
    return "\n\n".join(x for x in chunks if x)


def _format_progress(completed, total):
    total = max(total, 1)
    ratio = completed / total
    width = 40
    filled = int(round(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    status = "OVER" if completed >= total else "RUNNING"
    return f"[{completed}/{total}] [{bar}] [{ratio * 100:6.2f}%] [{status}]"


def _default_backup_dir(input_dir):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(input_dir, "_footnote_backup", stamp)


def _move_to_backup(path, backup_dir):
    if not os.path.isfile(path):
        return
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(path))
    if os.path.exists(backup_path):
        stem, ext = os.path.splitext(os.path.basename(path))
        idx = 1
        while True:
            candidate = os.path.join(backup_dir, f"{stem}.{idx}{ext}")
            if not os.path.exists(candidate):
                backup_path = candidate
                break
            idx += 1
    shutil.move(path, backup_path)


def _apply_ocr_result_updates(input_dir, ranges, corrected_ranges, backup_dir):
    for start, end in ranges:
        out_path = os.path.join(input_dir, f"{start}-{end}.md")
        _move_to_backup(out_path, backup_dir)
        for page_num in range(start, end + 1):
            _move_to_backup(os.path.join(input_dir, f"{page_num}.md"), backup_dir)
        _write_file(out_path, corrected_ranges[(start, end)])


def process_ranges(
    input_dir,
    images_dir,
    footnote_prompt_path,
    ocr_prompt_path,
    backup_dir=None,
    start_idx=None,
    end_idx=None,
    max_retries=5,
    plan_only=False,
):
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    pages = _numeric_md_files(input_dir)
    ranges = _find_ranges(pages, start_idx=start_idx, end_idx=end_idx)
    if not ranges:
        print("未发现跨页脚注承接范围。")
        return

    print("发现跨页脚注承接范围：")
    for start, end in ranges:
        print(f"- {start}-{end}.md")
    if plan_only:
        return

    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    footnote_prompt_text = _load_prompt(
        footnote_prompt_path,
        "请忠实整理 OCR 结果，只移动跨页脚注，不补写、不删改正文。作用页面为 {page_range}。",
    )
    ocr_prompt_text = _load_prompt(
        ocr_prompt_path,
        "Extract and transcribe any visible text from this image, exactly as it appears.",
    )
    completed = 0
    total = len(ranges)
    corrected_ranges = {}
    backup_dir = backup_dir or _default_backup_dir(input_dir)
    print(_format_progress(completed, total))
    for start, end in ranges:
        before_text = _original_range_text(start, end, input_dir)
        retry_feedback = ""
        last_errors = []
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                time.sleep(1)
            result = _request_range(
                start,
                end,
                images_dir,
                input_dir,
                footnote_prompt_text,
                ocr_prompt_text,
                retry_feedback=retry_feedback,
            )
            errors = _validate_content_preserved(before_text, result)
            if not errors:
                corrected_ranges[(start, end)] = result
                completed += 1
                print(f"{start}-{end} 校验通过。")
                print(_format_progress(completed, total))
                break

            last_errors = errors
            retry_feedback = "\n".join(errors) + "\n请保留所有处理前字符，只移动跨页脚注位置。"
            print(f"{start}-{end}.md 第 {attempt} 次校验失败，准备重试：{'；'.join(errors)}")
        else:
            raise RuntimeError(
                f"{start}-{end}.md 重试 {max_retries} 次后仍未通过字符守恒校验："
                + "；".join(last_errors)
            )

    _apply_ocr_result_updates(input_dir, ranges, corrected_ranges, backup_dir)
    print(f"全部跨页脚注处理完成，已直接修改 OCR 结果目录：{input_dir}")
    print(f"原单页文件已备份到：{backup_dir}")


def main():
    print("\n********************************")
    print("*** Footnote Continuation Fix ***")
    print("********************************\n")

    parser = argparse.ArgumentParser(
        description="Fix OCR footnotes split across continuous pages before rough merge."
    )
    parser.add_argument("--base-dir", default=os.getcwd(), help="Book root directory (default: current directory).")
    parser.add_argument("--book-name", default=None, help="Book name (used to resolve <base-dir>/<book-name>).")
    parser.add_argument("--base-dir-from", default=None, help="UTF-8 text file containing base directory.")
    parser.add_argument("--input-dir", default=None, help=f"Path to OCR folder (default: <base-dir>/{DEFAULT_INPUT_DIRNAME}).")
    parser.add_argument("--input-dir-from", default=None, help="UTF-8 text file containing input folder path.")
    parser.add_argument("--images-dir", default=None, help=f"Path to images folder (default: <base-dir>/{DEFAULT_IMAGES_DIRNAME}).")
    parser.add_argument("--images-dir-from", default=None, help="UTF-8 text file containing images folder path.")
    parser.add_argument("--backup-dir", default=None, help="Backup folder for original page markdown files (default: <input-dir>/_footnote_backup/<timestamp>).")
    parser.add_argument("--backup-dir-from", default=None, help="UTF-8 text file containing backup folder path.")
    parser.add_argument("--prompt-file", default=None, help="Path to footnote prompt file (default: <skill-dir>/assets/footnote_continuation_prompt.md).")
    parser.add_argument("--prompt-file-from", default=None, help="UTF-8 text file containing footnote prompt file path.")
    parser.add_argument("--ocr-prompt-file", default=None, help="Path to OCR prompt file sent as reference (default: <skill-dir>/assets/ocr_prompt.md).")
    parser.add_argument("--ocr-prompt-file-from", default=None, help="UTF-8 text file containing OCR prompt file path.")
    parser.add_argument("--start", type=int, default=None, help="Start page index (inclusive).")
    parser.add_argument("--end", type=int, default=None, help="End page index (inclusive).")
    parser.add_argument("--max-retries", type=int, default=5, help="Maximum API retries after validation failure (default: 5).")
    parser.add_argument("--plan-only", action="store_true", help="Only print detected ranges; do not call API or write files.")
    args = parser.parse_args()

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from
    if args.book_name:
        base_dir = os.path.join(base_dir, args.book_name)

    input_dir = args.input_dir or os.path.join(base_dir, DEFAULT_INPUT_DIRNAME)
    if args.input_dir_from:
        value = read_single_path(args.input_dir_from)
        if value:
            input_dir = value

    images_dir = args.images_dir or os.path.join(base_dir, DEFAULT_IMAGES_DIRNAME)
    if args.images_dir_from:
        value = read_single_path(args.images_dir_from)
        if value:
            images_dir = value

    backup_dir = args.backup_dir
    if args.backup_dir_from:
        value = read_single_path(args.backup_dir_from)
        if value:
            backup_dir = value

    prompt_path = args.prompt_file or os.path.join(ASSETS_DIR, DEFAULT_FOOTNOTE_PROMPT)
    if args.prompt_file_from:
        value = read_single_path(args.prompt_file_from)
        if value:
            prompt_path = value

    ocr_prompt_path = args.ocr_prompt_file or os.path.join(ASSETS_DIR, DEFAULT_OCR_PROMPT)
    if args.ocr_prompt_file_from:
        value = read_single_path(args.ocr_prompt_file_from)
        if value:
            ocr_prompt_path = value

    print(f"Input directory: {input_dir}")
    print(f"Images directory: {images_dir}")
    print(f"Backup directory: {backup_dir or os.path.join(input_dir, '_footnote_backup', '<timestamp>')}")
    print(f"Footnote prompt file: {prompt_path}")
    print(f"OCR prompt file: {ocr_prompt_path}")
    print(f"Page range: {args.start}-{args.end}")
    print(f"Plan only: {args.plan_only}")

    process_ranges(
        input_dir=input_dir,
        images_dir=images_dir,
        footnote_prompt_path=prompt_path,
        ocr_prompt_path=ocr_prompt_path,
        backup_dir=backup_dir,
        start_idx=args.start,
        end_idx=args.end,
        max_retries=args.max_retries,
        plan_only=args.plan_only,
    )


if __name__ == "__main__":
    main()
