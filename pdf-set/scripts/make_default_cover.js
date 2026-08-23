#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');

const WIDTH = 1200;
const HEIGHT = 1920;
const RED = '#c4003d';
const BLACK = '#171313';
const PAPER = '#fffefe';

function usage(exitCode = 0) {
  const command = path.basename(process.argv[1]);
  console.log(`Usage:
  node ${command} --author "作者" --title "书名" [--output cover.png] [--svg cover.svg]
  node ${command} "作者" "书名" [cover.png]

Required:
  --author       Author name shown at the top
  --title        Book title shown above the geometric motif

Optional:
  --output, -o   PNG output path (default: ./<title>-cover.png)
  --svg          Also keep the generated SVG at this path
  --help, -h     Show this help`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const result = { positional: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') usage(0);
    if (arg === '--author') result.author = argv[++i];
    else if (arg === '--title') result.title = argv[++i];
    else if (arg === '--output' || arg === '-o') result.output = argv[++i];
    else if (arg === '--svg') result.svg = argv[++i];
    else if (arg.startsWith('-')) throw new Error(`Unknown option: ${arg}`);
    else result.positional.push(arg);
  }

  result.author ||= result.positional[0];
  result.title ||= result.positional[1];
  result.output ||= result.positional[2];
  if (!result.author || !result.title) usage(1);
  return result;
}

function loadSharp() {
  const candidates = [
    'sharp',
    path.join(
      os.homedir(),
      '.cache',
      'codex-runtimes',
      'codex-primary-runtime',
      'dependencies',
      'node',
      'node_modules',
      'sharp'
    ),
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      if (error.code !== 'MODULE_NOT_FOUND') throw error;
    }
  }
  throw new Error('Cannot find the "sharp" package. Install it with: npm install sharp');
}

function xmlEscape(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function safeFilename(value) {
  const cleaned = value
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
    .replace(/[. ]+$/g, '')
    .trim();
  return cleaned || 'cover';
}

function glyphWidth(char) {
  if (/\s/u.test(char)) return 0.32;
  if (/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(char)) return 1;
  if (/[，。！？；：、“”‘’（）《》〈〉【】…—]/u.test(char)) return 0.75;
  if (/[A-Z0-9]/u.test(char)) return 0.67;
  return 0.56;
}

function textUnits(text) {
  return Array.from(text).reduce((sum, char) => sum + glyphWidth(char), 0);
}

function wrapTitle(title, maxUnits) {
  const trimmed = title.trim();
  const yearMatch = trimmed.match(/\s*(（\d{4}[–—-]\d{4}）)$/u);
  const trailingYear = yearMatch ? yearMatch[1] : '';
  const body = trailingYear ? trimmed.slice(0, yearMatch.index).trim() : trimmed;
  const chars = Array.from(body);
  const lines = [];
  let line = '';
  let units = 0;

  for (const char of chars) {
    const nextUnits = units + glyphWidth(char);
    if (line && nextUnits > maxUnits) {
      lines.push(line.trim());
      line = char;
      units = glyphWidth(char);
    } else {
      line += char;
      units = nextUnits;
    }
  }
  if (line.trim()) lines.push(line.trim());

  if (trailingYear) {
    const last = lines.at(-1) || '';
    if (last && textUnits(`${last} ${trailingYear}`) <= maxUnits) {
      lines[lines.length - 1] = `${last} ${trailingYear}`;
    } else {
      lines.push(trailingYear);
    }
  }

  const forbiddenAtStart = /^[，。！？；：、）》】〉”’…]/u;
  for (let i = 1; i < lines.length; i += 1) {
    while (forbiddenAtStart.test(lines[i]) && lines[i - 1]) {
      lines[i - 1] += lines[i][0];
      lines[i] = lines[i].slice(1);
    }
  }
  return lines.filter(Boolean);
}

function titleLayout(title) {
  const maxWidth = 610;
  const attempts = [
    { maxLines: 1, maxFontSize: 94, minFontSize: 72 },
    { maxLines: 2, maxFontSize: 94, minFontSize: 48 },
    { maxLines: 3, maxFontSize: 72, minFontSize: 42 },
  ];

  for (const attempt of attempts) {
    for (let fontSize = attempt.maxFontSize; fontSize >= attempt.minFontSize; fontSize -= 2) {
      const maxUnits = maxWidth / fontSize;
      const lines = wrapTitle(title, maxUnits);
      const lineHeight = Math.round(fontSize * 1.28);
      if (
        lines.length <= attempt.maxLines &&
        lineHeight * lines.length <= 360 &&
        lines.every((line) => textUnits(line) * fontSize <= maxWidth * 1.04)
      ) {
        return {
          fontSize,
          lineHeight,
          lines,
          firstBaseline: Math.round(675 - ((lines.length - 1) * lineHeight) / 2 + fontSize * 0.32),
        };
      }
    }
  }
  throw new Error('The title is too long to fit on the cover. Shorten it and try again.');
}

function authorLayout(author) {
  const maxWidth = 805;
  const units = Math.max(textUnits(author), 1);
  return Math.max(48, Math.min(78, Math.floor(maxWidth / units)));
}

function makeSvg(author, title) {
  const layout = titleLayout(title);
  const authorSize = authorLayout(author);
  const titleLines = layout.lines
    .map(
      (line, index) =>
        `<tspan x="1040" y="${layout.firstBaseline + index * layout.lineHeight}">${xmlEscape(line)}</tspan>`
    )
    .join('\n      ');

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
  <defs>
    <clipPath id="line-frame-clip">
      <path d="M130 626 L304 610 L326 862 L157 878 Z"/>
    </clipPath>
  </defs>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="${PAPER}"/>

  <text x="1100" y="190" text-anchor="end" fill="${RED}"
        font-family="Noto Serif SC, LXGW WenKai, LXGW Bright, STSong, serif"
        font-size="${authorSize}" font-weight="500" letter-spacing="2">${xmlEscape(author)}</text>

  <g fill="none" stroke="${RED}" stroke-width="2.2" opacity="0.98" clip-path="url(#line-frame-clip)">
    <path d="M198 619 C184 678 250 720 283 770 C306 806 302 846 324 862"/>
    <path d="M198 619 C222 699 170 725 195 802 C209 846 261 862 311 844"/>
    <path d="M136 748 C184 806 222 849 292 866"/>
    <path d="M297 612 C251 642 266 682 305 682"/>
    <path d="M212 615 C250 680 277 723 323 756"/>
  </g>
  <path d="M130 626 L304 610 L326 862 L157 878 Z" fill="none" stroke="${RED}" stroke-width="2.2"/>

  <text text-anchor="end" fill="${BLACK}"
        font-family="Noto Serif SC, Source Han Serif SC, STSong, serif"
        font-size="${layout.fontSize}" font-weight="650" letter-spacing="1">${titleLines}</text>

  <path fill="${RED}" d="M0 872 H1058 C1124 1013 1135 1244 1092 1437 C1049 1628 936 1748 775 1807 C577 1879 310 1865 0 1920 Z"/>

  <path fill="none" stroke="${PAPER}" stroke-width="230" stroke-linecap="round" stroke-linejoin="round"
        d="M486 1842 C257 1751 116 1526 160 1262 C201 1016 426 945 590 1022 C763 1104 782 1337 719 1532 C670 1686 584 1829 516 1922"/>

  <path fill="none" stroke="${PAPER}" stroke-width="215" stroke-linecap="round"
        d="M508 1902 C709 1872 907 1770 1041 1605 C1110 1521 1154 1437 1200 1342"/>
</svg>`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sharp = loadSharp();
  const outputPath = path.resolve(args.output || `${safeFilename(args.title)}-cover.png`);
  const svgPath = args.svg ? path.resolve(args.svg) : null;
  const svg = makeSvg(args.author, args.title);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  if (svgPath) {
    fs.mkdirSync(path.dirname(svgPath), { recursive: true });
    fs.writeFileSync(svgPath, svg, 'utf8');
  }

  await sharp(Buffer.from(svg))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(outputPath);

  console.log(`PNG: ${outputPath}`);
  if (svgPath) console.log(`SVG: ${svgPath}`);
  console.log(`Size: ${WIDTH}x${HEIGHT}`);
}

main().catch((error) => {
  console.error(`Cover generation failed: ${error.message}`);
  process.exit(1);
});
