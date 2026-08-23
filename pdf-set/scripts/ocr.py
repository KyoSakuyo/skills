import os
import sys
import time
import re
import base64
from datetime import datetime
import glob
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
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
FALLBACK_MODEL = "claude-sonnet-4-6"
DEFAULT_BATCH = 3
REASONING_EFFORT_CHOICES = ("none", "low", "medium", "high", "xhigh", "max")
DEFAULT_REASONING_EFFORT = "high"
REASONING_EFFORT = DEFAULT_REASONING_EFFORT
FAST_MODE = False

if not BASE_URL or not API_KEY or not MODEL:
    print("secrets_openai.txt missing required values: base_url, api_key, or model.")
    sys.exit(1)

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)


def _reasoning_kwargs(model_name):
    if str(model_name or "").lower().startswith("gpt-5"):
        return {"reasoning_effort": REASONING_EFFORT}
    return {}


def _request_kwargs(model_name):
    kwargs = _reasoning_kwargs(model_name)
    if FAST_MODE and str(model_name or "").lower().startswith("gpt-5"):
        kwargs["service_tier"] = "fast"
    return kwargs
 
def countdown_timer(seconds):
    """
    Display a countdown timer.
    """
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\rWaiting for {remaining} seconds...  ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\rWait complete!            \n")
    sys.stdout.flush()
 
def update_progress(completed, total):
    """
    Displays a simple single-line progress bar in the console.
    """
    if total <= 0:
        return
    bar_length = 50
    progress = completed / total
    block = int(round(bar_length * progress))
    bar = "#" * block + "-" * (bar_length - block)
    pct = round(progress * 100, 2)
    status = "OVER" if completed >= total else "RUNNING"
    text = f"[{completed}/{total}][{bar}][{pct:.2f}%][{status}]"
    sys.stdout.write("\r\033[K" + text)
    sys.stdout.flush()
    if completed >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()
 
def _read_image_bytes(image_path):
    with open(image_path, "rb") as f:
        return f.read()


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


def _extract_text_from_response(response):
    try:
        message = response.choices[0].message
    except Exception:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if not content:
        return ""
    texts = []
    for part in content:
        text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _get_finish_reason(response):
    try:
        choice = response.choices[0]
    except Exception:
        return ""
    for attr in ("finish_reason", "finishReason"):
        val = getattr(choice, attr, None)
        if val:
            return str(val)
    if isinstance(choice, dict):
        return choice.get("finishReason") or choice.get("finish_reason") or ""
    for method in ("model_dump", "to_dict"):
        if hasattr(response, method):
            try:
                data = getattr(response, method)()
                choice0 = (data.get("choices") or [None])[0] or {}
                return choice0.get("finishReason") or choice0.get("finish_reason") or ""
            except Exception:
                pass
    return ""

def read_single_path(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            value = line.strip()
            if value:
                return value
    return ""


def find_max_index(output_dir):
    """
    Find the last continuous numeric index starting from 0 in output_dir.
    Returns -1 if 0 is missing or directory doesn't exist.
    """
    if not os.path.isdir(output_dir):
        return -1
    nums = set()
    for name in os.listdir(output_dir):
        if name.endswith(".md"):
            stem = os.path.splitext(name)[0]
            if stem.endswith(".fail"):
                stem = stem[:-5]
            if stem.isdigit():
                nums.add(int(stem))
    idx = 0
    while idx in nums:
        idx += 1
    return idx - 1


def find_max_image_index(images_dir):
    """
    Find the maximum numeric index from image filenames in images_dir.
    Returns -1 if no numeric image files are found.
    """
    if not os.path.isdir(images_dir):
        return -1
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
    max_idx = -1
    for name in os.listdir(images_dir):
        if name.lower().endswith(exts):
            stem = os.path.splitext(name)[0]
            if stem.isdigit():
                max_idx = max(max_idx, int(stem))
    return max_idx


def _load_prompt(prompt_path):
    if prompt_path and os.path.isfile(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    return "Extract and transcribe any visible text from this image, exactly as it appears."


def extract_text_from_openai_api(image_path, page_num, prompt_text, model_name=None):
    """
    Sends the image to an OpenAI-compatible API and retrieves the extracted text.
    Added detailed logging and error information.
    """
    prohibited_sentinel = "__PROHIBITED_CONTENT__"
    selected_model = model_name or MODEL
    last_error_message = None
    for attempt in range(1, 6):
        try:
            image_bytes = _read_image_bytes(image_path)
            image_filename = os.path.basename(image_path)
            mime_type = _guess_mime_type(image_path)
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "text", "text": f"文件名：{image_filename}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        },
                    ],
                }
            ]
            response = client.chat.completions.create(
                model=selected_model,
                messages=messages,
                **_request_kwargs(selected_model),
            )

            finish_reason = _get_finish_reason(response)
            if finish_reason and "CONTENT_FILTER" in finish_reason.upper():
                return prohibited_sentinel
            if finish_reason and "PROHIBITED_CONTENT" in finish_reason.upper():
                return prohibited_sentinel

            content_text = _extract_text_from_response(response)
            if content_text:
                return content_text

        except Exception as e:
            error_message = f"\nError processing page {page_num}:\n"
            error_message += f"Error Type: {type(e).__name__}\n"
            error_message += f"Error Message: {str(e)}\n"

            if hasattr(e, 'status_code'):
                error_message += f"Status Code: {e.status_code}\n"
            if hasattr(e, 'response'):
                error_message += f"Response: {e.response}\n"
            if hasattr(e, 'details'):
                error_message += f"Details: {e.details}\n"
            last_error_message = error_message
            if attempt >= 5:
                if last_error_message:
                    print(last_error_message)
                raise RuntimeError(last_error_message or error_message) from e

        if attempt < 5:
            delay = 2.0
            time.sleep(delay)

    return None


def extract_text_with_fallback_model(image_path, page_num, prompt_text):
    text = extract_text_from_openai_api(image_path, page_num, prompt_text, model_name=MODEL)
    if text == "__PROHIBITED_CONTENT__":
        text = extract_text_from_openai_api(image_path, page_num, prompt_text, model_name=FALLBACK_MODEL)
    return text


def _list_image_files(images_dir, start_idx=None, end_idx=None):
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff", "*.webp")
    image_files = []
    for ext in exts:
        image_files.extend(glob.glob(os.path.join(images_dir, ext)))
    if start_idx is not None and end_idx is not None:
        filtered = []
        for path in image_files:
            name = os.path.splitext(os.path.basename(path))[0]
            if name.isdigit():
                num = int(name)
                if start_idx <= num <= end_idx:
                    filtered.append(path)
        image_files = filtered
    return sorted(
        image_files,
        key=lambda p: int(os.path.splitext(os.path.basename(p))[0])
        if os.path.splitext(os.path.basename(p))[0].isdigit()
        else os.path.basename(p),
    )


def _build_image_jobs(
    images_dir,
    output_dir,
    start_idx=None,
    end_idx=None,
    label_prefix="",
    skip_existing=True,
):
    if not os.path.isdir(images_dir):
        print(f"Images directory not found: {images_dir}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    image_files = _list_image_files(images_dir, start_idx=start_idx, end_idx=end_idx)
    if not image_files:
        print(f"No images found in current range: {images_dir}")
        return []

    jobs = []
    for seq, image_path in enumerate(image_files, start=1):
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        if skip_existing and (
            os.path.exists(os.path.join(output_dir, f"{base_name}.md"))
            or os.path.exists(os.path.join(output_dir, f"{base_name}.fail.md"))
        ):
            continue
        page_num = int(base_name) if base_name.isdigit() else seq
        label = f"{label_prefix}/{base_name}" if label_prefix else base_name
        jobs.append(
            {
                "image_path": image_path,
                "output_dir": output_dir,
                "base_name": base_name,
                "page_num": page_num,
                "label": label,
            }
        )
    return jobs


def _write_ocr_output(job, text):
    output_dir = job["output_dir"]
    base_name = job["base_name"]
    if text == "__PROHIBITED_CONTENT__":
        out_path = os.path.join(output_dir, f"{base_name}.fail.md")
        with open(out_path, "w", encoding="utf-8") as md_file:
            md_file.write("")
        return False
    if text is None:
        raise RuntimeError(
            f"No content after 5 attempts on page {job['page_num']}. Please intervene."
        )
    out_path = os.path.join(output_dir, f"{base_name}.md")
    with open(out_path, "w", encoding="utf-8") as md_file:
        md_file.write(text)
    return True


def _process_image_job(job, prompt_text):
    text = extract_text_with_fallback_model(
        job["image_path"], job["page_num"], prompt_text
    )
    ok = _write_ocr_output(job, text)
    return job["label"], ok


def process_image_jobs(jobs, prompt_text, batch_size=DEFAULT_BATCH):
    if not jobs:
        print("No images to OCR in current range.")
        return

    total = len(jobs)
    completed = 0
    fail_count = 0
    batch_size = max(1, int(batch_size))
    active_count = min(batch_size, total)
    print(f"Pending images: {total}")
    print(f"Active image limit: {active_count}")
    update_progress(0, total)

    next_job_idx = 0
    futures = {}
    with ThreadPoolExecutor(max_workers=active_count) as executor:
        for _ in range(active_count):
            job = jobs[next_job_idx]
            next_job_idx += 1
            futures[executor.submit(_process_image_job, job, prompt_text)] = job

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                label, ok = future.result()
                completed += 1
                if not ok:
                    fail_count += 1
                update_progress(completed, total)
                sys.stdout.write(f" {label}\n")
                sys.stdout.flush()

                if next_job_idx < total:
                    job = jobs[next_job_idx]
                    next_job_idx += 1
                    futures[executor.submit(_process_image_job, job, prompt_text)] = job

    if fail_count:
        print(f"Fail pages: {fail_count}")


def _auto_range_for_book(images_dir, output_dir):
    max_idx = find_max_index(output_dir)
    start_idx = max_idx + 1
    images_max_idx = find_max_image_index(images_dir)
    if images_max_idx >= start_idx:
        end_idx = images_max_idx
    else:
        end_idx = None
    return start_idx, end_idx, max_idx, images_max_idx


def process_books(
    base_dir,
    book_names,
    prompt_text,
    start_idx=None,
    end_idx=None,
    batch_size=DEFAULT_BATCH,
    overwrite=False,
):
    all_jobs = []
    for book_name in book_names:
        book_base = os.path.join(base_dir, book_name)
        images_dir = os.path.join(book_base, "images")
        output_dir = os.path.join(book_base, "ocr-result")
        book_start = start_idx
        book_end = end_idx
        if book_start is None and book_end is None:
            book_start, book_end, auto_start_from, auto_end_from = _auto_range_for_book(
                images_dir, output_dir
            )
            print(f"Book: {book_name}")
            print(f"  Images directory: {images_dir}")
            print(f"  Output directory: {output_dir}")
            print(f"  Auto start from (last continuous output index): {auto_start_from}")
            print(f"  Max image index: {auto_end_from}")
            if book_end is None:
                print("  Book complete: no pending images.")
                continue
            print(f"  Image index range: {book_start}-{book_end}")
        else:
            print(f"Book: {book_name}")
            print(f"  Images directory: {images_dir}")
            print(f"  Output directory: {output_dir}")
            print(f"  Image index range: {book_start}-{book_end}")
        all_jobs.extend(
            _build_image_jobs(
                images_dir,
                output_dir,
                start_idx=book_start,
                end_idx=book_end,
                label_prefix=book_name,
                skip_existing=not overwrite,
            )
        )
    process_image_jobs(all_jobs, prompt_text, batch_size=batch_size)
 
def process_images(
    images_dir,
    output_dir,
    prompt_text,
    start_idx=None,
    end_idx=None,
    batch_size=3,
    overwrite=False,
):
    """
    Reads JPG images from images_dir, extracts text using the API,
    and writes one Markdown file per image into output_dir.
    """
    if not os.path.isdir(images_dir):
        print(f"Images directory not found: {images_dir}")
        return

    jobs = _build_image_jobs(
        images_dir,
        output_dir,
        start_idx=start_idx,
        end_idx=end_idx,
        skip_existing=not overwrite,
    )
    process_image_jobs(jobs, prompt_text, batch_size=batch_size)


def process_single_image(image_path, output_dir, output_file, prompt_text):
    """
    Process a single image file and write one Markdown file.
    """
    if not os.path.isfile(image_path):
        print(f"Image file not found: {image_path}")
        return

    if output_file:
        out_path = output_file
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
    else:
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(output_dir, f"{base_name}.md")

    text = extract_text_with_fallback_model(image_path, 1, prompt_text)
    if text == "__PROHIBITED_CONTENT__":
        fail_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(image_path))[0]}.fail.md")
        try:
            with open(fail_path, "w", encoding="utf-8") as md_file:
                md_file.write("")
        except Exception as e:
            # Suppress write errors during processing
            pass
        return
    if text is None:
        print("No content after 5 attempts. Please intervene.")
        sys.exit(1)
    try:
        with open(out_path, "w", encoding="utf-8") as md_file:
            md_file.write(text)
    except Exception as e:
        # Suppress write errors during processing
        pass
 
def main():
    """
    Main function to execute the PDF to TXT conversion.
    """
    global FAST_MODE, REASONING_EFFORT

    print('\n********************************')
    print('*** Image OCR to Markdown ***')
    print('********************************\n')

    parser = argparse.ArgumentParser(
        description="OCR images to per-page Markdown files."
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
        help="Path to input images folder (default: <base-dir>/images).",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Path to a single image file to OCR (overrides input dir).",
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
        help="Path to output folder (default: <base-dir>/ocr-result).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Path to output Markdown file for single-image OCR.",
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
        help="Start index (inclusive) for numeric image filenames.",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="End index (inclusive) for numeric image filenames.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH,
        help="Concurrent batch size (default: 3).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        dest="batch_size",
        help="Alias for --batch-size.",
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
        "--overwrite",
        action="store_true",
        help="Re-OCR images even when matching .md or .fail.md output already exists.",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Path to prompt file (default: <skill-dir>/assets/ocr_prompt.md).",
    )
    parser.add_argument(
        "--prompt-file-from",
        default=None,
        help="UTF-8 text file containing prompt file path (first non-empty line).",
    )
    args = parser.parse_args()
    REASONING_EFFORT = args.reasoning_effort
    FAST_MODE = args.fast

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from
    book_names = args.book_name or [None]
    multiple_books = len(book_names) > 1

    if multiple_books and (
        args.input_dir
        or args.input_dir_from
        or args.input_file
        or args.input_file_from
        or args.output_dir
        or args.output_dir_from
        or args.output_file
        or args.output_file_from
    ):
        raise RuntimeError(
            "Multiple --book-name mode uses each book's default images/ocr-result directories; "
            "do not combine it with explicit input/output file or directory options."
        )

    if multiple_books:
        base_for_dirs = base_dir
    else:
        book_name = book_names[0]
        base_for_dirs = os.path.join(base_dir, book_name) if book_name else base_dir

    images_dir = args.input_dir or os.path.join(base_for_dirs, "images")
    if args.input_dir_from:
        input_dir_from = read_single_path(args.input_dir_from)
        if input_dir_from:
            images_dir = input_dir_from
    input_file = args.input_file
    if args.input_file_from:
        input_file_from = read_single_path(args.input_file_from)
        if input_file_from:
            input_file = input_file_from

    output_dir = args.output_dir or os.path.join(base_for_dirs, "ocr-result")
    if args.output_dir_from:
        output_dir_from = read_single_path(args.output_dir_from)
        if output_dir_from:
            output_dir = output_dir_from
    output_file = args.output_file
    if args.output_file_from:
        output_file_from = read_single_path(args.output_file_from)
        if output_file_from:
            output_file = output_file_from

    prompt_path = args.prompt_file or os.path.join(ASSETS_DIR, "ocr_prompt.md")
    if args.prompt_file_from:
        prompt_file_from = read_single_path(args.prompt_file_from)
        if prompt_file_from:
            prompt_path = prompt_file_from

    start_idx = args.start
    end_idx = args.end
    if input_file:
        start_idx = None
        end_idx = None
    auto_range = False
    auto_start_from = None
    auto_end_from = None
    if input_file:
        start_idx = None
        end_idx = None
    elif start_idx is None and end_idx is None:
        auto_range = True
        start_idx, end_idx, auto_start_from, auto_end_from = _auto_range_for_book(
            images_dir, output_dir
        )

    prompt_text = _load_prompt(prompt_path)

    if multiple_books:
        print(f"Model: {MODEL}")
        print(f"Reasoning effort: {REASONING_EFFORT}")
        print(f"Fast mode: {'enabled' if FAST_MODE else 'disabled'}")
        print(f"Prompt file: {prompt_path}")
        print(f"Batch size: {args.batch_size}")
        process_books(
            base_dir,
            book_names,
            prompt_text,
            start_idx=args.start,
            end_idx=args.end,
            batch_size=args.batch_size,
            overwrite=args.overwrite,
        )
        return

    print(f"Images directory: {images_dir}")
    print(f"Input file: {input_file or '(none)'}")
    print(f"Output directory: {output_dir}")
    print(f"Output file: {output_file or '(auto)'}")
    if auto_range:
        print(f"Auto start from (last continuous output index): {auto_start_from}")
        print(f"Max image index: {auto_end_from}")
        if end_idx is None:
            print("Book complete: no pending images.")
            return
    print(f"Image index range: {start_idx}-{end_idx}")
    print(f"Model: {MODEL}")
    print(f"Reasoning effort: {REASONING_EFFORT}")
    print(f"Fast mode: {'enabled' if FAST_MODE else 'disabled'}")
    print(f"Prompt file: {prompt_path}")
    print(f"Batch size: {args.batch_size}")

    if input_file:
        process_single_image(
            input_file,
            output_dir,
            output_file,
            prompt_text,
        )
    else:
        # Process images and extract text
        process_images(
            images_dir,
            output_dir,
            prompt_text,
            start_idx=start_idx,
            end_idx=end_idx,
            batch_size=args.batch_size,
            overwrite=args.overwrite,
        )
 
if __name__ == "__main__":
    main()
 
