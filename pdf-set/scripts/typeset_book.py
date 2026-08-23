# -*- coding: utf-8 -*-
import argparse
import os
import re


DEFAULT_INPUT_DIRNAME = "ocr-result"
EMPTY_PAGE_MARKER = "🈳"
IMAGE_MARKER = "🀄"


def starts_with_indent(text):
    return text.startswith(("  ", "\t", "\u3000"))


def is_marker_block(text):
    return IMAGE_MARKER in text


def is_heading(text):
    return bool(re.match(r"^#{1,6}\s+", text))


def natural_sort_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def normalize_block(block):
    lines = [line.rstrip() for line in block.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip("\n")


def split_blocks(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [normalize_block(block) for block in re.split(r"\n\s*\n+", text) if block.strip()]


def split_special_lines(block):
    parts = []
    normal_lines = []
    for line in block.splitlines():
        stripped = line.strip()
        if EMPTY_PAGE_MARKER in stripped:
            continue
        if is_marker_block(stripped) or is_heading(stripped):
            if normal_lines:
                parts.append("\n".join(normal_lines).rstrip())
                normal_lines = []
            parts.append(stripped)
        else:
            normal_lines.append(line)
    if normal_lines:
        parts.append("\n".join(normal_lines).rstrip())
    return [part for part in parts if part.strip()]


def needs_space(left, right):
    if not left or not right:
        return False
    if left.endswith("-"):
        return False
    return left[-1].isascii() and right[0].isascii() and not left[-1].isspace()


def merge_into_previous(previous, current):
    previous = previous.rstrip()
    current = current.lstrip()
    if previous.endswith("-"):
        return previous[:-1] + current
    if needs_space(previous, current):
        return previous + " " + current
    return previous + current


def merge_wrapped_lines(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    merged = lines[0]
    for line in lines[1:]:
        merged = merge_into_previous(merged, line)
    return merged


def is_hard_boundary(text):
    return is_marker_block(text) or is_heading(text)


def typeset_text(text):
    paragraphs = []

    for raw_block in split_blocks(text):
        for block in split_special_lines(raw_block):
            stripped = block.strip()
            if not stripped:
                continue

            if is_marker_block(stripped) or is_heading(stripped):
                paragraphs.append(stripped)
                continue

            merged_block = merge_wrapped_lines(block)
            if not merged_block:
                continue

            if starts_with_indent(block):
                paragraphs.append(merged_block)
                continue

            if paragraphs and not is_hard_boundary(paragraphs[-1]):
                paragraphs[-1] = merge_into_previous(paragraphs[-1], merged_block)
            else:
                paragraphs.append(merged_block)

    return "\n\n".join(p.strip() for p in paragraphs if p.strip()).rstrip() + "\n"


def read_ocr_pages(input_dir):
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"OCR input directory not found: {input_dir}")

    page_files = [
        entry.name
        for entry in os.scandir(input_dir)
        if entry.is_file() and entry.name.lower().endswith(".md")
    ]
    page_files.sort(key=natural_sort_key)
    if not page_files:
        raise FileNotFoundError(f"No Markdown page files found in: {input_dir}")

    pages = []
    for filename in page_files:
        path = os.path.join(input_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        if content.strip():
            pages.append(content)

    if not pages:
        raise ValueError(f"All Markdown page files are empty in: {input_dir}")

    print(f"Found {len(page_files)} OCR page files.")
    return "\n\n".join(pages)


def typeset_directory(input_dir, output_file):
    result = typeset_text(read_ocr_pages(input_dir))
    parent = os.path.dirname(output_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"Successfully typeset into: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge and typeset OCR page Markdown files into a final book Markdown file."
    )
    parser.add_argument("--base-dir", default=os.getcwd(), help="Book root directory.")
    parser.add_argument("--input-dir", default=None, help="OCR page Markdown directory.")
    parser.add_argument("--book-name", default=None, help="Output book name.")
    parser.add_argument("--output-file", default=None, help="Final output Markdown file.")
    args = parser.parse_args()

    base_dir = args.base_dir
    input_dir = args.input_dir or os.path.join(base_dir, DEFAULT_INPUT_DIRNAME)
    book_name = args.book_name or os.path.basename(os.path.normpath(base_dir))
    output_file = args.output_file or os.path.join(base_dir, f"{book_name}.md")

    typeset_directory(input_dir, output_file)
    print("Done.")


if __name__ == "__main__":
    main()
