import argparse
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import translation as tr


DEFAULT_BATCH = 10
REQUEST_TIMEOUT_SECONDS = 180
FALLBACK_PROMPT_FILE = "translate_fallback_prompt.md"
SERVER_500_BACKOFF_SECONDS = (5, 10, 20, 40, 60)
SERVER_500_JITTER_RANGE = (0.8, 1.2)
REASONING_EFFORT_CHOICES = ("none", "low", "medium", "high", "xhigh", "max")
DEFAULT_REASONING_EFFORT = "high"
REASONING_EFFORT = DEFAULT_REASONING_EFFORT

_thread_local = threading.local()
_progress_renderer = None


def _reasoning_kwargs(model_name):
    if str(model_name or "").lower().startswith("gpt-5"):
        return {"reasoning_effort": REASONING_EFFORT}
    return {}


def _request_kwargs(model_name):
    kwargs = _reasoning_kwargs(model_name)
    if tr.FAST_MODE and str(model_name or "").lower().startswith("gpt-5"):
        kwargs["service_tier"] = "fast"
    return kwargs


def _get_thread_client():
    if not hasattr(_thread_local, "openai_client"):
        _thread_local.openai_client = tr.OpenAI(
            base_url=tr.OPENAI_BASE_URL,
            api_key=tr.OPENAI_API_KEY,
            max_retries=0,
        )
    return _thread_local.openai_client


def _request_text_once_threadlocal(model_name, request_text, timeout_seconds=None):
    client = _get_thread_client()
    kwargs = {}
    if timeout_seconds is not None:
        kwargs["timeout"] = float(timeout_seconds)
    kwargs.update(_request_kwargs(model_name or tr.OPENAI_MODEL))
    response = client.chat.completions.create(
        model=model_name or tr.OPENAI_MODEL,
        messages=[{"role": "user", "content": request_text}],
        **kwargs,
    )
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
    raise tr.EmptyResponseError("OpenAI API 返回空文本")


def _request_text_once_openai_threadlocal(request_text):
    if not tr.OPENAI_BASE_URL or not tr.OPENAI_API_KEY or not tr.OPENAI_MODEL:
        raise RuntimeError(
            "secrets_openai.txt missing required values: base_url, api_key, or model."
        )
    return _request_text_once_threadlocal(tr.OPENAI_MODEL, request_text)


def _wait_with_terminal_hint_threadsafe(seconds, reason_text):
    seconds = max(1, int(seconds))
    if _progress_renderer is not None:
        _progress_renderer.log(
            f"检测到配额限制，暂停 {seconds} 秒后自动重试。原因: {reason_text}"
        )
    else:
        print(f"\n检测到配额限制，暂停 {seconds} 秒后自动重试。")
    time.sleep(seconds)
    if _progress_renderer is not None:
        _progress_renderer.log("已到重试时间，继续请求。")
    else:
        print("已到重试时间，继续请求。")


def _install_threadsafe_translation_hooks():
    tr._request_text_once = _request_text_once_threadlocal
    tr._request_text_once_openai = _request_text_once_openai_threadlocal
    tr._wait_with_terminal_hint = _wait_with_terminal_hint_threadsafe


def _format_progress_line(file_label, file_pos, file_total, para_done, para_total, status):
    para_total = max(para_total, 1)
    para_done = min(max(para_done, 0), para_total)
    ratio = para_done / para_total
    filled = int(round(40 * ratio))
    bar = "#" * filled + "-" * (40 - filled)
    label = f"{file_label} " if file_label else ""
    return (
        f"{label}Files [{file_pos}/{file_total}] "
        f"Paras [{para_done}/{para_total}] "
        f"[{bar}] [{ratio * 100:6.2f}%] [{status}]"
    )


class MultiProgress:
    def __init__(self):
        self._lock = threading.RLock()
        self._rows = {}
        self._rendered_lines = 0
        self._inited = False

    def _clear_rendered(self):
        if self._inited and self._rendered_lines > 0:
            sys.stdout.write(f"\033[{self._rendered_lines}F")
            sys.stdout.write("\033[J")

    def _render_unlocked(self):
        lines = []
        for slot in sorted(self._rows):
            row = self._rows[slot]
            lines.append(
                _format_progress_line(
                    row.get("file_label", ""),
                    row["file_pos"],
                    row["file_total"],
                    row["para_done"],
                    row["para_total"],
                    row["status"],
                )
            )

        self._clear_rendered()
        if lines:
            sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self._rendered_lines = len(lines)
        self._inited = True

    def update(self, slot, file_pos, file_total, para_done, para_total, status, file_label=""):
        with self._lock:
            self._rows[slot] = {
                "file_pos": file_pos,
                "file_total": file_total,
                "para_done": para_done,
                "para_total": para_total,
                "status": status,
                "file_label": file_label,
            }
            self._render_unlocked()

    def remove(self, slot):
        with self._lock:
            self._rows.pop(slot, None)
            self._render_unlocked()

    def log(self, message):
        with self._lock:
            self._clear_rendered()
            sys.stdout.write(str(message).rstrip() + "\n")
            self._rendered_lines = 0
            self._inited = False
            self._render_unlocked()


def _build_extra_instruction(expected_inc, no_blank_hint, failed_output, failure_reasons):
    extra_instruction = (
        f"一个`\n`代表一个换行符，一个`>`代表一个引用符号，一个`---`代表一个分隔符。每次分段你都需要使用一个换行符，请参考示例。你需要处理的文本有{expected_inc}段！"
        f"你必须输出{expected_inc}段，你绝对不可以乱合并。如果你正确分段换行的话，你输出的内容会有且只有──{expected_inc}个`\n>`（引出译文）和{expected_inc - 1}个`\n---\n`（分隔每段）以及一个单独的`\n---`（做结尾）──在你输出的内容中，不会出现`\n\n`的双换行符──即你不应该输出空行！。"
        f"输出内容会以第一段原文直接开头；原文和译文你都需要输出，原文的所有内容你原封不动地保留，一点也不可以落下。"
    )
    if no_blank_hint:
        extra_instruction += "不要输出空行。"
    extra_instruction += tr._build_retry_feedback_block(failed_output, failure_reasons)
    return extra_instruction


def _is_timeout_error(err):
    name = type(err).__name__.lower()
    text = str(err).lower()
    return "timeout" in name or "timed out" in text


def _is_content_filter_error(err):
    reason = tr._extract_finish_reason_from_error_text(str(err))
    return reason == "CONTENT_FILTER"


def _is_server_500_error(err):
    status_code = getattr(err, "status_code", None)
    if status_code == 500:
        return True
    response = getattr(err, "response", None)
    if getattr(response, "status_code", None) == 500:
        return True
    return bool(re.search(r"(?:error\s+code|status(?:_code)?)\s*[:=]\s*500\b", str(err), re.I))


def _wait_for_server_500_retry(failure_count, progress, file_label, phase):
    base_delay = SERVER_500_BACKOFF_SECONDS[failure_count - 1]
    jitter = random.uniform(*SERVER_500_JITTER_RANGE)
    delay = max(1.0, base_delay * jitter)
    progress.log(
        f"{file_label} {phase}遇到 HTTP 500；"
        f"{delay:.1f} 秒后重试（指数退避基础 {base_delay} 秒，含随机抖动）。"
    )
    time.sleep(delay)


def _load_fallback_prompt():
    path = os.path.join(tr.ASSETS_DIR, FALLBACK_PROMPT_FILE)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    return (
        "请把下方段落逐段翻译成中文。只输出中文译文，不要复述原文。"
        "每段译文必须以 > 开头，各段之间用单独一行 --- 分隔，结尾也要有 ---。"
    )


def _build_standard_request(paragraphs, prompt_text, extra_instruction=""):
    payload_text = "\n\n".join(paragraphs)
    extra_block = ""
    if extra_instruction.strip():
        extra_block = "\n\n分段要求（必须严格遵守）：\n" + extra_instruction.strip()
    return (
        prompt_text.strip()
        + extra_block
        + "\n\n"
        + "以下是需要翻译的段落（按段落空行分隔）：\n\n"
        + payload_text
    )


def _build_fallback_request(paragraphs, fallback_prompt, expected_inc):
    payload_text = "\n\n".join(paragraphs)
    return (
        fallback_prompt.strip()
        + "\n\n"
        + f"本次共有 {expected_inc} 段。只输出 {expected_inc} 段中文译文。"
        + "不要输出原文，不要输出空行，不要用代码块包裹。"
        + "\n\n以下是需要翻译的段落（按段落空行分隔）：\n\n"
        + payload_text
    )


def _parse_fallback_translations(output_text, expected_inc):
    lines = output_text.splitlines()
    blocks = []
    current = []
    has_blank_line = False
    first_error = ""

    for line in lines:
        if not line.strip():
            has_blank_line = True
        if line.strip() == "---":
            non_empty = [x.strip() for x in current if x.strip()]
            blocks.append(non_empty)
            current = []
            continue
        current.append(line)

    if any(x.strip() for x in current):
        first_error = "回退输出最后一个分割线后仍有未闭合内容"

    if len(blocks) != expected_inc and not first_error:
        first_error = f"回退输出分割块数 {len(blocks)} != 期望 {expected_inc}"

    translations = []
    if not first_error:
        for idx, block in enumerate(blocks, 1):
            if len(block) != 1:
                first_error = f"回退输出第 {idx} 段包含 {len(block)} 行译文（应为 1 行）"
                break
            if not block[0].startswith(">"):
                first_error = f"回退输出第 {idx} 段译文没有以 > 开头"
                break
            translations.append(block[0])

    return translations, first_error, has_blank_line


def _compose_bilingual_output(originals, translations):
    parts = []
    for original, translation in zip(originals, translations):
        parts.append(original.rstrip() + "\n" + translation.rstrip() + "\n---")
    return "\n".join(parts)


def _request_with_fast_timeout_fallback(
    paragraphs,
    prompt_text,
    extra_instruction,
    preferred_model,
    expected_inc,
    progress,
    file_label,
):
    model = preferred_model or tr.MODEL
    request_text = _build_standard_request(paragraphs, prompt_text, extra_instruction)
    last_error = None
    empty_count = 0
    has_non_empty_error = False
    ordinary_failures = 0
    server_500_failures = 0

    while True:
        try:
            text = _request_text_once_threadlocal(
                model, request_text, timeout_seconds=REQUEST_TIMEOUT_SECONDS
            )
            return text, model, False
        except Exception as err:
            last_error = err
            if _is_content_filter_error(err):
                progress.log(
                    f"{file_label} 常规双语请求触发 finishReason=CONTENT_FILTER，"
                    "切换到中文-only 回退。"
                )
                return _request_fallback_translation(
                    paragraphs, model, expected_inc, progress, file_label
                )
            if _is_timeout_error(err):
                progress.log(
                    f"{file_label} 批次 {REQUEST_TIMEOUT_SECONDS} 秒未返回，切换到中文-only 回退。"
                )
                return _request_fallback_translation(
                    paragraphs, model, expected_inc, progress, file_label
                )
            if _is_server_500_error(err):
                server_500_failures += 1
                if server_500_failures <= len(SERVER_500_BACKOFF_SECONDS):
                    _wait_for_server_500_retry(
                        server_500_failures, progress, file_label, "常规双语请求"
                    )
                    continue
                break

            ordinary_failures += 1
            if isinstance(err, tr.EmptyResponseError):
                empty_count += 1
            else:
                has_non_empty_error = True
                err_text = str(err)
                if "429" in err_text or "RATE_LIMIT" in err_text.upper():
                    retry_after = tr._extract_retry_delay_seconds(err_text)
                    if retry_after:
                        if ordinary_failures >= 5:
                            break
                        _wait_with_terminal_hint_threadsafe(
                            retry_after, "OpenAI 429 / RATE_LIMIT"
                        )
                        continue
            if ordinary_failures >= 5:
                break
            time.sleep(1 if empty_count and not has_non_empty_error else 2)

    if server_500_failures > len(SERVER_500_BACKOFF_SECONDS):
        detail = "连续 6 次 HTTP 500（已按 5/10/20/40/60 秒指数退避）"
    else:
        detail = "普通错误重试 5 次"
    raise RuntimeError(f"翻译失败（模型 {model}，{detail}后仍失败）: {last_error}")


def _request_fallback_translation(paragraphs, model, expected_inc, progress, file_label):
    fallback_prompt = _load_fallback_prompt()
    request_text = _build_fallback_request(paragraphs, fallback_prompt, expected_inc)
    last_error = None
    last_output = ""
    format_failures = 0
    ordinary_failures = 0
    server_500_failures = 0

    while True:
        try:
            text = _request_text_once_threadlocal(
                model, request_text, timeout_seconds=REQUEST_TIMEOUT_SECONDS
            )
        except Exception as err:
            last_error = err
            if _is_server_500_error(err):
                server_500_failures += 1
                if server_500_failures <= len(SERVER_500_BACKOFF_SECONDS):
                    _wait_for_server_500_retry(
                        server_500_failures, progress, file_label, "中文-only 回退"
                    )
                    continue
                raise RuntimeError(
                    f"中文-only 回退失败（模型 {model}，连续 6 次 HTTP 500）: {last_error}"
                ) from err
            ordinary_failures += 1
            if ordinary_failures < 3:
                time.sleep(2)
                continue
            raise RuntimeError(f"中文-only 回退失败（模型 {model}）: {last_error}") from err

        translations, block_error, has_blank_line = _parse_fallback_translations(
            text, expected_inc
        )
        if translations and not block_error and not has_blank_line:
            progress.log(f"{file_label} 已用中文-only 回退完成当前批次。")
            return _compose_bilingual_output(paragraphs, translations), model, True

        reasons = []
        if block_error:
            reasons.append(block_error)
        if has_blank_line:
            reasons.append("回退输出中出现空行")
        last_output = text
        progress.log(
            f"{file_label} 中文-only 回退格式不符合要求，准备重试："
            + "；".join(reasons)
        )
        format_failures += 1
        if format_failures >= 3:
            break

    raise RuntimeError(
        "中文-only 回退失败："
        + (f"最后输出片段：{last_output[:300]}" if last_output else str(last_error))
    )


def _select_pending_files(input_dir, output_dir, start_idx=None, end_idx=None):
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)
    files = tr._list_input_markdown_files(input_dir)
    pending = []
    all_file_nums = []

    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not stem.isdigit():
            continue
        num = int(stem)
        if start_idx is not None and num < start_idx:
            continue
        if end_idx is not None and num > end_idx:
            continue
        all_file_nums.append(num)

        input_paras = tr._split_paragraphs(tr._read_file(path))
        total_paras = len(input_paras)
        out_path = os.path.join(output_dir, f"{num}.md")
        try:
            output_text = tr._read_file(out_path)
        except UnicodeDecodeError as err:
            raise RuntimeError(tr._format_decode_error(out_path, err)) from err
        done_paras = tr._count_translated_paragraphs(output_text)
        if total_paras == 0 or done_paras >= total_paras:
            continue
        pending.append(
            {
                "num": num,
                "in_path": path,
                "out_path": out_path,
                "input_paras": input_paras,
                "total_paras": total_paras,
                "done_paras": done_paras,
            }
        )

    full_file_total = max(all_file_nums) if all_file_nums else 0
    return pending, full_file_total


def _split_path_args(values):
    paths = []
    for value in values or []:
        if not value:
            continue
        for part in re.split(r"[;,]", value):
            part = part.strip().strip('"')
            if part:
                paths.append(part)
    return paths


def _read_path_list(path):
    if not path:
        return []
    text = tr._read_file(path)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _build_explicit_file_jobs(input_files, output_files, output_dir):
    if not input_files:
        return [], 0

    if output_files and len(output_files) != len(input_files):
        raise ValueError(
            "Multiple-file mode requires --output-file count to match --input-file count, "
            "or omit --output-file and use --output-dir."
        )

    os.makedirs(output_dir, exist_ok=True)
    pending = []
    for idx, in_path in enumerate(input_files, start=1):
        if not os.path.isfile(in_path):
            raise FileNotFoundError(f"Input file not found: {in_path}")

        if output_files:
            out_path = output_files[idx - 1]
        else:
            out_path = os.path.join(output_dir, os.path.basename(in_path))

        output_parent = os.path.dirname(out_path)
        if output_parent:
            os.makedirs(output_parent, exist_ok=True)

        input_paras = tr._split_paragraphs(tr._read_file(in_path))
        total_paras = len(input_paras)
        try:
            output_text = tr._read_file(out_path)
        except UnicodeDecodeError as err:
            raise RuntimeError(tr._format_decode_error(out_path, err)) from err
        done_paras = tr._count_translated_paragraphs(output_text)
        if total_paras == 0 or done_paras >= total_paras:
            continue

        pending.append(
            {
                "num": idx,
                "display_name": os.path.basename(in_path),
                "in_path": in_path,
                "out_path": out_path,
                "input_paras": input_paras,
                "total_paras": total_paras,
                "done_paras": done_paras,
            }
        )

    return pending, len(input_files)


def _translate_one_file(job, prompt_text, chunk_size, progress, slot):
    num = job["num"]
    display_name = job.get("display_name", f"{num}.md")
    out_path = job["out_path"]
    input_paras = job["input_paras"]
    total_paras = job["total_paras"]
    start_para = job["done_paras"]
    file_pos = job["file_pos"]
    file_total = job["file_total"]

    progress.update(
        slot, file_pos, file_total, start_para, total_paras, "RUNNING", display_name
    )

    while start_para < total_paras:
        current_model = tr.MODEL
        should_add_no_blank_line_hint = False
        last_failed_output = ""
        last_failure_reasons = []
        current_chunk_size = max(1, int(chunk_size))

        while True:
            chunk = input_paras[start_para : start_para + current_chunk_size]
            expected_inc = len(chunk)
            size_before = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
            done_before = start_para

            extra_instruction = _build_extra_instruction(
                expected_inc,
                should_add_no_blank_line_hint,
                last_failed_output,
                last_failure_reasons,
            )
            result, used_model, used_fallback = _request_with_fast_timeout_fallback(
                chunk,
                prompt_text,
                extra_instruction,
                current_model,
                expected_inc,
                progress,
                display_name,
            )
            current_model = used_model

            sep_count, block_error, has_blank_line = tr._validate_batch_blocks_two_lines(
                result
            )
            if sep_count != expected_inc or block_error or has_blank_line:
                reason = []
                if sep_count != expected_inc:
                    reason.append(f"分割线数量 {sep_count} != 期望 {expected_inc}")
                if block_error:
                    reason.append(block_error)
                if has_blank_line:
                    reason.append("输出中出现空行")
                    should_add_no_blank_line_hint = True
                reason.extend(tr._analyze_structure_mismatch_details(result, expected_inc))
                last_failed_output = result
                last_failure_reasons = list(reason)
                progress.log(f"{display_name} 批次结构不符合要求，准备重试：" + "；".join(reason))
                continue

            original_mismatch_reasons = tr._find_original_mismatch_reasons(chunk, result)
            if original_mismatch_reasons:
                last_failed_output = result
                last_failure_reasons = list(original_mismatch_reasons)
                if current_chunk_size > 1:
                    next_chunk_size = current_chunk_size - 1
                    progress.log(
                        f"{display_name} 批次原文校验失败，准备重试并缩小批次："
                        + "；".join(original_mismatch_reasons)
                        + f"（chunk-size {current_chunk_size} -> {next_chunk_size}）"
                    )
                    current_chunk_size = next_chunk_size
                else:
                    progress.log(
                        f"{display_name} 批次原文校验失败，准备重试："
                        + "；".join(original_mismatch_reasons)
                        + "（当前已降到 chunk-size 1）"
                    )
                continue

            heading_mismatch_reasons = tr._find_heading_tag_mismatch_reasons(chunk, result)
            if heading_mismatch_reasons:
                last_failed_output = result
                last_failure_reasons = list(heading_mismatch_reasons)
                progress.log(
                    f"{display_name} 批次标题标签校验失败，准备重试："
                    + "；".join(heading_mismatch_reasons)
                )
                continue

            tr._append_file(out_path, result)

            try:
                output_text_after_append = tr._read_file(out_path)
            except UnicodeDecodeError as err:
                tr._rollback_file_to_size(out_path, size_before)
                last_failed_output = result
                last_failure_reasons = [
                    "输出文件写入后不是合法 UTF-8，已回滚并重试："
                    + tr._format_decode_error(out_path, err)
                ]
                progress.log(
                    f"{display_name} 输出文件 UTF-8 校验失败，已撤回重试："
                    + tr._format_decode_error(out_path, err)
                )
                continue

            new_done = tr._count_translated_paragraphs(output_text_after_append)
            actual_inc = new_done - done_before
            if actual_inc == expected_inc:
                start_para = new_done
                progress.update(
                    slot,
                    file_pos,
                    file_total,
                    start_para,
                    total_paras,
                    "RUNNING",
                    display_name,
                )
                break

            tr._rollback_file_to_size(out_path, size_before)
            last_failed_output = result
            last_failure_reasons = [
                f"批次段落数不一致：输入 {expected_inc} 段，输出 {max(actual_inc, 0)} 段"
            ]
            progress.log(
                f"{display_name} 批次段落数不一致，已撤回重试："
                f"输入 {expected_inc} 段，输出 {max(actual_inc, 0)} 段。"
            )

    try:
        final_output_text = tr._read_file(out_path)
    except UnicodeDecodeError as err:
        raise RuntimeError(tr._format_decode_error(out_path, err)) from err
    final_done = tr._count_translated_paragraphs(final_output_text)
    if final_done < total_paras:
        raise RuntimeError(f"文件 {display_name} 段落数未对齐：输出 {final_done} < 输入 {total_paras}")

    progress.update(
        slot, file_pos, file_total, total_paras, total_paras, "OVER", display_name
    )
    return num


def _run_fast_translation_jobs(pending, full_file_total, prompt_text, chunk_size, max_files):
    global _progress_renderer

    if not pending:
        print("No files to translate in current range.")
        return

    pending_total = len(pending)
    for idx, job in enumerate(pending, start=1):
        job.setdefault("file_pos", job.get("num", idx))
        job.setdefault("file_total", full_file_total or pending_total)
        job.setdefault("display_name", f"{job.get('num', idx)}.md")

    active_count = max(1, min(int(max_files), pending_total))
    progress = MultiProgress()
    _progress_renderer = progress

    print(f"Pending files: {pending_total}")
    print(f"Full file count: {full_file_total}")
    print(f"Active file limit: {active_count}")

    failures = []
    next_job_idx = 0
    futures = {}

    with ThreadPoolExecutor(max_workers=active_count) as executor:
        for slot in range(active_count):
            if next_job_idx >= pending_total:
                break
            job = pending[next_job_idx]
            next_job_idx += 1
            futures[executor.submit(_translate_one_file, job, prompt_text, chunk_size, progress, slot)] = (
                slot,
                job,
            )

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                slot, job = futures.pop(future)
                try:
                    future.result()
                except Exception as err:
                    display_name = job.get("display_name", f"{job['num']}.md")
                    progress.update(
                        slot,
                        job["file_pos"],
                        job["file_total"],
                        job["done_paras"],
                        job["total_paras"],
                        "ERROR",
                        display_name,
                    )
                    failures.append((display_name, err))
                    progress.log(f"{display_name} 处理失败：{err}")

                if next_job_idx < pending_total:
                    next_job = pending[next_job_idx]
                    next_job_idx += 1
                    futures[
                        executor.submit(
                            _translate_one_file,
                            next_job,
                            prompt_text,
                            chunk_size,
                            progress,
                            slot,
                        )
                    ] = (slot, next_job)
                else:
                    if not failures or slot not in [s for s, _ in futures.values()]:
                        time.sleep(0.2)
                        progress.remove(slot)

    _progress_renderer = None
    if failures:
        failed_names = ", ".join(name for name, _ in failures)
        raise RuntimeError(f"{len(failures)} 个文件处理失败：{failed_names}")

    print("\n全部任务完成。")


def process_fast_translation_files(
    input_dir,
    output_dir,
    prompt_text,
    chunk_size,
    start_idx=None,
    end_idx=None,
    max_files=DEFAULT_BATCH,
):
    pending, full_file_total = _select_pending_files(
        input_dir, output_dir, start_idx, end_idx
    )
    _run_fast_translation_jobs(pending, full_file_total, prompt_text, chunk_size, max_files)


def process_fast_translation_books(
    base_dir,
    book_names,
    prompt_text,
    chunk_size,
    start_idx=None,
    end_idx=None,
    max_files=DEFAULT_BATCH,
):
    all_pending = []
    for book_name in book_names:
        book_base_dir = os.path.join(base_dir, book_name)
        input_dir = os.path.join(book_base_dir, "translate-typeset")
        output_dir = os.path.join(book_base_dir, "translate-result")
        print(f"Book: {book_name}")
        print(f"  Input directory: {input_dir}")
        print(f"  Output directory: {output_dir}")
        pending, _ = _select_pending_files(input_dir, output_dir, start_idx, end_idx)
        for job in pending:
            job["book_name"] = book_name
            job["display_name"] = f"{book_name}/{job['num']}.md"
            all_pending.append(job)

    for idx, job in enumerate(all_pending, start=1):
        job["file_pos"] = idx
        job["file_total"] = len(all_pending)

    _run_fast_translation_jobs(
        all_pending,
        len(all_pending),
        prompt_text,
        chunk_size,
        max_files,
    )


def process_fast_translation_file(input_file, output_file, prompt_text, chunk_size):
    jobs, full_file_total = _build_explicit_file_jobs(
        [input_file], [output_file], os.path.dirname(output_file) or os.getcwd()
    )
    _run_fast_translation_jobs(jobs, full_file_total, prompt_text, chunk_size, 1)


def process_fast_translation_file_list(
    input_files,
    output_files,
    output_dir,
    prompt_text,
    chunk_size,
    max_files=DEFAULT_BATCH,
):
    jobs, full_file_total = _build_explicit_file_jobs(input_files, output_files, output_dir)
    _run_fast_translation_jobs(jobs, full_file_total, prompt_text, chunk_size, max_files)


def main():
    global REASONING_EFFORT

    _install_threadsafe_translation_hooks()

    print("\n********************************")
    print("*** Fast Markdown Translation ***")
    print("********************************\n")

    parser = argparse.ArgumentParser(
        description="Translate markdown paragraphs with configurable active file progress bars."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Book root directory (default: current directory).",
    )
    parser.add_argument(
        "--book-name",
        nargs="+",
        default=None,
        help="Book name(s), used to resolve <base-dir>/<book-name>. Multiple names share one batch pool.",
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
        action="append",
        default=[],
        help="Path to input markdown file. Repeat for multiple files, or separate paths with ; or ,.",
    )
    parser.add_argument(
        "--input-dir-from",
        default=None,
        help="UTF-8 text file containing input directory (first non-empty line).",
    )
    parser.add_argument(
        "--input-file-from",
        default=None,
        help="UTF-8 text file containing input file paths, one per line.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Path to output folder (default: <base-dir>/translate-result).",
    )
    parser.add_argument(
        "--output-file",
        action="append",
        default=[],
        help="Path to output markdown file. Repeat to match --input-file, or omit and use --output-dir.",
    )
    parser.add_argument(
        "--output-dir-from",
        default=None,
        help="UTF-8 text file containing output directory (first non-empty line).",
    )
    parser.add_argument(
        "--output-file-from",
        default=None,
        help="UTF-8 text file containing output file paths, one per line.",
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
        "--batch",
        type=int,
        default=DEFAULT_BATCH,
        help="Maximum active files at once (default: 10).",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default=DEFAULT_REASONING_EFFORT,
        help="GPT-5 reasoning effort (default: high).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help='Use the Fast service tier (service_tier="fast").',
    )
    parser.add_argument(
        "--max-files",
        type=int,
        dest="batch",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    REASONING_EFFORT = args.reasoning_effort
    tr.FAST_MODE = args.fast

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = tr.read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from

    book_names = args.book_name or [None]

    input_files = _split_path_args(args.input_file)
    if args.input_dir_from:
        input_dir_from = tr.read_single_path(args.input_dir_from)
    if args.input_file_from:
        input_files.extend(_read_path_list(args.input_file_from))

    output_files = _split_path_args(args.output_file)
    if args.output_dir_from:
        output_dir_from = tr.read_single_path(args.output_dir_from)
    if args.output_file_from:
        output_files.extend(_read_path_list(args.output_file_from))

    prompt_path = args.prompt_file or os.path.join(tr.ASSETS_DIR, "translate_prompt.md")
    if args.prompt_file_from:
        prompt_file_from = tr.read_single_path(args.prompt_file_from)
        if prompt_file_from:
            prompt_path = prompt_file_from

    prompt_text = tr._load_prompt(prompt_path)

    print(f"Prompt file: {prompt_path}")
    print(f"Model: {tr.OPENAI_MODEL}")
    print(f"Reasoning effort: {REASONING_EFFORT}")
    print(f"Fast mode: {'enabled' if tr.FAST_MODE else 'disabled'}")
    print(f"Paragraphs per request: {args.chunk_size}")
    print(f"File index range: {args.start}-{args.end}")

    multiple_books = len(book_names) > 1
    if multiple_books and (
        args.input_dir
        or args.input_dir_from
        or args.output_dir
        or args.output_dir_from
        or input_files
        or output_files
    ):
        raise RuntimeError(
            "Multiple --book-name mode uses each book's default translate-typeset/translate-result directories; "
            "do not combine it with explicit input/output file or directory options."
        )

    if input_files or output_files:
        input_dir = args.input_dir or os.path.join(base_dir, "translate-typeset")
        if args.input_dir_from and input_dir_from:
            input_dir = input_dir_from
        output_dir = args.output_dir or os.path.join(base_dir, "translate-result")
        if args.output_dir_from and output_dir_from:
            output_dir = output_dir_from
        if not input_files:
            raise ValueError("Explicit file mode requires at least one --input-file.")
        if output_files and len(output_files) != len(input_files):
            raise ValueError(
                "When --output-file is provided, its count must match --input-file."
            )
        print(f"Input files: {len(input_files)}")
        if output_files:
            print(f"Output files: {len(output_files)}")
        else:
            print(f"Output directory: {output_dir}")
        process_fast_translation_file_list(
            input_files=input_files,
            output_files=output_files,
            output_dir=output_dir,
            prompt_text=prompt_text,
            chunk_size=max(1, int(args.chunk_size)),
            max_files=args.batch,
        )
        return

    if multiple_books:
        process_fast_translation_books(
            base_dir=base_dir,
            book_names=book_names,
            prompt_text=prompt_text,
            chunk_size=max(1, int(args.chunk_size)),
            start_idx=args.start,
            end_idx=args.end,
            max_files=args.batch,
        )
        return

    for idx, book_name in enumerate(book_names, start=1):
        book_base_dir = os.path.join(base_dir, book_name) if book_name else base_dir
        input_dir = args.input_dir or os.path.join(book_base_dir, "translate-typeset")
        if args.input_dir_from and input_dir_from:
            input_dir = input_dir_from
        output_dir = args.output_dir or os.path.join(book_base_dir, "translate-result")
        if args.output_dir_from and output_dir_from:
            output_dir = output_dir_from

        print(f"Input directory: {input_dir}")
        print(f"Output directory: {output_dir}")
        process_fast_translation_files(
            input_dir=input_dir,
            output_dir=output_dir,
            prompt_text=prompt_text,
            chunk_size=max(1, int(args.chunk_size)),
            start_idx=args.start,
            end_idx=args.end,
            max_files=args.batch,
        )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        print(f"\n错误：{err}")
        sys.exit(1)
