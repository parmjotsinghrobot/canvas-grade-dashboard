# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with python -I after installing the wheel, to exclude source imports."""
import asyncio
import os
from pathlib import Path
import tempfile

async def main():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['CANVAS_GRADES_HOME'] = directory
        os.chdir(directory)
        from canvas_grades import browser_sync, store
        from canvas_grades.app import GradesApp
        from textual.widgets import DataTable
        assert store.DATA == Path(directory)
        page = browser_sync.setup_page('https://canvas.example.edu')
        assert 'Canvas Grades Sync' in page.read_text(encoding='utf-8')
        app = GradesApp(demo_mode=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.query_one('#courses', DataTable).row_count == 4
            await pilot.press('?')
            await pilot.pause()
            await pilot.click('#close-help')
        print('Installed wheel: demo, stylesheet, help and browser exporter work')

asyncio.run(main())
