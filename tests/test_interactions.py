# SPDX-License-Identifier: GPL-3.0-or-later
"""Keyboard focus, hover previews and per-assessment bar emphasis."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rich.console import Console
from textual.widgets import DataTable, Static
from canvas_grades import model, store
from canvas_grades.app import GradesApp
from canvas_grades.grade_bar import GradeBar


class Interactions(unittest.IsolatedAsyncioTestCase):
    async def test_tab_has_three_stops_and_notes_remain_keyboard_accessible(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(120, 38)) as pilot:
                await pilot.pause()
                self.assertEqual(app.focused.id, 'courses')
                expected = ('assignments', 'targets', 'courses', 'targets', 'assignments', 'courses')
                for key, focus in zip(('tab', 'tab', 'tab', 'shift+tab', 'shift+tab', 'shift+tab'), expected):
                    await pilot.press(key)
                    await pilot.pause()
                    self.assertEqual(app.focused.id, focus)
                app.query_one('#warnings', Static).update('A long grading note\n' * 80)
                app.query_one('#targets', DataTable).focus()
                await pilot.pause()
                panel = app.query_one('#target-panel')
                self.assertFalse(panel.can_focus)
                start = panel.scroll_y
                await pilot.press('pagedown')
                await pilot.pause()
                self.assertGreater(panel.scroll_y, start)
                await pilot.press('pageup')
                await pilot.pause()
                self.assertEqual(panel.scroll_y, start)
                self.assertEqual(app.focused.id, 'targets')

    async def test_selection_hover_header_and_leave_without_recalculating_or_selecting(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                table, bar = app.query_one('#assignments', DataTable), app.query_one(GradeBar)
                self.assertIsNone(bar.highlighted_id)
                with patch.object(model, 'project', side_effect=AssertionError('Highlighting must reuse grades')):
                    # Mouse preview works even while keyboard focus remains in courses.
                    await pilot.hover('#assignments', offset=(4, 4))
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '103')
                    self.assertEqual(app.focused.id, 'courses')
                    self.assertEqual(table.cursor_row, 0)
                    await pilot.hover('#brand')
                    await pilot.pause()
                    self.assertIsNone(bar.highlighted_id)
                    await pilot.press('tab', 'down')
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '102')
                    await pilot.hover('#assignments', offset=(4, 4))
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '103')
                    self.assertEqual(table.cursor_row, 1)
                    await pilot.hover('#assignments', offset=(4, 1))
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '102')
                    await pilot.hover('#assignments', offset=(4, 2))
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '101')
                    await pilot.press('down')
                    await pilot.pause()
                    self.assertEqual(bar.highlighted_id, '103')
                    await pilot.hover('#brand')
                    await pilot.press('tab')
                    await pilot.pause()
                    self.assertIsNone(bar.highlighted_id)
                    self.assertEqual(app.focused.id, 'targets')

    async def test_highlighting_one_small_assessment_dims_groupmates_without_reflow(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.pause()
                table, bar = app.query_one('#assignments', DataTable), app.query_one(GradeBar)
                layout, height = bar.segment_layout(), bar.region.height
                self.assertEqual(bar.colours[110], bar.colours[112])
                table.focus()
                table.move_cursor(row=3)  # Quiz 1, in the small shared quiz group.
                await pilot.pause()
                self.assertEqual(bar.highlighted_id, '110')
                self.assertIs(bar.segment_layout(), layout)
                self.assertEqual(bar.region.height, height)
                rendered = bar.bar_text()
                offset = rendered.plain.index('\n') + 1
                console = Console(color_system='truecolor')
                selected_cells, groupmate_cells = 0, 0
                for glyphs, colour, aid in layout:
                    style = rendered.get_style_at_offset(console, offset)
                    self.assertEqual(bool(style.dim), aid != '110')
                    self.assertEqual(bool(style.bold), aid == '110')
                    if aid == '110':
                        selected_cells += len(glyphs)
                        self.assertEqual(style.color.triplet.hex, colour)
                    if aid == '112':
                        groupmate_cells += len(glyphs)
                    offset += len(glyphs)
                self.assertGreater(selected_cells, 0)
                self.assertGreater(groupmate_cells, 0)
                table.move_cursor(row=4)  # Quiz 2 is dropped at the ceiling.
                await pilot.pause()
                self.assertIn('no contribution', bar.bar_text().plain)
                self.assertEqual(bar.region.height, height)
                app.query_one('#courses', DataTable).focus()
                await pilot.pause()
                self.assertIsNone(bar.highlighted_id)
                self.assertIs(bar.segment_layout(), layout)
