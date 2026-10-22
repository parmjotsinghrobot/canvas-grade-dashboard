# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from canvas_grades import browser_sync, store, demo, model
from canvas_grades.app import GradesApp, BrowserConnect
from textual.widgets import DataTable, Input


def sample():
    return {**demo.snapshot(), 'format':'canvas-grades/v1','source':'browser'}


class BrowserSync(unittest.TestCase):
    def test_setup_uses_default_browser_with_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)), patch.object(browser_sync.webbrowser, 'open', return_value=True) as opened:
            self.assertTrue(browser_sync.open_setup('https://canvas.example.edu'))
            path = Path(directory)/'browser-setup.html'
            markup = path.read_text()
            self.assertIn('javascript:void', markup)
            self.assertIn('Canvas Grades Sync', markup)
            self.assertIn('https://canvas.example.edu', markup)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            opened.assert_called_once_with(path.as_uri(), new=2)
            browser_sync.open_canvas('https://canvas.example.edu')
            opened.assert_called_with('https://canvas.example.edu', new=2)

    def test_validate_and_calculate_exported_data(self):
        data = sample()
        result = browser_sync.validate(data, 'https://canvas.example.edu')
        self.assertEqual(result['courses'][3]['nickname'], 'Signals crew')
        self.assertIsNotNone(model.project(result['courses'][0]).percent)

    def test_rejects_malformed_or_other_canvas_data(self):
        changes = [lambda d:d.update(format='unknown'), lambda d:d.update(base_url='https://other.example'),
                   lambda d:d.update(fetched_at='2026-10-22T00:00:00'), lambda d:d['courses'].append(d['courses'][0]),
                   lambda d:d['courses'][0]['groups'][0]['assignments'][0]['submission'].update(score=float('nan')),
                   lambda d:d['courses'][0]['groups'][0].update(group_weight='fifty'),
                   lambda d:d['courses'][0]['groups'][0]['assignments'][0].update(points_possible=-10)]
        for change in changes:
            with self.subTest(change=change):
                data = sample(); change(data)
                with self.assertRaises(ValueError):
                    browser_sync.validate(data, 'https://canvas.example.edu')

    def test_download_candidates_and_size_limit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'CANVAS_GRADES_DOWNLOADS': directory}):
            valid = Path(directory)/'canvas-grades-100.json'
            valid.write_text(json.dumps(sample()))
            (Path(directory)/'unrelated.json').write_text('{}')
            (Path(directory)/'canvas-grades-200.json.part').write_text('{}')
            self.assertEqual(browser_sync.candidates(), [valid])
            self.assertEqual(browser_sync.read_export(valid)['source'], 'browser')
            with patch.object(browser_sync, 'MAX_BYTES', 10):
                with self.assertRaisesRegex(ValueError, 'too large'):
                    browser_sync.read_export(valid)


class BrowserApp(unittest.IsolatedAsyncioTestCase):
    async def test_browser_login_and_download_import_keep_weights(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as downloads, patch.object(store, 'DATA', Path(directory)), patch.dict('os.environ', {'CANVAS_TOKEN':'','CANVAS_GRADES_DOWNLOADS':downloads}), patch.object(browser_sync.webbrowser,'open',return_value=True) as opened:
            app = GradesApp()
            async with app.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, BrowserConnect)
                app.screen.query_one('#browser-url', Input).value = 'https://canvas.example.edu'
                await pilot.click('#browser-connect')
                await pilot.pause()
                self.assertTrue(opened.call_args[0][0].endswith('browser-setup.html'))
                self.assertEqual(app.config['auth_mode'],'browser')
                key = 'https://canvas.example.edu|1'
                app.config['weights']={key:{'mode':'groups','values':{'1':35,'2':25,'3':5,'4':35}}}
                path = Path(downloads)/'canvas-grades-123.json'
                path.write_text(json.dumps(sample()))
                app.poll_browser_downloads()
                await pilot.pause()
                self.assertEqual(app.query_one('#courses', DataTable).row_count,4)
                self.assertEqual(app.course()['groups'][0]['group_weight'],35)
                self.assertEqual(store.read('snapshot.json')['source'],'browser')
                self.assertIsNone(app.client)
                self.assertFalse((Path(directory)/'credentials.json').exists())
                await pilot.press('r')
                await pilot.pause()
                opened.assert_called_with('https://canvas.example.edu',new=2)
