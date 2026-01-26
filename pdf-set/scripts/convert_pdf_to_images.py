import argparse
import os

from pdf2image import convert_from_path as _convert_from_path


def convert(pdf_path, output_dir, dpi=144, start_index=0, image_format="jpg", max_dim=None):
    os.makedirs(output_dir, exist_ok=True)
    images = _convert_from_path(pdf_path, dpi=dpi)
    page_count = len(images)

    for i, image in enumerate(images):
        if max_dim:
            width, height = image.size
            if width > max_dim or height > max_dim:
                scale_factor = min(max_dim / width, max_dim / height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                image = image.resize((new_width, new_height))

        filename = f"{start_index + i}.{image_format}"
        image_path = os.path.join(output_dir, filename)
        save_format = "JPEG" if image_format.lower() in {"jpg", "jpeg"} else image_format.upper()
        image.save(image_path, format=save_format)
        print(f"Saved page {start_index + i} as {image_path} (size: {image.size})")

    print(f"Converted {page_count} pages to {image_format} images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PDF pages to images.")
    parser.add_argument("input_pdf", help="Path to input PDF.")
    parser.add_argument("output_dir", help="Directory to save output images.")
    parser.add_argument("--dpi", type=int, default=144, help="Render DPI (default: 144).")
    parser.add_argument("--start", type=int, default=0, help="Starting index for filenames (default: 0).")
    parser.add_argument(
        "--format",
        default="jpg",
        choices=["jpg", "jpeg", "png"],
        help="Output image format (default: jpg).",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=None,
        help="Optional max dimension for scaling (default: no scaling).",
    )
    args = parser.parse_args()

    convert(
        args.input_pdf,
        args.output_dir,
        dpi=args.dpi,
        start_index=args.start,
        image_format=args.format,
        max_dim=args.max_dim,
    )
