import os
import sys
import time
import re
import glob
import argparse
import math
import tempfile
import unicodedata
from datetime import datetime, timezone, timedelta
from openai import OpenAI

SCRIPT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "assets"))


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


def _load_prompt(prompt_path):
    if prompt_path and os.path.isfile(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    return "请将下方全部法语段落逐段翻译成中文。每段输出格式必须是：原文一段，下一行是以 > 开头的中文译文，然后单独一行 ---。不要漏段。"


def _split_paragraphs(text):
    text = (text or "").strip()
    if not text:
        return []
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _count_translated_paragraphs(output_text):
    if not output_text.strip():
        return 0
    return len(re.findall(r"(?m)^\s*---\s*$", output_text))


def _validate_batch_blocks_two_lines(output_text):
    """Validate each block before '---' has exactly two non-empty lines and no blank lines."""
    lines = output_text.splitlines()
    block: list[str] = []
    sep_count = 0
    first_error = ""
    has_blank_line = False

    for line in lines:
        if not line.strip():
            has_blank_line = True
        if re.match(r"^\s*---\s*$", line):
            sep_count += 1
            non_empty = [x for x in block if x.strip()]
            if len(non_empty) != 2 and not first_error:
                first_error = (
                    f"第 {sep_count} 个分割块包含 {len(non_empty)} 行（应为 2 行）"
                )
            block = []
            continue
        block.append(line)

    if not first_error and any(x.strip() for x in block):
        first_error = "最后一个分割线后仍有未闭合内容"

    return sep_count, first_error, has_blank_line


def _analyze_structure_mismatch_details(output_text, expected_count):
    lines = output_text.splitlines()
    block = []
    details = []
    block_idx = 0
    max_detail = 5
    para_cursor = 1

    for line in lines:
        if re.match(r"^\s*---\s*$", line):
            block_idx += 1
            non_empty = [x for x in block if x.strip()]
            n = len(non_empty)
            if n != 2 and len(details) < max_detail:
                if n > 2 and n % 2 == 0:
                    merged = n // 2
                    start_no = para_cursor
                    end_no = para_cursor + merged - 1
                    if merged >= 2:
                        details.append(
                            f"疑似把原文的第 {start_no} 段和第 {end_no} 段误合并成一段了，必须分开。"
                        )
                    else:
                        details.append(
                            f"第 {block_idx} 个分割块有 {n} 行，疑似发生合并，必须分开。"
                        )
                elif n < 2:
                    details.append(
                        f"第 {block_idx} 个分割块只有 {n} 行，疑似缺少原文或译文。"
                    )
                else:
                    details.append(
                        f"第 {block_idx} 个分割块有 {n} 行，疑似发生错误拆分或格式错位。"
                    )
            block = []
            if n > 0:
                if n % 2 == 0:
                    para_cursor += max(1, n // 2)
                else:
                    para_cursor += 1
            continue
        block.append(line)

    sep_count = len(re.findall(r"(?m)^\s*---\s*$", output_text))
    if sep_count < expected_count and len(details) < max_detail:
        details.append(
            f"总分割块数不足：只输出了 {sep_count} 段，期望 {expected_count} 段，疑似存在合并或漏段。"
        )
    elif sep_count > expected_count and len(details) < max_detail:
        details.append(
            f"总分割块数过多：输出了 {sep_count} 段，期望 {expected_count} 段，疑似存在错误拆分。"
        )
    return details


def _read_file(path):
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _format_decode_error(path, err):
    return (
        f"{path} 不是合法 UTF-8：byte {err.start}-{err.end}，"
        f"{err.reason}。请移走或删除这个半成品输出文件后续翻。"
    )


def _append_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = b""
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as rf:
            existing = rf.read()

    prefix_newline = b""
    if existing and existing[-1:] not in (b"\n", b"\r"):
        prefix_newline = b"\n"

    addition = prefix_newline + (text.rstrip() + "\n").encode("utf-8")
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "wb") as f:
        f.write(existing)
        f.write(addition)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _rollback_file_to_size(path, size_before_append):
    if size_before_append <= 0:
        # No previous content: clear file to empty.
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        return
    with open(path, "rb+") as f:
        f.truncate(size_before_append)


def _truncate_preview_text(text, max_len=50):
    line = re.sub(r"\s+", " ", text.strip())
    if len(line) <= max_len:
        return line
    return line[: max_len - 3] + "..."


def _build_chunk_preview(paragraphs, start_para_idx, max_len=50):
    lines = []
    for i, para in enumerate(paragraphs, start=1):
        para_no = start_para_idx + i
        lines.append(f"Para{para_no}")
        lines.append(_truncate_preview_text(para, max_len=max_len))
        lines.append("---")
    return "\n".join(lines)


def _build_retry_feedback_block(failed_output, reasons):
    output_text = (failed_output or "").strip()
    reason_lines = [r.strip() for r in (reasons or []) if str(r).strip()]
    if not output_text and not reason_lines:
        return ""

    parts = ["\n\n你上一次输出未通过校验，请严格修正："]
    if output_text:
        parts.append("上一次失败输出（错误示例，请勿复用）：")
        parts.append(output_text)
    if reason_lines:
        parts.append("上一次错误原因：")
        for idx, item in enumerate(reason_lines, start=1):
            parts.append(f"{idx}. {item}")
    parts.append(
        "请只输出这一次的正确结果，严格遵守每段的行数结构（原文+`>`译文）并以 `---` 分隔，且不要输出空行。请务必修正过来。"
    )
    return "\n".join(parts)


def _extract_two_line_blocks(output_text):
    lines = output_text.splitlines()
    block = []
    blocks = []

    for line in lines:
        if re.match(r"^\s*---\s*$", line):
            non_empty = [x for x in block if x.strip()]
            if len(non_empty) != 2:
                return [], f"分割块行数异常：{len(non_empty)}（应为 2 行）"
            blocks.append((non_empty[0], non_empty[1]))
            block = []
            continue
        block.append(line)

    if any(x.strip() for x in block):
        return [], "最后一个分割线后仍有未闭合内容"
    return blocks, ""


def _normalize_for_content_match(text):
    src = (text or "")
    kept = []
    for ch in src:
        cat = unicodedata.category(ch)
        if cat.startswith("P"):
            continue
        if ch.isspace():
            continue
        kept.append(ch)
    return "".join(kept)


def _looks_like_merge(out_original, first_expected, second_expected):
    out_n = _normalize_for_content_match(out_original)
    a_n = _normalize_for_content_match(first_expected)
    b_n = _normalize_for_content_match(second_expected)
    if not out_n or not a_n or not b_n:
        return False
    return a_n in out_n and b_n in out_n


def _find_original_mismatch_reasons(expected_paragraphs, output_text):
    blocks, parse_error = _extract_two_line_blocks(output_text)
    if parse_error:
        return [parse_error]

    reasons = []
    expected_len = len(expected_paragraphs)
    output_len = len(blocks)

    if output_len != expected_len:
        if output_len < expected_len:
            reasons.append(
                f"你的错误案例中只输出了 {output_len} 段，期望是 {expected_len} 段，存在漏段或合并。"
            )
        else:
            reasons.append(
                f"你的错误案例中输出了 {output_len} 段，期望是 {expected_len} 段，存在多段或错误拆分。"
            )

    check_len = min(expected_len, output_len)
    merge_hits = 0
    max_merge_report = 3

    for i in range(check_len):
        expected = expected_paragraphs[i]
        out_original = blocks[i][0]
        if _normalize_for_content_match(out_original) == _normalize_for_content_match(expected):
            continue

        para_no = i + 1
        if i + 1 < expected_len and _looks_like_merge(
            out_original, expected_paragraphs[i], expected_paragraphs[i + 1]
        ):
            next_no = para_no + 1
            if merge_hits < max_merge_report:
                reasons.append(
                    f"第 {para_no} 段与第 {next_no} 段疑似被合并到同一个输出段里。"
                )
            merge_hits += 1
            continue

        reasons.append(
            f"本次输出第 {para_no} 段没有忠实还原原文的非标点字符内容。"
            f"你必须原封不动输出以下原文：\n<<<\n{expected}\n>>>"
        )

    if expected_len > output_len:
        for i in range(output_len, expected_len):
            para_no = i + 1
            expected = expected_paragraphs[i]
            reasons.append(
                f"本次输出第 {para_no} 段未输出。你必须补上以下原文并逐字保留：\n<<<\n{expected}\n>>>"
            )
            if len(reasons) >= 20:
                break

    if merge_hits > max_merge_report:
        reasons.append(f"另外还有 {merge_hits - max_merge_report} 处疑似合并问题。")

    return reasons


def _has_markdown_heading_prefix(text, allow_blockquote=False):
    src = (text or "").lstrip()
    if allow_blockquote:
        src = re.sub(r"^\s*>+\s*", "", src)
    return bool(re.match(r"^#{1,6}(?:\s+|$)", src))


def _find_heading_tag_mismatch_reasons(expected_paragraphs, output_text):
    blocks, parse_error = _extract_two_line_blocks(output_text)
    if parse_error:
        return [parse_error]

    reasons = []
    check_len = min(len(expected_paragraphs), len(blocks))
    for i in range(check_len):
        expected = expected_paragraphs[i]
        if not _has_markdown_heading_prefix(expected, allow_blockquote=False):
            continue

        out_original, out_translation = blocks[i]
        para_no = i + 1
        if not _has_markdown_heading_prefix(out_original, allow_blockquote=False):
            reasons.append(
                f"第 {para_no} 段输入为 Markdown 标题段，但输出原文行未保留标题标签（#）。"
            )
        if _has_markdown_heading_prefix(out_translation, allow_blockquote=True):
            reasons.append(
                f"第 {para_no} 段输入为 Markdown 标题段，但译文行出现了标题标签（#）；"
                "标题标签只能出现在原文行。"
            )
    return reasons


def _format_progress_line(prefix, completed, total, width=40, status=None):
    total = max(total, 1)
    completed = min(max(completed, 0), total)
    ratio = completed / total
    filled = int(round(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    pct = ratio * 100
    status = status or ("OVER" if completed >= total else "RUNNING")
    return f"{prefix} [{completed}/{total}] [{bar}] [{pct:6.2f}%] [{status}]"


class DoubleProgress:
    def __init__(self):
        self.file_line = ""
        self.para_line = ""
        self.inited = False
        self.preview_lines = 0

    def _render(self):
        if not self.inited:
            print(self.file_line)
            print(self.para_line)
            self.inited = True
            return
        sys.stdout.write("\033[2F")
        sys.stdout.write("\033[K" + self.file_line + "\n")
        sys.stdout.write("\033[K" + self.para_line + "\n")
        sys.stdout.flush()

    def update(self, file_completed, file_total, para_completed, para_total):
        file_status = (
            "OVER"
            if file_completed >= file_total and para_completed >= para_total
            else "RUNNING"
        )
        self.file_line = _format_progress_line(
            "Files", file_completed, file_total, status=file_status
        )
        self.para_line = _format_progress_line("Paras", para_completed, para_total)
        self._render()

    def preview(self, text):
        if not self.inited:
            print("Preview: " + text)
            return
        move_up = 2 + self.preview_lines
        sys.stdout.write(f"\033[{move_up}F")
        sys.stdout.write("\033[J")
        print(text)
        print(self.file_line)
        print(self.para_line)
        self.preview_lines = text.count("\n") + 1 if text else 0
        sys.stdout.flush()


openai_secrets_path = os.path.join(ASSETS_DIR, "secrets_openai.txt")
openai_secrets_text = _load_secrets_or_exit(openai_secrets_path)
OPENAI_BASE_URL = _extract_secret(
    [
        r"base_url\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"['\"]base_url['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
    ],
    openai_secrets_text,
)
OPENAI_API_KEY = _extract_secret(
    [
        r"api_key\s*=\s*['\"]([^'\"]+)['\"]",
        r"api_key\s*:\s*['\"]([^'\"]+)['\"]",
    ],
    openai_secrets_text,
)
OPENAI_MODEL = _extract_secret(
    [
        r"model\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"['\"]model['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
    ],
    openai_secrets_text,
)
if not OPENAI_BASE_URL or not OPENAI_API_KEY or not OPENAI_MODEL:
    print("secrets_openai.txt missing required values: base_url, api_key, or model.")
    sys.exit(1)
MODEL = OPENAI_MODEL
openai_client = None
FAST_MODE = False


def _request_kwargs():
    return {"service_tier": "fast"} if FAST_MODE else {}


class EmptyResponseError(RuntimeError):
    """Raised when API returns a structurally valid but empty response."""


class FallbackSignalError(RuntimeError):
    """Raised when response indicates truncation/safety finish reason."""


FALLBACK_FINISH_REASONS = {"PROHIBITED_CONTENT", "RECITATION"}


def _normalize_finish_reason(reason):
    if reason is None:
        return ""
    if hasattr(reason, "name") and getattr(reason, "name", None):
        return str(reason.name).strip().upper()
    text = str(reason).strip().upper()
    if "." in text:
        text = text.split(".")[-1]
    return text


def _extract_finish_reason(response):
    try:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return ""
        first = candidates[0]
        if isinstance(first, dict):
            reason = first.get("finishReason") or first.get("finish_reason")
            return _normalize_finish_reason(reason)
        reason = getattr(first, "finish_reason", None)
        if reason is not None:
            return _normalize_finish_reason(reason)
        reason = getattr(first, "finishReason", None)
        if reason is not None:
            return _normalize_finish_reason(reason)
    except Exception:
        pass
    return ""


def _extract_finish_reason_from_error_text(error_text):
    text = str(error_text or "")
    if not text:
        return ""
    patterns = [
        r'"finishReason"\s*:\s*"([^"]+)"',
        r"'finishReason'\s*:\s*'([^']+)'",
        r"finishReason\s*=\s*([A-Za-z0-9_\.]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return _normalize_finish_reason(m.group(1))
    return ""


def _is_fallback_finish_reason(reason_text):
    reason = _normalize_finish_reason(reason_text)
    if not reason:
        return False
    if reason in FALLBACK_FINISH_REASONS:
        return True
    # 兼容如 FinishReason.PROHIBITED_CONTENT 这类格式。
    return any(token in reason for token in FALLBACK_FINISH_REASONS)


def _parse_duration_to_seconds(text):
    if not text:
        return None
    s = str(text).strip()
    if not s:
        return None

    # Support formats such as: 1412.6s, 23m32.6s, 1h2m3s
    total = 0.0
    found = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)([hms])", s.lower()):
        found = True
        amount = float(value)
        if unit == "h":
            total += amount * 3600
        elif unit == "m":
            total += amount * 60
        else:
            total += amount
    if found:
        return max(1, int(math.ceil(total)))

    # Fallback: pure number means seconds.
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return max(1, int(math.ceil(float(s))))
    return None


def _extract_retry_delay_seconds(error_text):
    text = str(error_text or "")
    if not text:
        return None

    patterns = [
        r'"retryDelay"\s*:\s*"([^"]+)"',
        r'\\"retryDelay\\"\s*:\s*\\"([^\\"]+)\\"',
        r'"quotaResetDelay"\s*:\s*"([^"]+)"',
        r'\\"quotaResetDelay\\"\s*:\s*\\"([^\\"]+)\\"',
        r"reset after\s+([0-9hms\.]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        seconds = _parse_duration_to_seconds(m.group(1))
        if seconds:
            return seconds

    ts_patterns = [
        r'"quotaResetTimeStamp"\s*:\s*"([^"]+)"',
        r'\\"quotaResetTimeStamp\\"\s*:\s*\\"([^\\"]+)\\"',
    ]
    for pattern in ts_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        ts = m.group(1).strip()
        try:
            reset_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            wait_seconds = int(math.ceil((reset_at - now).total_seconds()))
            if wait_seconds > 0:
                return wait_seconds
        except Exception:
            continue
    return None


def _wait_with_terminal_hint(seconds, reason_text):
    seconds = max(1, int(seconds))
    resume_at = datetime.now() + timedelta(seconds=seconds)
    print(f"\n检测到配额限制，暂停 {seconds} 秒后自动重试。")
    if reason_text:
        print(f"原因: {reason_text}")
    print(f"预计重试时间: {resume_at.strftime('%Y-%m-%d %H:%M:%S')}")
    while seconds > 0:
        mins, secs = divmod(seconds, 60)
        sys.stdout.write(f"\r等待重试倒计时: {mins:02d}:{secs:02d}")
        sys.stdout.flush()
        time.sleep(1)
        seconds -= 1
    sys.stdout.write("\r等待重试倒计时: 00:00\n")
    sys.stdout.flush()
    print("已到重试时间，继续请求。")


def _request_text_once(model_name, request_text):
    global openai_client
    if openai_client is None:
        openai_client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    response = openai_client.chat.completions.create(
        model=model_name or OPENAI_MODEL,
        messages=[{"role": "user", "content": request_text}],
        **_request_kwargs(),
    )
    finish_reason = ""
    try:
        finish_reason = str(response.choices[0].finish_reason or "").upper()
    except Exception:
        finish_reason = ""
    if finish_reason and "CONTENT_FILTER" in finish_reason:
        raise RuntimeError(f"finishReason={finish_reason}")
    text = ""
    try:
        content = response.choices[0].message.content
        if isinstance(content, str):
            text = content.strip()
    except Exception:
        text = ""
    if text:
        return text
    raise EmptyResponseError("OpenAI API 返回空文本")


def _request_text_once_openai(request_text):
    global openai_client
    if not OPENAI_BASE_URL or not OPENAI_API_KEY or not OPENAI_MODEL:
        raise RuntimeError(
            "secrets_openai.txt missing required values: base_url, api_key, or model."
        )
    if openai_client is None:
        openai_client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": request_text}],
        **_request_kwargs(),
    )
    finish_reason = ""
    try:
        finish_reason = str(response.choices[0].finish_reason or "").upper()
    except Exception:
        finish_reason = ""
    if finish_reason and "CONTENT_FILTER" in finish_reason:
        raise RuntimeError(f"finishReason={finish_reason}")
    text = ""
    try:
        content = response.choices[0].message.content
        if isinstance(content, str):
            text = content.strip()
    except Exception:
        text = ""
    if text:
        return text
    raise EmptyResponseError("OpenAI API 返回空文本")


def _request_with_retries(model_name, request_text, max_attempts=5):
    last_error = None
    empty_count = 0
    has_non_empty_error = False

    for attempt in range(1, max_attempts + 1):
        try:
            return (
                _request_text_once(model_name, request_text),
                None,
                empty_count,
                has_non_empty_error,
                None,
            )
        except EmptyResponseError as e:
            last_error = e
            empty_count += 1
            if attempt < max_attempts:
                time.sleep(1)
        except Exception as e:
            last_error = e
            has_non_empty_error = True
            err_text = str(e)
            if "429" in err_text or "RATE_LIMIT" in err_text.upper():
                retry_after = _extract_retry_delay_seconds(err_text)
                if retry_after:
                    _wait_with_terminal_hint(retry_after, "OpenAI 429 / RATE_LIMIT")
                    continue
            if attempt < max_attempts:
                time.sleep(2)

    return None, last_error, empty_count, has_non_empty_error, None


def _request_openai_with_retries(request_text, max_attempts=5):
    last_error = None
    empty_count = 0
    has_non_empty_error = False
    for attempt in range(1, max_attempts + 1):
        try:
            return _request_text_once_openai(request_text), None, empty_count, has_non_empty_error
        except EmptyResponseError as e:
            last_error = e
            empty_count += 1
            if attempt < max_attempts:
                time.sleep(1)
        except Exception as e:
            last_error = e
            has_non_empty_error = True
            err_text = str(e)
            if "429" in err_text or "RATE_LIMIT" in err_text.upper():
                retry_after = _extract_retry_delay_seconds(err_text)
                if retry_after:
                    _wait_with_terminal_hint(retry_after, "OpenAI 429 / RATE_LIMIT")
                    continue
            if attempt < max_attempts:
                time.sleep(2)
    return None, last_error, empty_count, has_non_empty_error


def translate_paragraph_batch(paragraphs, prompt_text, extra_instruction="", preferred_model=None):
    payload_text = "\n\n".join(paragraphs)
    extra_block = ""
    if extra_instruction.strip():
        extra_block = "\n\n分段要求（必须严格遵守）：\n" + extra_instruction.strip()
    request_text = (
        prompt_text.strip()
        + extra_block
        + "\n\n"
        + "以下是需要翻译的段落（按段落空行分隔）：\n\n"
        + payload_text
    )

    primary_model = preferred_model or MODEL
    text, last_error, empty_count, has_non_empty_error, fallback_signal = _request_with_retries(
        primary_model, request_text, max_attempts=5
    )
    if text:
        return text, primary_model
    raise RuntimeError(f"翻译失败（模型 {primary_model} 重试 5 次后仍失败）: {last_error}")


def _find_max_output_index(output_dir):
    if not os.path.isdir(output_dir):
        return None
    max_idx = None
    for name in os.listdir(output_dir):
        if not name.endswith(".md"):
            continue
        stem = os.path.splitext(name)[0]
        if stem.endswith(".fail"):
            stem = stem[:-5]
        if stem.isdigit():
            num = int(stem)
            if max_idx is None or num > max_idx:
                max_idx = num
    return max_idx


def _list_input_markdown_files(input_dir):
    if not os.path.isdir(input_dir):
        return []
    files = glob.glob(os.path.join(input_dir, "*.md"))

    def sort_key(path):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.isdigit():
            return (0, int(stem))
        return (1, stem)

    return sorted(files, key=sort_key)


def _calc_resume_state(input_dir, output_dir):
    max_idx = _find_max_output_index(output_dir)
    if max_idx is None:
        return None, 0, None

    in_path = os.path.join(input_dir, f"{max_idx}.md")
    out_path = os.path.join(output_dir, f"{max_idx}.md")
    if os.path.isfile(in_path) and os.path.isfile(out_path):
        in_total = len(_split_paragraphs(_read_file(in_path)))
        try:
            out_text = _read_file(out_path)
        except UnicodeDecodeError as err:
            raise RuntimeError(_format_decode_error(out_path, err)) from err
        out_done = _count_translated_paragraphs(out_text)
        if out_done < in_total:
            return max_idx, out_done, (max_idx, out_done, in_total, False)
        return max_idx + 1, 0, (max_idx, out_done, in_total, True)

    return max_idx + 1, 0, (max_idx, None, None, None)


def _preview_target_file(path):
    text = _read_file(path)
    paras = _split_paragraphs(text)
    print(f"待处理文件: {path}")
    print(f"总段落数: {len(paras)}")
    for i, p in enumerate(paras[:5], 1):
        print(f"Para {i} {repr(p[:60])}")


def process_translation_files(input_dir, output_dir, prompt_text, chunk_size, start_idx=None, end_idx=None):
    if not os.path.isdir(input_dir):
        print(f"Input directory not found: {input_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    files = _list_input_markdown_files(input_dir)
    if not files:
        print(f"No markdown files found in: {input_dir}")
        return

    if start_idx is None and end_idx is None:
        resume_idx, resume_para, resume_info = _calc_resume_state(input_dir, output_dir)
        if resume_info is None:
            print("检验结果：输出目录暂无历史文件，将从第一个待翻译文件开始。")
        else:
            idx, out_done, in_total, is_complete = resume_info
            if out_done is None or in_total is None or is_complete is None:
                print(
                    f"检验结果：{idx}.md 在输入或输出目录中缺失，"
                    f"将从 {resume_idx}.md 开始。"
                )
            elif is_complete:
                print(
                    f"检验结果：{idx}.md 的已翻译段落数 {out_done}，"
                    f"待翻译段落数 {in_total}，已翻译完成，接下来翻译 {resume_idx}.md。"
                )
            else:
                print(
                    f"检验结果：{idx}.md 的已翻译段落数 {out_done}，"
                    f"待翻译段落数 {in_total}，未翻译完成，将从第 {out_done + 1} 段继续。"
                )
    else:
        resume_idx, resume_para = start_idx, 0

    numeric_file_nums = []
    selected = []
    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not stem.isdigit():
            continue
        num = int(stem)
        if start_idx is not None and num < start_idx:
            continue
        if end_idx is not None and num > end_idx:
            continue
        numeric_file_nums.append(num)
        if resume_idx is not None and num < resume_idx:
            continue
        selected.append((num, path))

    if not selected:
        print("No files to translate in current range.")
        return

    _preview_target_file(selected[0][1])

    progress = DoubleProgress()
    full_file_total = max(numeric_file_nums) if numeric_file_nums else selected[-1][0]

    for file_idx, (num, in_path) in enumerate(selected, start=1):
        out_path = os.path.join(output_dir, f"{num}.md")
        input_paras = _split_paragraphs(_read_file(in_path))
        total_paras = len(input_paras)
        if total_paras == 0:
            progress.update(num, full_file_total, 0, 1)
            continue

        try:
            existing_output_text = _read_file(out_path)
        except UnicodeDecodeError as err:
            raise RuntimeError(_format_decode_error(out_path, err)) from err
        existing_done = _count_translated_paragraphs(existing_output_text)
        start_para = existing_done
        if resume_idx is not None and num == resume_idx:
            start_para = max(start_para, resume_para)

        progress.update(num, full_file_total, start_para, total_paras)

        while start_para < total_paras:
            retry_idx = 0
            current_model = MODEL
            should_add_no_blank_line_hint = False
            last_failed_output = ""
            last_failure_reasons = []
            current_chunk_size = max(1, int(chunk_size))
            while True:
                chunk = input_paras[start_para : start_para + current_chunk_size]
                expected_inc = len(chunk)
                progress.preview(_build_chunk_preview(chunk, start_para, max_len=50))
                size_before = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
                done_before = start_para

                extra_instruction = (
                    f"一个`\n`代表一个换行符，一个`>`代表一个引用符号，一个`---`代表一个分隔符。每次分段你都需要使用一个换行符，请参考示例。你需要处理的文本有{expected_inc}段！"
                    f"你必须输出{expected_inc}段，你绝对不可以乱合并。如果你正确分段换行的话，你输出的内容会有且只有──{expected_inc}个`\n>`（引出译文）和{expected_inc - 1}个`\n---\n`（分隔每段）以及一个单独的`\n---`（做结尾）──在你输出的内容中，不会出现`\n\n`的双换行符──即你不应该输出空行！。"
                    f"输出内容会以第一段原文直接开头；原文和译文你都需要输出，原文的所有内容你原封不动地保留，一点也不可以落下。"
                )
                if should_add_no_blank_line_hint:
                    extra_instruction += "不要输出空行。"
                extra_instruction += _build_retry_feedback_block(
                    last_failed_output, last_failure_reasons
                )
                result, used_model = translate_paragraph_batch(
                    chunk,
                    prompt_text,
                    extra_instruction=extra_instruction,
                    preferred_model=current_model,
                )
                # If this batch switched to fallback model, keep using it for retries of this batch.
                current_model = used_model

                sep_count, block_error, has_blank_line = _validate_batch_blocks_two_lines(result)
                if sep_count != expected_inc or block_error or has_blank_line:
                    reason = []
                    if sep_count != expected_inc:
                        reason.append(
                            f"分割线数量 {sep_count} != 期望 {expected_inc}"
                        )
                    if block_error:
                        reason.append(block_error)
                    if has_blank_line:
                        reason.append("输出中出现空行")
                        should_add_no_blank_line_hint = True
                    reason.extend(
                        _analyze_structure_mismatch_details(result, expected_inc)
                    )
                    last_failed_output = result
                    last_failure_reasons = list(reason)
                    print(
                        "\n批次结构不符合要求，准备重试："
                        + "；".join(reason)
                    )
                    retry_idx += 1
                    continue

                original_mismatch_reasons = _find_original_mismatch_reasons(
                    chunk, result
                )
                if original_mismatch_reasons:
                    last_failed_output = result
                    last_failure_reasons = list(original_mismatch_reasons)
                    if current_chunk_size > 1:
                        next_chunk_size = current_chunk_size - 1
                        print(
                            f"\n批次原文校验失败，准备重试并缩小批次："
                            + "；".join(original_mismatch_reasons)
                            + f"（chunk-size {current_chunk_size} -> {next_chunk_size}）"
                        )
                        current_chunk_size = next_chunk_size
                    else:
                        print(
                            "\n批次原文校验失败，准备重试："
                            + "；".join(original_mismatch_reasons)
                            + "（当前已降到 chunk-size 1）"
                        )
                    retry_idx += 1
                    continue

                heading_mismatch_reasons = _find_heading_tag_mismatch_reasons(
                    chunk, result
                )
                if heading_mismatch_reasons:
                    last_failed_output = result
                    last_failure_reasons = list(heading_mismatch_reasons)
                    print(
                        "\n批次标题标签校验失败，准备重试："
                        + "；".join(heading_mismatch_reasons)
                    )
                    retry_idx += 1
                    continue

                _append_file(out_path, result)

                try:
                    output_text_after_append = _read_file(out_path)
                except UnicodeDecodeError as err:
                    _rollback_file_to_size(out_path, size_before)
                    last_failed_output = result
                    last_failure_reasons = [
                        "输出文件写入后不是合法 UTF-8，已回滚并重试："
                        + _format_decode_error(out_path, err)
                    ]
                    print(
                        "\n输出文件 UTF-8 校验失败，已撤回重试："
                        + _format_decode_error(out_path, err)
                    )
                    retry_idx += 1
                    continue

                new_done = _count_translated_paragraphs(output_text_after_append)
                actual_inc = new_done - done_before
                if actual_inc == expected_inc:
                    start_para = new_done
                    progress.update(num, full_file_total, start_para, total_paras)
                    break

                _rollback_file_to_size(out_path, size_before)
                last_failed_output = result
                last_failure_reasons = [
                    f"批次段落数不一致：输入 {expected_inc} 段，输出 {max(actual_inc, 0)} 段"
                ]
                print(
                    f"\n批次段落数不一致，已撤回重试："
                    f"输入 {expected_inc} 段，输出 {max(actual_inc, 0)} 段。"
                )
                retry_idx += 1

        try:
            final_output_text = _read_file(out_path)
        except UnicodeDecodeError as err:
            raise RuntimeError(_format_decode_error(out_path, err)) from err
        final_done = _count_translated_paragraphs(final_output_text)
        if final_done < total_paras:
            raise RuntimeError(f"文件 {num}.md 段落数未对齐：输出 {final_done} < 输入 {total_paras}")

        progress.update(num, full_file_total, total_paras, total_paras)

    print("\n全部任务完成。")


def process_translation_file(input_file, output_file, prompt_text, chunk_size):
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    output_parent = os.path.dirname(output_file)
    if output_parent:
        os.makedirs(output_parent, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="translation_single_") as tmp_dir:
        temp_input_dir = os.path.join(tmp_dir, "translate-typeset")
        temp_output_dir = os.path.join(tmp_dir, "translate-result")
        os.makedirs(temp_input_dir, exist_ok=True)
        os.makedirs(temp_output_dir, exist_ok=True)

        temp_input_file = os.path.join(temp_input_dir, "1.md")
        with open(input_file, "r", encoding="utf-8") as src, open(
            temp_input_file, "w", encoding="utf-8"
        ) as dst:
            dst.write(src.read())

        process_translation_files(
            input_dir=temp_input_dir,
            output_dir=temp_output_dir,
            prompt_text=prompt_text,
            chunk_size=chunk_size,
            start_idx=1,
            end_idx=1,
        )

        temp_output_file = os.path.join(temp_output_dir, "1.md")
        if not os.path.isfile(temp_output_file):
            raise FileNotFoundError(f"Translated output not found: {temp_output_file}")

        with open(temp_output_file, "r", encoding="utf-8") as src, open(
            output_file, "w", encoding="utf-8"
        ) as dst:
            dst.write(src.read())


def main():
    global FAST_MODE

    print("\n********************************")
    print("*** Markdown Translation Tool ***")
    print("********************************\n")

    parser = argparse.ArgumentParser(description="Translate markdown paragraphs in batches.")
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Book root directory (default: current directory).",
    )
    parser.add_argument(
        "--book-name",
        default=None,
        help="Book name (used to resolve <base-dir>/<book-name>).",
    )
    parser.add_argument(
        "--base-dir-from",
        default=None,
        help="UTF-8 text file containing base directory (first non-empty line).",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Path to input markdown folder (default: <base-dir>/translate-typeset).",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Path to a single input markdown file.",
    )
    parser.add_argument(
        "--input-dir-from",
        default=None,
        help="UTF-8 text file containing input directory (first non-empty line).",
    )
    parser.add_argument(
        "--input-file-from",
        default=None,
        help="UTF-8 text file containing input file path (first non-empty line).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Path to output folder (default: <base-dir>/translate-result).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Path to a single output markdown file.",
    )
    parser.add_argument(
        "--output-dir-from",
        default=None,
        help="UTF-8 text file containing output directory (first non-empty line).",
    )
    parser.add_argument(
        "--output-file-from",
        default=None,
        help="UTF-8 text file containing output file path (first non-empty line).",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="Start index (inclusive) for numeric markdown filenames.",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="End index (inclusive) for numeric markdown filenames.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5,
        help="Number of paragraphs per API request (default: 5).",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Path to prompt file (default: <skill-dir>/assets/translate_prompt.md).",
    )
    parser.add_argument(
        "--prompt-file-from",
        default=None,
        help="UTF-8 text file containing prompt file path (first non-empty line).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help='Use the Fast service tier (service_tier="fast").',
    )
    args = parser.parse_args()
    FAST_MODE = args.fast

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from
    if args.book_name:
        base_dir = os.path.join(base_dir, args.book_name)

    input_dir = args.input_dir or os.path.join(base_dir, "translate-typeset")
    input_file = args.input_file
    if args.input_dir_from:
        input_dir_from = read_single_path(args.input_dir_from)
        if input_dir_from:
            input_dir = input_dir_from
    if args.input_file_from:
        input_file_from = read_single_path(args.input_file_from)
        if input_file_from:
            input_file = input_file_from

    output_dir = args.output_dir or os.path.join(base_dir, "translate-result")
    output_file = args.output_file
    if args.output_dir_from:
        output_dir_from = read_single_path(args.output_dir_from)
        if output_dir_from:
            output_dir = output_dir_from
    if args.output_file_from:
        output_file_from = read_single_path(args.output_file_from)
        if output_file_from:
            output_file = output_file_from

    prompt_path = args.prompt_file or os.path.join(ASSETS_DIR, "translate_prompt.md")
    if args.prompt_file_from:
        prompt_file_from = read_single_path(args.prompt_file_from)
        if prompt_file_from:
            prompt_path = prompt_file_from

    prompt_text = _load_prompt(prompt_path)

    print(f"Prompt file: {prompt_path}")
    print(f"Paragraphs per request: {args.chunk_size}")
    print(f"File index range: {args.start}-{args.end}")

    if input_file or output_file:
        if not input_file or not output_file:
            raise ValueError("Single-file mode requires both --input-file and --output-file.")
        print(f"Input file: {input_file}")
        print(f"Output file: {output_file}")
        process_translation_file(
            input_file=input_file,
            output_file=output_file,
            prompt_text=prompt_text,
            chunk_size=max(1, int(args.chunk_size)),
        )
        return

    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    process_translation_files(
        input_dir=input_dir,
        output_dir=output_dir,
        prompt_text=prompt_text,
        chunk_size=max(1, int(args.chunk_size)),
        start_idx=args.start,
        end_idx=args.end,
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        print(f"\n错误：{err}")
        sys.exit(1)
