# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject private files in release artifacts; require runtime assets and licence."""
from pathlib import Path
import tarfile
import zipfile

PRIVATE = {'.local', '.venv', '.env', '__pycache__', 'credentials.json',
           'session.json', 'snapshot.json', 'config.json', 'browser-setup.html'}
archives = list(Path('dist').glob('*.whl')) + list(Path('dist').glob('*.tar.gz'))
assert any(p.suffix == '.whl' for p in archives), 'No wheel built'
assert any(p.name.endswith('.tar.gz') for p in archives), 'No source archive built'
for path in archives:
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    for name in names:
        parts = Path(name).parts
        assert not PRIVATE.intersection(parts), f'Private file in {path.name}: {name}'
        assert not any(part.startswith('.env.') for part in parts), name
        assert not (Path(name).name.startswith('canvas-grades-') and name.endswith('.json')), name
        assert not name.endswith('.pyc'), name
    for required in ('canvas_grades/style.tcss', 'canvas_grades/browser_export.js', 'LICENSE'):
        assert any(name.endswith('/' + required) or name == required for name in names), (path, required)
    print(f'{path.name}: private files excluded; runtime assets and GPL licence included')
