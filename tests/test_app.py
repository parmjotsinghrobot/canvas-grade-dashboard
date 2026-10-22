# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import DataTable, Input, Static
from canvas_grades import store
from canvas_grades.app import GradesApp, Setup, WhatIf, Picker, BrowserConnect


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_navigation_scenario_and_help(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(160, 50)) as pilot:
                await pilot.pause()
                self.assertEqual(app.query_one("#courses", DataTable).row_count, 4)
                self.assertEqual(app.query_one("#assignments", DataTable).row_count, 8)
                app.query_one("#courses", DataTable).move_cursor(row=3)
                await pilot.pause()
                self.assertEqual(app.current_id, 4)
                self.assertIn("Signals crew", str(app.query_one("#course-title", Static).render()))
                await pilot.press("w")
                await pilot.pause()
                self.assertIsInstance(app.screen, WhatIf)
                app.screen.query_one(Input).value = "85"
                await pilot.click("#apply")
                await pilot.pause()
                self.assertTrue(app.overrides[4])
                await pilot.press("m")
                self.assertTrue(app.strict)
                await pilot.press("x")
                self.assertFalse(app.strict)
                self.assertFalse(app.overrides)
                await pilot.press("?")
                await pilot.pause()
                await pilot.click("#close-help")
                await pilot.pause()
                app.save_screenshot("preview.svg", path="/tmp")

    async def test_setup_hidden_token_and_cancel(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)), patch.dict("os.environ", {"CANVAS_TOKEN": ""}):
            app = GradesApp()
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, BrowserConnect)
                self.assertEqual(app.screen.query_one('#browser-url', Input).value, '')
                app.screen.query_one('#browser-url', Input).value = 'https://canvas.example.edu'
                await pilot.click("#token-login")
                await pilot.pause()
                self.assertIsInstance(app.screen, Setup)
                self.assertEqual(app.screen.query_one('#url', Input).value, 'https://canvas.example.edu')
                self.assertTrue(app.screen.query_one("#token", Input).password)
                await pilot.click("#cancel")
                await pilot.pause()
                self.assertIn("cancelled", str(app.query_one("#sync", Static).render()))

    async def test_small_terminal(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                self.assertEqual(app.query_one("#courses", DataTable).row_count, 4)
                await pilot.press("tab", "down")

    async def test_connect_choose_courses_fetch_and_offline(self):
        from canvas_grades import api, demo
        sample = demo.snapshot()
        catalog = sample["courses"]
        async def courses(client):
            return catalog, []
        async def snapshot(client, selected, warnings=None):
            value = {**sample, "courses": selected}
            store.write("snapshot.json", value)
            return value
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)), patch.dict("os.environ", {"CANVAS_TOKEN": ""}), patch.object(api.Client, "courses", courses), patch.object(api.Client, "snapshot", snapshot):
            app = GradesApp()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.click("#token-login")
                await pilot.pause()
                app.screen.query_one("#url", Input).value = "https://canvas.example.edu"
                app.screen.query_one("#token", Input).value = "fake-test-token"
                await pilot.click("#connect")
                await pilot.pause()
                self.assertIsInstance(app.screen, Picker)
                app.screen.query_one("SelectionList").select(4)
                await pilot.click("#choose")
                await pilot.pause()
                self.assertEqual(app.query_one("#courses", DataTable).row_count, 1)
                self.assertEqual(app.current_id, 4)
                self.assertEqual(store.read("config.json")["course_ids"], [4])
                self.assertEqual(store.read("credentials.json")["token"], "fake-test-token")
                self.assertFalse(app.loading)
                await pilot.press("r")
                await pilot.pause()
                self.assertEqual(app.query_one("#courses", DataTable).row_count, 1)
            offline = GradesApp(offline=True)
            async with offline.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(offline.query_one("#courses", DataTable).row_count, 1)
                self.assertIsNone(offline.client)

    async def test_weight_editor_validation_and_restore(self):
        from canvas_grades.app import WeightChoice, WeightEditor
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                original = app.course()["groups"][0]["group_weight"]
                await pilot.press("g")
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightChoice)
                await pilot.click("#weight-groups")
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightEditor)
                app.screen.query_one("#weight-1", Input).value = "35"
                await pilot.click("#weight-save")
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightEditor)
                self.assertIn("100%", str(app.screen.query_one("#weight-error", Static).render()))
                app.screen.query_one("#weight-4", Input).value = "35"
                await pilot.pause(.4)
                await pilot.click("#weight-save")
                await pilot.pause()
                self.assertEqual(app.course()["groups"][0]["group_weight"], 35)
                self.assertEqual(app.raw_course()["groups"][0]["group_weight"], original)
                await pilot.press("g")
                await pilot.pause()
                await pilot.click("#weight-canvas")
                await pilot.pause()
                self.assertEqual(app.course()["groups"][0]["group_weight"], original)
                await pilot.press("g")
                await pilot.pause()
                await pilot.click("#weight-assignments")
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightEditor)
                app.save_screenshot("canvas-weights.svg", path="/tmp")
                await pilot.click("#weight-save")
                await pilot.pause()
                self.assertEqual(app.course()["_weights_mode"], "assignments")

    async def test_saved_weights_reapplied_on_next_launch(self):
        from canvas_grades import demo
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)):
            store.write("snapshot.json", demo.snapshot())
            app = GradesApp(offline=True)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.save_weights({"mode": "groups", "values": {"1": 35, "2": 25, "3": 5, "4": 35}})
                await pilot.pause()
                self.assertEqual(app.course()["groups"][0]["group_weight"], 35)
            app2 = GradesApp(offline=True)
            async with app2.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(app2.course()["groups"][0]["group_weight"], 35)
                self.assertEqual(app2.raw_course()["groups"][0]["group_weight"], 30)

    async def test_compact_assignment_columns_fit_long_titles_and_resize(self):
        from canvas_grades import demo
        sample = demo.snapshot()
        for c in sample['courses']:
            c['name'] += ' A very long official course name' * 5
            for g in c['groups']:
                for a in g['assignments']:
                    a['name'] += ' A very long assessment title' * 8
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)), patch.object(demo, 'snapshot', return_value=sample):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(160, 45)) as pilot:
                await pilot.pause()
                table = app.query_one('#assignments', DataTable)
                self.assertEqual([str(column.label) for column in table.columns.values()], ['Assessment', 'Status', 'Mark', 'Weight'])
                self.assertEqual(str(table.get_row_at(0)[1]), 'Graded')
                self.assertEqual(str(table.get_row_at(1)[1]), 'Submitted')
                self.assertEqual(str(table.get_row_at(6)[1]), 'Not done')
                self.assertEqual(str(table.get_row_at(7)[1]), 'Offline')
                self.assertEqual(table.max_scroll_x, 0)
                self.assertIn('5 graded', str(app.query_one('#summary', Static).render()))
                self.assertIn('1 submitted', str(app.query_one('#summary', Static).render()))
                self.assertIn('1 not done yet', str(app.query_one('#summary', Static).render()))
                await pilot.resize_terminal(100, 35)
                await pilot.pause()
                self.assertEqual(table.max_scroll_x, 0)
                self.assertEqual(app.query_one('#courses', DataTable).max_scroll_x, 0)
                app.save_screenshot('canvas-compact.svg', path='/tmp')

    async def test_selected_assessment_weight_shortcut_and_visible_weight(self):
        from canvas_grades.app import WeightEditor
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(130, 40)) as pilot:
                await pilot.pause()
                table = app.query_one('#assignments', DataTable)
                table.move_cursor(row=1)
                await pilot.pause()
                await pilot.press('a')
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightEditor)
                self.assertEqual(app.screen.focused.id, 'weight-102')
                await pilot.click('#weight-save')
                await pilot.pause()
                self.assertEqual(app.course()['_weights_mode'], 'assignments')
                self.assertEqual(str(table.get_row_at(1)[3]), '18%')

    async def test_local_assessment_create_edit_disable_refresh_restart_and_delete(self):
        from canvas_grades import demo, model
        from canvas_grades.app import LocalAssessmentEditor, WeightEditor
        from textual.widgets import Select
        sample = demo.snapshot()
        sample['courses'][0]['groups'][3]['group_weight'] = 20
        sample['courses'][0]['groups'].append({'id': 5, 'name': 'Benchmark', 'group_weight': 20, 'assignments': [], 'rules': {}})
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            store.write('snapshot.json', sample)
            app = GradesApp(offline=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                self.assertIsNone(model.project(app.course()).percent)
                await pilot.press('n')
                await pilot.pause()
                self.assertIsInstance(app.screen, LocalAssessmentEditor)
                self.assertEqual(app.screen.query_one('#local-group', Select).value, 5)
                app.screen.query_one('#local-name', Input).value = 'Benchmark test'
                app.screen.query_one('#local-points', Input).value = '0'
                await pilot.click('#local-save')
                await pilot.pause()
                self.assertIn('greater than zero', str(app.screen.query_one('#local-error', Static).render()))
                app.screen.query_one('#local-points', Input).value = '20'
                app.screen.query_one('#local-score', Input).value = '19'
                await pilot.pause(.4)
                await pilot.click('#local-save')
                await pilot.pause()
                local = app.selected_assignment()
                self.assertTrue(local['_local'])
                self.assertEqual(local['submission']['score'], 19)
                local_id = local['id']
                table = app.query_one('#assignments', DataTable)
                self.assertEqual(table.row_count, 9)
                self.assertIn('[custom]', str(table.get_row_at(8)[0]))
                self.assertIsNotNone(model.project(app.course()).percent)
                self.assertEqual(app.raw_course()['groups'][-1]['assignments'], [])
                await pilot.press('d')
                await pilot.pause()
                self.assertTrue(app.selected_assignment()['_disabled'])
                self.assertEqual(str(table.get_row_at(8)[1]), 'Disabled –')
                self.assertIsNone(model.project(app.course()).percent)
                self.assertFalse(next(iter(store.read('config.json')['local_assessments'].values()))[0]['enabled'])
                app.save_screenshot('canvas-custom.svg', path='/tmp')
            app = GradesApp(offline=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                table = app.query_one('#assignments', DataTable)
                table.move_cursor(row=8)
                await pilot.pause()
                self.assertTrue(app.selected_assignment()['_disabled'])
                await pilot.press('d')
                await pilot.pause()
                await pilot.press('e')
                await pilot.pause()
                self.assertIsInstance(app.screen, LocalAssessmentEditor)
                app.screen.query_one('#local-score', Input).value = '18'
                await pilot.click('#local-save')
                await pilot.pause()
                self.assertEqual(app.selected_assignment()['submission']['score'], 18)
                await pilot.press('a')
                await pilot.pause()
                self.assertIsInstance(app.screen, WeightEditor)
                self.assertEqual(app.screen.focused.id, 'weight-' + local_id)
                await pilot.click('#weight-edit-cancel')
                await pilot.pause()
                app.accept_browser_snapshot({**sample, 'source': 'browser'})
                await pilot.pause()
                self.assertEqual(app.query_one('#assignments', DataTable).row_count, 9)
                self.assertEqual(app.selected_assignment()['submission']['score'], 18)
                await pilot.press('delete')
                await pilot.pause()
                self.assertEqual(table.row_count, 8)
                self.assertFalse(next(iter(store.read('config.json')['local_assessments'].values())))
                await pilot.press('delete')
                await pilot.pause()
                self.assertEqual(table.row_count, 8)
                self.assertFalse(any(a.get('_local') for _, a in model.assignments(app.course())))
