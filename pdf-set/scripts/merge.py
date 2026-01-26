# -*- coding: utf-8 -*-
import argparse
import os
import re

DEFAULT_INPUT_DIRNAME = 'ocr-result'
DEFAULT_OUTPUT_DIRNAME = 'merge-result'
DEFAULT_OUTPUT_FILENAME = '0.rough.md'

def read_single_path(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            value = line.strip()
            if value:
                return value
    return ""

def get_natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def merge_ocr_results(input_dir, output_dir, output_file):
    if not os.path.exists(input_dir):
        print(f"Error: Input directory {input_dir} does not exist.")
        return

    md_files = [f for f in os.listdir(input_dir) if f.endswith('.md')]
    # Sort files numerically (0.md, 1.md, 10.md, etc.)
    md_files.sort(key=get_natural_sort_key)

    print(f"Found {len(md_files)} files to merge.")

    all_content = []
    for filename in md_files:
        filepath = os.path.join(input_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                all_content.append(content)

    # Join with a single blank line (two newlines)
    merged_content = "\n\n".join(all_content)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(merged_content + "\n")

    print(f"Successfully merged {len(md_files)} files into {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge OCR markdown files into a single document."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Base directory containing OCR input/output folders (default: current directory).",
    )
    parser.add_argument(
        "--base-dir-from",
        default=None,
        help="UTF-8 text file containing base directory (first non-empty line).",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help=f"Path to input folder (default: <base-dir>/{DEFAULT_INPUT_DIRNAME}).",
    )
    parser.add_argument(
        "--input-dir-from",
        default=None,
        help="UTF-8 text file containing input folder path (first non-empty line).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Path to output folder (default: <base-dir>/{DEFAULT_OUTPUT_DIRNAME}).",
    )
    parser.add_argument(
        "--output-dir-from",
        default=None,
        help="UTF-8 text file containing output folder path (first non-empty line).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help=f"Output filename (default: {DEFAULT_OUTPUT_FILENAME}).",
    )
    parser.add_argument(
        "--output-file-from",
        default=None,
        help="UTF-8 text file containing output filename or path (first non-empty line).",
    )
    args = parser.parse_args()

    base_dir = args.base_dir
    if args.base_dir_from:
        base_dir_from = read_single_path(args.base_dir_from)
        if base_dir_from:
            base_dir = base_dir_from

    input_dir = args.input_dir or os.path.join(base_dir, DEFAULT_INPUT_DIRNAME)
    if args.input_dir_from:
        input_dir_from = read_single_path(args.input_dir_from)
        if input_dir_from:
            input_dir = input_dir_from

    output_dir = args.output_dir or os.path.join(base_dir, DEFAULT_OUTPUT_DIRNAME)
    if args.output_dir_from:
        output_dir_from = read_single_path(args.output_dir_from)
        if output_dir_from:
            output_dir = output_dir_from

    output_filename = args.output_file or DEFAULT_OUTPUT_FILENAME
    if args.output_file_from:
        output_file_from = read_single_path(args.output_file_from)
        if output_file_from:
            output_filename = output_file_from

    output_file = output_filename
    if not os.path.isabs(output_filename):
        output_file = os.path.join(output_dir, output_filename)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    merge_ocr_results(input_dir, output_dir, output_file)
