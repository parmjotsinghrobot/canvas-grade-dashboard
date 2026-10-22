# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from canvas_grades import store


class StoragePaths(unittest.TestCase):
    def test_checkout_keeps_existing_local_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'CANVAS_GRADES_HOME': ''}):
            root = Path(directory)
            (root / 'pyproject.toml').touch()
            (root / 'canvas_grades').mkdir()
            self.assertEqual(store.data_directory(root), root / '.local')

    def test_installed_tool_uses_writable_user_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'CANVAS_GRADES_HOME': ''}), patch.object(store, 'user_data_path', return_value=Path(directory)/'user-data'):
            self.assertEqual(store.data_directory(Path(directory)/'site-packages'), Path(directory)/'user-data')

    def test_override_expands_home_and_is_absolute(self):
        with patch.dict(os.environ, {'CANVAS_GRADES_HOME': '~/canvas-grades-test'}):
            self.assertEqual(store.data_directory(), Path.home()/'canvas-grades-test')
