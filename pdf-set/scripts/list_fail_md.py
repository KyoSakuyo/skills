import argparse
import os
import re

DEFAULT_OCR_DIRNAME = "ocr-result"
FAIL_SUFFIX = ".fail.md"
FAIL_PATTERN = re.compile(r"^\d+\.fail\.md$")
IMAGE_DIRNAME = "图片"


def list_fail_files(ocr_dir):
    if not os.path.isdir(ocr_dir):
        return []
    names = []
    for name in os.listdir(ocr_dir):
        if name.endswith(FAIL_SUFFIX) and FAIL_PATTERN.match(name):
            names.append(name)
    names.sort(key=lambda n: int(n.split(".", 1)[0]))
    return names


def format_image_path(base_dir, ocr_dir, name, basename_only):
    number = name.split(".", 1)[0]
    book_dir = os.path.dirname(ocr_dir)
    book_name = os.path.basename(book_dir)
    image_rel = os.path.join(book_name, IMAGE_DIRNAME, f"{number}.jpg")
    if basename_only:
        return os.path.basename(image_rel)
    if base_dir:
        return image_rel
    return os.path.join(book_dir, IMAGE_DIRNAME, f"{number}.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List .fail.md files in ocr-result for OCR补漏 processing."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Base directory containing the ocr-result folder (default: current directory).",
    )
    parser.add_argument(
        "--ocr-dir",
        default=None,
        help=f"Path to ocr-result folder (default: <base-dir>/{DEFAULT_OCR_DIRNAME}).",
    )
    parser.add_argument(
        "--basename-only",
        action="store_true",
        help="Print only filenames without paths.",
    )
    args = parser.parse_args()

    ocr_dir = args.ocr_dir or os.path.join(args.base_dir, DEFAULT_OCR_DIRNAME)
    for name in list_fail_files(ocr_dir):
        print(format_image_path(args.base_dir, ocr_dir, name, args.basename_only))
