#!/usr/bin/env python3
"""Rasterize the native SVG with sandboxed Chrome, then make PNG icon sizes.

No remote resources, npm dependencies, font rendering or hand-edited raster
source. The small-icon contact sheet deliberately shows normal and enlarged
pixels on light/dark desktop backgrounds.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def render():
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    if not chrome:
        raise RuntimeError('Chrome/Chromium is required to rasterize the SVG')
    svg = (HERE / 'app.svg').read_text()
    with tempfile.TemporaryDirectory(prefix='course-icon-render-') as folder:
        temp = Path(folder)
        page = temp / 'icon.html'
        page.write_text('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:1024px;height:1024px;overflow:hidden;background:transparent}svg{display:block;width:1024px;height:1024px}</style>' + svg)
        result = subprocess.run([chrome, '--headless', '--disable-gpu', '--no-first-run',
            '--hide-scrollbars', '--force-device-scale-factor=1', '--default-background-color=00000000',
            '--user-data-dir=' + str(temp / 'profile'), '--window-size=1024,1024',
            '--screenshot=' + str(temp / 'render.png'), page.as_uri()],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr[-3000:])
        image = Image.open(temp / 'render.png').convert('RGBA')
        if image.size != (1024, 1024):
            raise RuntimeError('Unexpected viewport: ' + str(image.size))
        if image.getpixel((0, 0))[3] != 0:
            raise RuntimeError('Chrome did not preserve transparency')
        for size in SIZES:
            icon = image.resize((size, size), Image.Resampling.LANCZOS)
            # Lanczos can leave barely visible alpha=1 rings at small corners.
            # Keep the exported transparent canvas genuinely transparent.
            icon.putalpha(icon.getchannel('A').point(lambda alpha: 0 if alpha < 4 else alpha))
            icon.save(HERE / ('app-' + str(size) + '.png'))
    sheet = Image.new('RGB', (1200, 720), '#101b24')
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((36, 25), 'C++ Backend / Desktop application icon', fill='#e4edf2', font=font)
    large = Image.open(HERE / 'app-512.png')
    sheet.paste(large, (25, 105), large)
    for row, background in enumerate(('#18252f', '#eef2f5')):
        left, top = 570, 105 + row * 260
        draw.rounded_rectangle((left, top, 1170, top + 230), radius=18, fill=background)
        for index, size in enumerate((16, 24, 32, 48, 64, 128)):
            x = left + 28 + index * 87
            icon = Image.open(HERE / ('app-' + str(size) + '.png'))
            sheet.paste(icon, (x, top + 38 + (128 - size) // 2), icon)
            draw.text((x, top + 185), str(size) + ' px', fill='#90a8b7' if row == 0 else '#405664', font=font)
    draw.text((40, 660), 'Vector master / transparent PNG / no external images or fonts', fill='#b1c1cc', font=font)
    sheet.save(HERE / 'contact-sheet.png')
    print(json.dumps({'sizes': SIZES, 'master': str(HERE / 'app.svg'),
                      'alpha': True, 'sandbox_disabled': False}))


if __name__ == '__main__':
    render()
