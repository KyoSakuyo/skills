import argparse
import os
import re

DEFAULT_INPUT_DIRNAME = '合并结果'
DEFAULT_INPUT_FILENAME = '0.粗全文.md'

def read_single_path(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            value = line.strip()
            if value:
                return value
    return ""

def split_markdown_by_h1(input_file, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by level 1 header "# " at the start of a line
    parts = re.split(r'^#\s+', content, flags=re.MULTILINE)

    index = 1
    for i in range(1, len(parts)):
        section_content = parts[i]
        lines = section_content.split('\n', 1)
        title = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""

        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        filename = f"{index}.{safe_title}.md"
        output_path = os.path.join(output_dir, filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n{body}")

        print(f"Created: {filename}")
        index += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Split merged markdown into multiple files by H1 headings."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Base directory containing the merged output folder (default: current directory).",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help=f"Path to merged markdown file (default: <base-dir>/{DEFAULT_INPUT_DIRNAME}/{DEFAULT_INPUT_FILENAME}).",
    )
    parser.add_argument(
        "--input-file-from",
        default=None,
        help="UTF-8 text file containing a single input file path (first non-empty line).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Path to output folder (default: <base-dir>/{DEFAULT_INPUT_DIRNAME}).",
    )
    args = parser.parse_args()

    input_file = args.input_file or os.path.join(
        args.base_dir, DEFAULT_INPUT_DIRNAME, DEFAULT_INPUT_FILENAME
    )
    if args.input_file_from:
        input_file_from = read_single_path(args.input_file_from)
        if input_file_from:
            input_file = input_file_from
    output_dir = args.output_dir or os.path.join(args.base_dir, DEFAULT_INPUT_DIRNAME)

    split_markdown_by_h1(input_file, output_dir)
