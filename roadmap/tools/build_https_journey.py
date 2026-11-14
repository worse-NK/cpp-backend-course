#!/usr/bin/env python3
"""Build the HTTPS laboratory from its template, using only local runtime assets."""
import argparse
from pathlib import Path
from web_security import secure_html

ROOT = Path(__file__).resolve().parents[1]


def render():
    source = (ROOT / 'templates/https_journey_lab.html').read_bytes()
    # The canonical HTML matches publication. Offline/desktop collection applies
    # its stricter policy later; the template itself has no remote runtime URLs.
    return secure_html(source, name='https_journey_lab.html', mode='web')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'https_journey_lab.html'
    expected = render()
    if args.check:
        if not target.exists() or target.read_bytes() != expected:
            raise SystemExit('Stale HTTPS laboratory: run roadmap/tools/build_https_journey.py')
        print('PASS: HTTPS laboratory matches its template and course CSP')
    else:
        target.write_bytes(expected)
        print('Built roadmap/https_journey_lab.html')
