# SPDX-License-Identifier: GPL-3.0-or-later
"""Raw marks, contribution accounting, persistence and navigation regressions."""
import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import DataTable, Input, Static
from canvas_grades import demo, model, store
from canvas_grades.app import GradesApp, WhatIf
from canvas_grades.grade_bar import GradeBar, buckets


def assessment(aid, points, mark=None):
    return {'id': aid, 'name': f'Assessment {aid}', 'points_possible': points,
            'submission_types': ['on_paper'], 'submission': {'score': mark}}


def example(items):
    return {'groups': [{'id': 1, 'name': 'Coursework', 'group_weight': 100,
                        'assignments': items, 'rules': {}}]}


class Calculations(unittest.TestCase):
    def test_override_is_raw_mark_and_zero_point_extra_credit_works(self):
        original = example([assessment(1, 30)])
        self.assertEqual(model.project(original, overrides={1: 24}).percent, 80)
        self.assertIsNone(original['groups'][0]['assignments'][0]['submission']['score'])
        extra = example([assessment(1, 100, 90), assessment(2, 0)])
        self.assertEqual(model.project(extra, overrides={2: 5}).percent, 95)
        parts = model.Calculator(extra, overrides={2: 5}).contributions()
        self.assertAlmostEqual(sum(p.earned + p.remaining for p in parts), 95)

    def test_prepared_calculations_match_full_projection_with_drop_rules(self):
        rng = random.Random(331)
        for weighted in (False, True):
            for rule in ('drop_lowest', 'drop_highest', None):
                for _ in range(12):
                    course = {'apply_assignment_group_weights': weighted, 'groups': []}
                    for gid, weight in enumerate((15, 35, 50), 1):
                        items = [assessment(gid*10+i, rng.randint(1, 50),
                                            None if i % 2 else rng.randint(0, 20)) for i in range(5)]
                        course['groups'].append({'id': gid, 'name': f'Group {gid}', 'group_weight': weight,
                                                 'assignments': items, 'rules': {rule: 2, 'never_drop': [gid*10]} if rule else {}})
                    overrides = {11: 8}
                    calculator = model.Calculator(course, overrides=overrides)
                    frozen = copy.deepcopy(course)
                    for remaining in (0, 23.5, 80, 100):
                        expected = model.project(course, remaining, overrides=overrides).percent
                        self.assertAlmostEqual(calculator._percent(remaining), expected)
                    parts = calculator.contributions()
                    self.assertAlmostEqual(sum(p.earned + p.remaining for p in parts), calculator.project().percent)
                    self.assertAlmostEqual(sum(p.weight for p in parts), 100)
                    self.assertFalse(set(p.assignment_id for p in parts) & calculator.project().dropped)
                    low, high = calculator.project(0).percent, calculator.project().percent
                    target = low + .7*(high-low)
                    needed = calculator.required(target)
                    self.assertGreaterEqual(model.project(course, needed, overrides=overrides).percent, target-1e-8)
                    self.assertEqual(course, frozen)

    def test_small_assignments_share_group_bucket_and_large_ones_are_separate(self):
        course = example([assessment(i, 1, 1) for i in range(10)] + [assessment(20, 90)])
        parts = model.Calculator(course).contributions()
        grouped = buckets(parts)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0].name, 'Coursework')
        self.assertEqual(len(grouped[0].parts), 10)
        self.assertEqual(grouped[1].name, 'Assessment 20')
        weighted = model.apply_weights(course, {'mode': 'assignments', 'values': {str(i): 1 for i in range(10)} | {'20': 90}})
        self.assertEqual(len(buckets(model.Calculator(weighted).contributions())), 2)

    def test_zero_excused_disabled_overdue_and_unknown_groups(self):
        course = example([assessment(1, 10, 0), assessment(2, 10), assessment(3, 10), assessment(4, 10)])
        course['groups'][0]['assignments'][1].update(due_at='2020-01-01T00:00:00Z', submission_types=['online_upload'])
        course['groups'][0]['assignments'][2]['submission']['excused'] = True
        course['groups'][0]['assignments'][3]['_disabled'] = True
        parts = model.Calculator(course, strict=True).contributions()
        self.assertEqual([p.assignment_id for p in parts], [1, 2])
        self.assertEqual(sum(p.remaining for p in parts), 0)
        self.assertEqual(sum(p.lost for p in parts), 100)
        unknown = {'apply_assignment_group_weights': True, 'groups': [
            {'id': 1, 'name': 'Hidden exam', 'group_weight': 100, 'assignments': []}]}
        self.assertEqual(model.Calculator(unknown).contributions(), [])


class Scenarios(unittest.IsolatedAsyncioTestCase):
    async def test_raw_mark_validation_visible_override_restart_clear_and_host_isolation(self):
        snapshot = demo.snapshot()
        origin = snapshot['base_url']
        foreign = 'https://other.example|1'
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            store.write('snapshot.json', snapshot)
            store.write('config.json', {'whatifs': {foreign: {'unit': 'points', 'marks': {'102': 30}}}})
            app = GradesApp(offline=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                self.assertFalse(app.overrides)
                table = app.query_one('#assignments', DataTable)
                table.move_cursor(row=1)
                await pilot.pause()
                await pilot.press('w')
                await pilot.pause()
                self.assertIsInstance(app.screen, WhatIf)
                self.assertEqual(app.screen.maximum, 30)
                field = app.screen.query_one('#whatif-value', Input)
                field.value = '31'
                await pilot.click('#apply')
                await pilot.pause()
                self.assertIn('0 to 30', str(app.screen.query_one('#whatif-error', Static).render()))
                field.value = '24'
                await pilot.click('#apply')
                await pilot.pause()
                self.assertEqual(app.overrides[1][102], 24)
                self.assertEqual(str(table.get_row('102')[2]), '24/30*')
                self.assertEqual(str(table.get_row('102')[1]), 'Submitted')
                self.assertIn('*', str(app.query_one('#courses', DataTable).get_row('1')[4]))
                self.assertIn('24/30*', str(app.query_one('#assignment-detail', Static).render()))
                self.assertIsNone(app.raw_course()['groups'][0]['assignments'][1]['submission']['score'])
                entry = store.read('config.json')['whatifs'][origin+'|1']
                self.assertEqual(entry, {'unit': 'points', 'marks': {'102': 24}})
                self.assertEqual((Path(directory)/'config.json').stat().st_mode & 0o777, 0o600)
                app.action_strict()
                app.accept_browser_snapshot({**copy.deepcopy(snapshot), 'source': 'browser'})
                await pilot.pause()
                self.assertEqual(app.overrides[1][102], 24)
            app = GradesApp(offline=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                self.assertTrue(app.strict)
                self.assertEqual(str(app.query_one('#assignments', DataTable).get_row('102')[2]), '24/30*')
                app.query_one('#assignments', DataTable).move_cursor(row=1)
                await pilot.pause()
                await pilot.press('w')
                await pilot.pause()
                self.assertEqual(app.screen.query_one(Input).value, '24')
                app.screen.query_one(Input).value = ''
                await pilot.click('#apply')
                await pilot.pause()
                self.assertEqual(str(app.query_one('#assignments', DataTable).get_row('102')[2]), '—/30')
                self.assertNotIn(origin+'|1', store.read('config.json')['whatifs'])
                app.apply_whatif((102, 0))
                self.assertEqual(str(app.query_one('#assignments', DataTable).get_row('102')[2]), '0/30*')
                app.action_reset()
                self.assertFalse(app.strict)
                self.assertFalse(app.overrides)
                self.assertEqual(list(store.read('config.json')['whatifs']), [foreign])
            app = GradesApp(offline=True)
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.pause()
                self.assertFalse(app.overrides)
                self.assertFalse(app.strict)

    async def test_custom_mark_restores_by_string_id_and_delete_clears_saved_scenario(self):
        snapshot = demo.snapshot()
        key = snapshot['base_url']+'|1'
        record = {'id': 'local-extra', 'name': 'Custom test', 'group_id': 1,
                  'points_possible': 20, 'score': None, 'status': 'not_done', 'enabled': True}
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            store.write('snapshot.json', snapshot)
            store.write('config.json', {'local_assessments': {key: [record]}})
            app = GradesApp(offline=True)
            async with app.run_test(size=(130, 42)) as pilot:
                await pilot.pause()
                app.apply_whatif(('local-extra', 17.5))
            app = GradesApp(offline=True)
            async with app.run_test(size=(130, 42)) as pilot:
                await pilot.pause()
                self.assertEqual(app.overrides[1]['local-extra'], 17.5)
                self.assertEqual(str(app.query_one('#assignments', DataTable).get_row('local-extra')[2]), '17.5/20*')
                app.save_local_records([], deleted_id='local-extra')
                self.assertNotIn(key, store.read('config.json')['whatifs'])

    async def test_navigation_modal_cancel_and_resize_reuse_results_demo_does_not_save(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATA', Path(directory)):
            app = GradesApp(demo_mode=True)
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause()
                with patch.object(model, 'project', side_effect=AssertionError('Navigation must reuse projections')), patch.object(model.Calculator, '_percent', side_effect=AssertionError('Navigation must reuse targets')):
                    app.query_one('#assignments', DataTable).focus()
                    await pilot.press('down', 'down', 'up')
                    await pilot.pause()
                    await pilot.press('w')
                    await pilot.pause()
                    await pilot.click('#cancel-whatif')
                    await pilot.pause()
                    await pilot.resize_terminal(100, 35)
                    await pilot.pause()
                self.assertEqual(app.query_one('#assignments', DataTable).max_scroll_x, 0)
                bar = app.query_one(GradeBar)
                self.assertEqual(set(bar.colours), {101, 102, 103, 110, 112, 113, 104})
                table = app.query_one('#assignments', DataTable)
                columns, row = list(table.columns), table.rows[next(iter(table.rows))]
                app.apply_whatif((102, 24))
                self.assertEqual(list(table.columns), columns)
                self.assertIs(table.rows[next(iter(table.rows))], row)
                app.action_strict()
                self.assertFalse((Path(directory)/'config.json').exists())
                app.save_screenshot('canvas-new-features.svg', path='/tmp')
