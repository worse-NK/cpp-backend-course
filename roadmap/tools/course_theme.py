"""Apply the course's local dark stylesheet to complete HTML documents.

The operation changes shell metadata only, never lesson fragments, scripts,
examples or stored-progress keys. It is idempotent so source builders and the
publication collector can both use it.
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_PAGES = {
    "cpp_backend_roadmap.html": "home",
    "cpp_cheatsheet.html": "reference",
    "sources.html": "sources",
    "glossary.html": "glossary",
    "cpp_basic_level.html": "basic",
    "visual_labs.html": "visual-labs",
    "object_lifetime_demo.html": "lifetime",
    "sql_trainer.html": "sql",
    "security_sql_demo.html": "security-sql",
    "security_labs.html": "security",
    "service_workshop.html": "workshop",
    "cpp_station9_databases_intro.html": "redirect",
    "cpp_project_device_monitoring.html": "project",
}


def lab_flask_icon():
    """Decorative catalog mark; the adjacent link text supplies its name."""
    return ('<svg class="lab-flask" viewBox="0 0 24 24" width="24" height="24" '
            'aria-hidden="true" focusable="false" fill="none" stroke="currentColor" '
            'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M9 3h6M10 3v6l-5.2 8.5A2.3 2.3 0 0 0 6.8 21h10.4a2.3 2.3 0 0 0 2-3.5L14 9V3M8 15h8"/>'
            '</svg>')


def _with_classes(tag, names):
    match = re.search(r'\bclass\s*=\s*([\"\x27])(.*?)\1', tag, re.I | re.S)
    classes = match.group(2).split() if match else []
    for name in names:
        if name not in classes:
            classes.append(name)
    attribute = 'class="' + ' '.join(classes) + '"'
    if match:
        return tag[:match.start()] + attribute + tag[match.end():]
    return tag[:-1] + ' ' + attribute + '>'


def decorate_html(source, *, surfaces=True, page=None):
    """Return a full HTML document with opt-in dark tokens and optional surfaces."""
    if not re.search(r'<html\b', source, re.I):
        raise ValueError("The course theme accepts complete HTML documents only")
    if page is not None and not re.fullmatch(r'[a-z][a-z0-9-]*', page):
        raise ValueError("Unsafe course page class")

    source = re.sub(r'<html\b[^>]*>', lambda m: _with_classes(m.group(), ['course-dark']), source, count=1, flags=re.I)
    # sources.html originally relied on implied head/body tags. Make the shell
    # explicit before adding metadata rather than inserting styles into <main>.
    if not re.search(r'<head\b', source, re.I):
        source = re.sub(r'(<html\b[^>]*>)', r'\1<head>', source, count=1, flags=re.I)
        if re.search(r'<body\b', source, re.I):
            source = re.sub(r'(?=<body\b)', '</head>', source, count=1, flags=re.I)
        else:
            source = re.sub(r'(?=<main\b)', '</head><body>', source, count=1, flags=re.I)
            source = re.sub(r'(?=</html>)', '</body>', source, count=1, flags=re.I)
    if not re.search(r'<body\b', source, re.I):
        raise ValueError("The course theme requires a body element")
    classes = ['course-dark']
    if surfaces:
        classes.append('course-support')
    if page:
        classes.append('course-page-' + page)
    source = re.sub(r'<body\b[^>]*>', lambda m: _with_classes(m.group(), classes), source, count=1, flags=re.I)
    source = re.sub(r'\s*<link\b[^>]*href=[\"\x27]assets/course-(?:theme|dark-surfaces)\.css(?:\?[^\"\x27]*)?[\"\x27][^>]*>', '', source, flags=re.I)
    source = re.sub(r'\s*<meta\b(?=[^>]*\bname=[\"\x27]theme-color[\"\x27])[^>]*>', '', source, flags=re.I)
    assets = ['course-theme.css'] + (['course-dark-surfaces.css'] if surfaces else [])
    links = ['<meta name="theme-color" content="#18252f">']
    for asset in assets:
        version = hashlib.sha256((ROOT / 'assets' / asset).read_bytes()).hexdigest()[:12]
        links.append(f'<link rel="stylesheet" href="assets/{asset}?v={version}">')
    result = re.sub(r'\s*</head>', '\n' + '\n'.join(links) + '\n</head>', source, count=1, flags=re.I)
    from web_security import secure_html
    return secure_html(result.encode('utf-8')).decode('utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pages', nargs='*', choices=tuple(SUPPORT_PAGES))
    args = parser.parse_args()
    paths = args.pages or list(SUPPORT_PAGES)
    for filename in paths:
        path = ROOT / filename
        source = path.read_text(encoding='utf-8')
        result = decorate_html(source, page=SUPPORT_PAGES[filename])
        if result != source:
            path.write_text(result, encoding='utf-8')
        print('Themed ' + filename)
