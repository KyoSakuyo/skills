import argparse
import os
import re

DEFAULT_INPUT_DIRNAME = "排版结果"

def read_single_path(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            value = line.strip()
            if value:
                return value
    return ""

def merge_md_files(input_dir, output_file):
    files = [f for f in os.listdir(input_dir) if f.endswith('.md')]

    def get_file_number(filename):
        match = re.search(r'^(\d+)\.', filename)
        return int(match.group(1)) if match else 999

    files.sort(key=get_file_number)

    print(f"Merging files in order: {files}")

    merged_content = []
    for filename in files:
        file_path = os.path.join(input_dir, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            merged_content.append(content)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(merged_content) + "\n")

    print(f"Successfully merged into: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge typeset markdown files into a single book file."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Book root directory (default: current directory).",
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
        help="UTF-8 text file containing input directory (first non-empty line).",
    )
    parser.add_argument(
        "--book-name",
        default=None,
        help="Output book name (defaults to base directory name).",
    )
    parser.add_argument(
        "--book-name-from",
        default=None,
        help="UTF-8 text file containing book name (first non-empty line).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Full output file path (overrides --book-name).",
    )
    parser.add_argument(
        "--output-file-from",
        default=None,
        help="UTF-8 text file containing output file path (first non-empty line).",
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

    book_name = args.book_name or os.path.basename(os.path.normpath(base_dir))
    if args.book_name_from:
        book_name_from = read_single_path(args.book_name_from)
        if book_name_from:
            book_name = book_name_from

    output_file = args.output_file or os.path.join(base_dir, f"{book_name}.md")
    if args.output_file_from:
        output_file_from = read_single_path(args.output_file_from)
        if output_file_from:
            output_file = output_file_from

    merge_md_files(input_dir, output_file)
