import os
import sys
import time
import re
from datetime import datetime
import glob
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
 
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
        print("请在Antigravity Tools中复制配置粘贴到secrets.txt中！")
        sys.exit(1)
    return content


secrets_path = os.path.join(os.path.dirname(__file__), "secrets.txt")
secrets_text = _load_secrets_or_exit(secrets_path)

BASE_URL = _extract_secret(
    [
        r"api_endpoint\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"['\"]api_endpoint['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"client_options\s*=\s*{[^}]*api_endpoint\s*:\s*['\"]([^'\"]+)['\"][^}]*}",
        r"client_options\s*=\s*{[^}]*['\"]api_endpoint['\"]\s*:\s*['\"]([^'\"]+)['\"][^}]*}",
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
MODEL = _extract_secret([r"GenerativeModel\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"], secrets_text)

if not BASE_URL or not API_KEY or not MODEL:
    print("secrets.txt missing required values: api_endpoint, api_key, or model.")
    sys.exit(1)

if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3]

client = genai.Client(
    api_key=API_KEY,
    http_options={"base_url": BASE_URL},
)

SAFETY_SETTINGS = {
    "HARM_CATEGORY_HARASSMENT": "OFF",
    "HARM_CATEGORY_HATE_SPEECH": "OFF",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "OFF",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "OFF",
}
 
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
    if getattr(response, "text", None):
        return response.text
    try:
        parts = response.candidates[0].content.parts
    except Exception:
        return ""
    if not parts:
        return ""
    texts = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _get_finish_reason(response):
    try:
        cand = response.candidates[0]
    except Exception:
        return ""
    for attr in ("finish_reason", "finishReason"):
        val = getattr(cand, attr, None)
        if val:
            return str(val)
    if isinstance(cand, dict):
        return cand.get("finishReason") or cand.get("finish_reason") or ""
    for method in ("model_dump", "to_dict"):
        if hasattr(response, method):
            try:
                data = getattr(response, method)()
                cand0 = (data.get("candidates") or [None])[0] or {}
                return cand0.get("finishReason") or cand0.get("finish_reason") or ""
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


def extract_text_from_gemini_api(image_path, page_num, prompt_text):
    """
    Sends the image to a GenAI-compatible API and retrieves the extracted text.
    Added detailed logging and error information.
    """
    prohibited_sentinel = "__PROHIBITED_CONTENT__"
    last_error_message = None
    for attempt in range(1, 6):
        try:
            image_bytes = _read_image_bytes(image_path)
            content = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt_text),
                    types.Part.from_bytes(data=image_bytes, mime_type=_guess_mime_type(image_path)),
                ],
            )
            response = client.models.generate_content(
                model=MODEL,
                contents=[content],
            )

            finish_reason = _get_finish_reason(response)
            if finish_reason and "PROHIBITED_CONTENT" in finish_reason.upper():
                return prohibited_sentinel
            if finish_reason and "RECITATION" in finish_reason.upper():
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
 
def process_images(images_dir, output_dir, prompt_text, start_idx=None, end_idx=None, batch_size=3):
    """
    Reads JPG images from images_dir, extracts text using the API,
    and writes one Markdown file per image into output_dir.
    """
    if not os.path.isdir(images_dir):
        print(f"Images directory not found: {images_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff", "*.webp")
    image_files = []
    for ext in exts:
        image_files.extend(glob.glob(os.path.join(images_dir, ext)))
    if not image_files:
        print(f"No images found in: {images_dir}")
        return
    if start_idx is not None and end_idx is not None:
        filtered = []
        for path in image_files:
            name = os.path.splitext(os.path.basename(path))[0]
            if name.isdigit():
                num = int(name)
                if start_idx <= num <= end_idx:
                    filtered.append(path)
        image_files = filtered
        if not image_files:
            print(f"No images found in range {start_idx}-{end_idx}: {images_dir}")
            return
    image_files = sorted(
        image_files,
        key=lambda p: int(os.path.splitext(os.path.basename(p))[0])
        if os.path.splitext(os.path.basename(p))[0].isdigit()
        else os.path.basename(p)
    )

    total = len(image_files)
    fail_count = 0
    from threading import Lock
    fail_lock = Lock()

    def _process_one(image_path, idx):
        nonlocal fail_count
        text = extract_text_from_gemini_api(image_path, idx, prompt_text)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        if text == "__PROHIBITED_CONTENT__":
            out_path = os.path.join(output_dir, f"{base_name}.fail.md")
            try:
                with open(out_path, 'w', encoding='utf-8') as md_file:
                    md_file.write("")
            except Exception as e:
                # Suppress write errors during processing
                pass
            with fail_lock:
                fail_count += 1
            return
        if text is None:
            raise RuntimeError(f"No content after 5 attempts on page {idx}. Please intervene.")
        out_path = os.path.join(output_dir, f"{base_name}.md")
        try:
            with open(out_path, 'w', encoding='utf-8') as md_file:
                md_file.write(text)
        except Exception as e:
            # Suppress write errors during processing
            pass

    completed = 0
    batch_size = max(1, int(batch_size))
    items = list(enumerate(image_files, start=1))
    update_progress(0, total)
    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(_process_one, image_path, idx) for idx, image_path in batch]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"\n{e}")
                    sys.exit(1)
                completed += 1
                update_progress(completed, total)

    if fail_count:
        print(f"Fail pages: {fail_count}")


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

    text = extract_text_from_gemini_api(image_path, 1, prompt_text)
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
        default=3,
        help="Concurrent batch size (default: 3).",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Path to prompt file (default: <script-dir>/ocr_prompt.md).",
    )
    parser.add_argument(
        "--prompt-file-from",
        default=None,
        help="UTF-8 text file containing prompt file path (first non-empty line).",
    )
    args = parser.parse_args()

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from
    if args.book_name:
        base_dir = os.path.join(base_dir, args.book_name)

    images_dir = args.input_dir or os.path.join(base_dir, "images")
    if args.input_dir_from:
        input_dir_from = read_single_path(args.input_dir_from)
        if input_dir_from:
            images_dir = input_dir_from
    input_file = args.input_file
    if args.input_file_from:
        input_file_from = read_single_path(args.input_file_from)
        if input_file_from:
            input_file = input_file_from

    output_dir = args.output_dir or os.path.join(base_dir, "ocr-result")
    if args.output_dir_from:
        output_dir_from = read_single_path(args.output_dir_from)
        if output_dir_from:
            output_dir = output_dir_from
    output_file = args.output_file
    if args.output_file_from:
        output_file_from = read_single_path(args.output_file_from)
        if output_file_from:
            output_file = output_file_from

    prompt_path = args.prompt_file or os.path.join(os.path.dirname(__file__), "ocr_prompt.md")
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
        max_idx = find_max_index(output_dir)
        start_idx = max_idx + 1
        auto_start_from = max_idx
        images_max_idx = find_max_image_index(images_dir)
        if images_max_idx >= start_idx:
            end_idx = images_max_idx
            auto_end_from = images_max_idx
        else:
            end_idx = start_idx + 49
            auto_end_from = end_idx

    prompt_text = _load_prompt(prompt_path)

    print(f"Images directory: {images_dir}")
    print(f"Input file: {input_file or '(none)'}")
    print(f"Output directory: {output_dir}")
    print(f"Output file: {output_file or '(auto)'}")
    if auto_range:
        print(f"Auto start from (last continuous output index): {auto_start_from}")
        print(f"Auto end from (max image index or fallback): {auto_end_from}")
    print(f"Image index range: {start_idx}-{end_idx}")
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
        )
 
if __name__ == "__main__":
    main()
 
