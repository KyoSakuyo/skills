#!/usr/bin/env python3
"""Flag cropped images whose visible content touches an outer border."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

from PIL import Image, ImageStat


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass
class EdgeResult:
    name: str
    touched: int
    longest_run: int

    @property
    def flagged(self) -> bool:
        return self.longest_run >= 2 or self.touched >= 8


def _median_background(image: Image.Image, corner_size: int = 8) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    w, h = rgb.size
    boxes = [
        (0, 0, min(corner_size, w), min(corner_size, h)),
        (max(0, w - corner_size), 0, w, min(corner_size, h)),
        (0, max(0, h - corner_size), min(corner_size, w), h),
        (max(0, w - corner_size), max(0, h - corner_size), w, h),
    ]
    samples = []
    for box in boxes:
        samples.extend(rgb.crop(box).get_flattened_data())
    channels = sorted(zip(*samples))
    middle = len(samples) // 2
    return tuple(channel[middle] for channel in channels)


def _is_content(pixel: tuple[int, int, int], background: tuple[int, int, int], tolerance: int) -> bool:
    distance = max(abs(pixel[i] - background[i]) for i in range(3))
    luminance = (pixel[0] * 299 + pixel[1] * 587 + pixel[2] * 114) // 1000
    return distance > tolerance and luminance < 235


def _edge_result(name: str, values: list[bool]) -> EdgeResult:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return EdgeResult(name, sum(values), longest)


def inspect_image(path: Path, band: int = 1, tolerance: int = 24) -> tuple[tuple[int, int, int], list[EdgeResult]]:
    with Image.open(path) as source:
        image = source.convert("RGB")
    w, h = image.size
    if w < 2 or h < 2:
        return (255, 255, 255), [EdgeResult("invalid", 1, 1)]
    background = _median_background(image)
    px = image.load()
    band = max(1, min(band, w // 2, h // 2))

    top = [any(_is_content(px[x, y], background, tolerance) for y in range(band)) for x in range(w)]
    bottom = [any(_is_content(px[x, h - 1 - y], background, tolerance) for y in range(band)) for x in range(w)]
    left = [any(_is_content(px[x, y], background, tolerance) for x in range(band)) for y in range(h)]
    right = [any(_is_content(px[w - 1 - x, y], background, tolerance) for x in range(band)) for y in range(h)]
    return background, [
        _edge_result("top", top),
        _edge_result("bottom", bottom),
        _edge_result("left", left),
        _edge_result("right", right),
    ]


def iter_images(paths: list[Path]):
    for path in paths:
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Image files or asset directories")
    parser.add_argument("--band", type=int, default=1, help="Outer pixel-border width (default: 1)")
    parser.add_argument("--tolerance", type=int, default=24, help="RGB distance from corner background")
    parser.add_argument("--all", action="store_true", help="Print passing images too")
    args = parser.parse_args()

    checked = flagged = 0
    for path in iter_images(args.paths):
        checked += 1
        background, edges = inspect_image(path, args.band, args.tolerance)
        bad = [edge for edge in edges if edge.flagged]
        if bad:
            flagged += 1
        if bad or args.all:
            status = "FLAG" if bad else "PASS"
            detail = ",".join(f"{e.name}:{e.touched}/{e.longest_run}" for e in bad) or "uniform"
            print(f"{status}\t{path}\tbg={background}\t{detail}")
    print(f"SUMMARY\tchecked={checked}\tflagged={flagged}")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
