# -*- coding: utf-8 -*-
import argparse
import os
import re

DEFAULT_INPUT_DIRNAME = 'merge-result'
DEFAULT_OUTPUT_DIRNAME = 'typeset-result'

def cleanup_text(text):
    """Clean up OCR artifacts like repeated Chinese words/characters and footnote newlines."""
    # Dedupe for Chinese words (2+ characters) like "已经已经"
    text = re.sub(r'([\u4e00-\u9fa5]{2,})\1+', r'\1', text)
    # Dedupe for 3+ repeated Chinese characters (e.g., "太太太" -> "太太")
    text = re.sub(r'([\u4e00-\u9fa5])\1{2,}', r'\1\1', text)
    # Dedupe for English/word-boundary repeating sequences
    text = re.sub(r'(\b\w+\b)\1+', r'\1', text)
    
    # New Rule: Remove all newlines and multiple spaces within <sup>...</sup>
    def clean_footnote(match):
        content = match.group(0)
        # Replace newlines with nothing or a single space if it was a line break in text
        # But per user instructions, "删除其中空行，保证注释只有一段"
        # We replace any sequence of whitespace (including newlines) with a single space or nothing
        # If it's Chinese-like text, we probably want to join directly.
        # Let's join and then handle common spacing.
        lines = content.splitlines()
        cleaned_content = "".join(line.strip() for line in lines)
        return cleaned_content

    text = re.compile(r'<sup>.*?</sup>', re.DOTALL).sub(clean_footnote, text)
    
    return text

def process_layout(input_path, output_path, is_index=False):
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()

    blocks = []
    current_block = ""

    prev_block_is_heading = False

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue
        
        # Determine if this line starts a NEW paragraph/block
        # Rules: 
        # 1. Starts with # (heading)
        # 2. Starts with two spaces (indented paragraph)
        # 3. Contains 🀄 (page marker)
        # 4. Is a footnote <sup>
        # 5. Starts with special brackets 【 (often titles/sections)
        # 6. If it's an index file, treat almost all lines as new blocks if they are not very long
        
        starts_with_two_spaces = line.startswith('  ')
        is_heading = line.startswith('#')
        is_marker = '🀄' in line
        is_footnote_start = line.startswith('<sup>')
        is_bracket_title = line.startswith('【') or line.startswith('（')
        
        # New Rule: Lines starting with a date (e.g., 1842) followed by space
        is_date_line = re.match(r'^\d{4}(\.\.\.)?\s+', stripped_line)
        
        is_new_block = (is_heading or 
                        starts_with_two_spaces or 
                        is_marker or 
                        is_footnote_start or
                        is_bracket_title or
                        is_date_line)

        # Force a new block after headings so the following paragraph is separate
        if current_block and current_block.lstrip().startswith('#'):
            is_new_block = True
        
        # Special logic for index/list files or lines that look like list items
        if not is_new_block:
            if is_index:
                is_new_block = True
            elif len(stripped_line) < 50 and not any(c in stripped_line for c in "。！？"):
                # Increased threshold to 50, and only exclude strong terminal punctuation
                is_new_block = True

        if is_new_block:
            if current_block:
                blocks.append(current_block.rstrip())
                prev_block_is_heading = current_block.lstrip().startswith('#')

            # If the previous block was a heading, ensure the following paragraph
            # starts with a two-space indent unless it's a special line.
            if prev_block_is_heading and not (
                is_heading or is_marker or is_footnote_start or is_bracket_title or is_date_line
            ) and not starts_with_two_spaces:
                line = "  " + stripped_line

            current_block = line
        else:
            # Merge with the previous block
            if current_block:
                if current_block.rstrip().endswith('-'):
                    current_block = current_block.rstrip()[:-1] + stripped_line
                else:
                    current_block = current_block.rstrip() + stripped_line
            else:
                current_block = line

    if current_block:
        blocks.append(current_block.rstrip())

    # Join blocks with a single empty line (two newlines)
    final_text = "\n\n".join(blocks)
    final_text = cleanup_text(final_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_text + "\n")

def read_file_list(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines()]
    return [line for line in lines if line and line != '0.rough.md']

def match_by_indices(input_dir, indices):
    matched = []
    for index in indices:
        prefix = f"{index}."
        for filename in os.listdir(input_dir):
            if (
                filename.startswith(prefix)
                and filename.endswith('.md')
                and filename != '0.rough.md'
            ):
                matched.append(filename)
                break
    return matched

def collect_input_files(input_dir, filenames, files_from, file_indices):
    if files_from:
        return read_file_list(files_from)
    if file_indices:
        return match_by_indices(input_dir, file_indices)
    if filenames:
        return [f for f in filenames if f != '0.rough.md']
    return sorted(
        f for f in os.listdir(input_dir)
        if f.endswith('.md') and f != '0.rough.md'
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Typeset OCR markdown files by merging hard line breaks and cleaning footnotes."
    )
    parser.add_argument(
        "--base-dir",
        default=os.getcwd(),
        help="Base directory containing input/output folders (default: current directory).",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help=f"Path to input folder (default: <base-dir>/{DEFAULT_INPUT_DIRNAME}).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Path to output folder (default: <base-dir>/{DEFAULT_OUTPUT_DIRNAME}).",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Optional list of filenames to process (defaults to all .md files in input folder).",
    )
    parser.add_argument(
        "--files-from",
        default=None,
        help="UTF-8 text file with one filename per line to process (avoids shell encoding issues).",
    )
    parser.add_argument(
        "--file-indices",
        nargs="*",
        type=int,
        default=None,
        help="Optional list of numeric prefixes to match files like 1.xxx.md, 2.xxx.md.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir or os.path.join(args.base_dir, DEFAULT_INPUT_DIRNAME)
    output_dir = args.output_dir or os.path.join(args.base_dir, DEFAULT_OUTPUT_DIRNAME)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files_to_process = collect_input_files(
        input_dir,
        args.files,
        args.files_from,
        args.file_indices,
    )

    for filename in files_to_process:
        in_p = os.path.join(input_dir, filename)
        out_p = os.path.join(output_dir, filename)
        if os.path.exists(in_p):
            print(f"Processing {filename}...")
            is_index = "目录" in filename
            process_layout(in_p, out_p, is_index=is_index)
        else:
            print(f"Warning: {filename} not found.")

    print(f"Layout cleanup complete. Files processed: {len(files_to_process)}.")
