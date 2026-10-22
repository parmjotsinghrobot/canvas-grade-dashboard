# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import itertools
import random
import unittest
from datetime import datetime, timezone
from canvas_grades import model


def assignment(id, points, score=None, **extra):
    return {"id": id, "name": f"Work {id}", "points_possible": points,
            "submission_types": ["online_upload"], "submission": {"score": score}, **extra}


def course(items, *, weighted=False, rules=None):
    return {"apply_assignment_group_weights": weighted,
            "groups": [{"id": 1, "name": "Work", "group_weight": 100, "assignments": items, "rules": rules or {}}]}


class Grades(unittest.TestCase):
    def test_cutoffs(self):
        for label, cutoff in model.GRADE_BANDS:
            self.assertEqual(model.letter(cutoff), label)
        self.assertEqual(model.letter(89.499), "A")
        self.assertEqual(model.letter(None), "—")

    def test_points_zero_is_fixed(self):
        c = course([assignment(1, 20, 0), assignment(2, 80)])
        self.assertAlmostEqual(model.project(c).percent, 80)
        self.assertEqual(model.letter(model.project(c).percent), "A-")
        self.assertIsNone(model.required(c, 84.5))
        self.assertAlmostEqual(model.required(c, 79.5), 99.375)

    def test_weighted(self):
        c = course([assignment(1, 20, 10)], weighted=True)
        c["groups"][0]["group_weight"] = 30
        c["groups"].append({"id": 2, "name": "Exam", "group_weight": 70, "assignments": [assignment(2, 200)]})
        self.assertAlmostEqual(model.project(c).percent, 85)
        self.assertAlmostEqual(model.project(c, 0).percent, 15)
        self.assertAlmostEqual(model.required(c, 84.5), (84.5-15)/.7)
        self.assertEqual(model.project(c).warnings, [])

    def test_drop_unequal_points(self):
        # Dropping 60/100 beats dropping 1/10, even though 10% is lower.
        c = course([assignment(1, 10, 1), assignment(2, 100, 60), assignment(3, 100, 100)], rules={"drop_lowest": 1})
        self.assertEqual(model.project(c).dropped, {2})
        self.assertAlmostEqual(model.project(c).percent, 101 / 110 * 100)

    def test_drop_matches_exhaustive_fractional_solution(self):
        rng = random.Random(212)
        for maximize in (True, False):
            for _ in range(80):
                rows = [(i, rng.randint(0, 100), rng.randint(1, 100)) for i in range(7)]
                never = {0, 2}
                chosen = model._best_subset(rows, 3, never, maximize)
                result = sum(r[1] for r in chosen) / sum(r[2] for r in chosen)
                options = [subset for subset in itertools.combinations(rows, 4) if never.issubset({r[0] for r in subset})]
                ratios = [sum(r[1] for r in subset)/sum(r[2] for r in subset) for subset in options]
                expected = (max if maximize else min)(ratios)
                self.assertAlmostEqual(result, expected)

    def test_never_drop(self):
        c = course([assignment(1, 10, 1), assignment(2, 10, 5), assignment(3, 10, 10)], rules={"drop_lowest": 1, "never_drop": [1]})
        self.assertEqual(model.project(c).dropped, {2})
        self.assertAlmostEqual(model.project(c).percent, 55)

    def test_excused_excluded_and_zero_weight(self):
        c = course([assignment(1, 10, 10), assignment(2, 100, 0, submission={"excused": True}),
                    assignment(3, 100, 0, omit_from_final_grade=True)], weighted=True)
        c["groups"].append({"id": 2, "name": "Practice", "group_weight": 0, "assignments": [assignment(4, 100, 0)]})
        self.assertEqual(model.project(c).percent, 100)

    def test_strict_only_overdue_online_unsubmitted(self):
        c = course([assignment(1, 10, due_at="2020-01-01T00:00:00Z"),
                    assignment(2, 10, due_at="2020-01-01T00:00:00Z", submission={"submitted_at": "2020-01-01T00:00:00Z"}),
                    assignment(3, 10, due_at="2020-01-01T00:00:00Z", submission_types=["on_paper"])])
        self.assertEqual(model.project(c).percent, 100)
        self.assertAlmostEqual(model.project(c, strict=True).percent, 200/3)
        self.assertEqual(model.project(c, strict=True, overrides={1: 80}).percent, 280/3)

    def test_resubmission_and_submission_status(self):
        a = assignment(1, 10, submission={"score": 2, "workflow_state": "submitted", "grade_matches_current_submission": False})
        self.assertIsNone(model.fixed_score(a))
        self.assertEqual(model.status(a), "Submitted · awaiting grade")
        self.assertFalse(model.submitted(assignment(2, 10, 10)))

    def test_empty_and_incomplete_models_warn(self):
        self.assertIsNone(model.project(course([])).percent)
        c = course([assignment(1, 10, 10)], weighted=True)
        c["groups"][0]["group_weight"] = 99
        self.assertEqual(model.project(c).percent, 99)
        self.assertIn("99%", model.project(c).warnings[0])
        c["groups"].append({"id": 2, "name": "Hidden exam", "group_weight": 1, "assignments": []})
        self.assertIn("unknown", model.project(c).warnings[0])
        self.assertIsNone(model.project(c).percent)

    def test_override_does_not_change_canvas_model(self):
        c = course([assignment(1, 10, 0), assignment(2, 10)])
        self.assertEqual(model.project(c, overrides={1: 90, 2: 90}).percent, 90)
        self.assertEqual(model.project(c).percent, 50)

    def test_extra_credit(self):
        c = course([assignment(1, 100, 90), assignment(2, 0, 5)])
        self.assertEqual(model.project(c).percent, 95)

    def test_required_recalculates_drop_choice(self):
        c = course([assignment(1, 10, 9), assignment(2, 10, 1), assignment(3, 10), assignment(4, 10)], rules={"drop_lowest": 1})
        self.assertAlmostEqual(model.required(c, 89.5), 89.25)
        need = model.required(c, 84.5)
        self.assertGreaterEqual(model.project(c, need).percent, 84.5-1e-8)
        self.assertLess(model.project(c, need-0.001).percent, 84.5)

    def test_nickname(self):
        self.assertEqual(model.title({"name": "nickname", "original_name": "ELECTENG 331 · Signals", "nickname": "Signals crew"}),
                         "Signals crew (ELECTENG 331 · Signals)")

    def test_custom_group_weights_are_immutable_and_preserve_drop_rules(self):
        c = course([assignment(1, 10, 2), assignment(2, 10, 8)], rules={"drop_lowest": 1})
        c["groups"].append({"id": 2, "name": "Exam", "assignments": [assignment(3, 100)], "rules": {}})
        custom = model.apply_weights(c, {"mode": "groups", "values": {"1": 30, "2": 70}})
        self.assertAlmostEqual(model.project(custom).percent, 94)
        self.assertEqual(model.project(custom).dropped, {1})
        self.assertFalse(c["apply_assignment_group_weights"])
        self.assertEqual(c["groups"][0]["group_weight"], 100)
        self.assertIs(model.apply_weights(c, None), c)

    def test_custom_assessment_weights_and_new_items_warn(self):
        c = course([assignment(1, 10, 5), assignment(2, 100)], rules={"drop_lowest": 1})
        custom = model.apply_weights(c, {"mode": "assignments", "values": {"1": 20, "2": 80}})
        self.assertAlmostEqual(model.project(custom).percent, 90)
        self.assertFalse(model.project(custom).dropped)
        self.assertIn("replace", model.project(custom).warnings[0])
        c["groups"][0]["assignments"].append(assignment(3, 50))
        custom = model.apply_weights(c, {"mode": "assignments", "values": {"1": 20, "2": 80}})
        self.assertTrue(any("New items" in w for w in model.project(custom).warnings))

    def test_assignment_progress_states_and_counts(self):
        items = [assignment(1, 10, 0),
                 assignment(2, 10, submission={"submitted_at": "2026-10-20T00:00:00Z"}),
                 assignment(3, 10, due_at="2099-01-01T00:00:00Z"),
                 assignment(4, 10, due_at="2000-01-01T00:00:00Z"),
                 assignment(5, 10, submission_types=["on_paper"]),
                 assignment(6, 10, submission={"excused": True})]
        self.assertEqual([model.status_kind(a) for a in items],
                         ["graded", "submitted", "not_done", "not_done", "offline", "excused"])
        self.assertEqual(model.status(items[0]), "Graded")
        self.assertEqual(model.status(items[1]), "Submitted · awaiting grade")
        self.assertEqual(model.status(items[2]), "Not done yet")
        self.assertEqual(model.status(items[3]), "Not done yet · overdue")
        self.assertEqual(model.status(items[4]), "Offline · status unknown")
        self.assertEqual(model.progress(course(items)), {"graded": 1, "submitted": 1, "not_done": 2, "offline": 1})

    def test_local_assessment_fills_empty_weighted_group(self):
        c = {'apply_assignment_group_weights': True, 'groups': [
            {'id': 1, 'name': 'Benchmark', 'group_weight': 20, 'assignments': []},
            {'id': 2, 'name': 'Exam', 'group_weight': 80, 'assignments': [assignment(2, 100)]}]}
        record = {'id': 'local-benchmark', 'group_id': 1, 'group_name': 'Benchmark', 'name': 'Benchmark test', 'points_possible': 20, 'score': 19, 'status': 'offline', 'enabled': True}
        self.assertIsNone(model.project(c).percent)
        merged = model.apply_local_assessments(c, [record])
        self.assertAlmostEqual(model.project(merged).percent, 99)
        self.assertAlmostEqual(model.project(merged, 0).percent, 19)
        self.assertAlmostEqual(model.required(merged, 89.5), 88.125)
        self.assertEqual(c['groups'][0]['assignments'], [])
        self.assertEqual(len(model.apply_local_assessments(merged, [record])['groups'][0]['assignments']), 1)
        disabled = model.apply_local_assessments(c, [{**record, 'enabled': False}])
        local = disabled['groups'][0]['assignments'][0]
        self.assertFalse(model.eligible(local))
        self.assertEqual(model.status_kind(local), 'disabled')
        self.assertEqual(model.progress(disabled), {'graded': 0, 'submitted': 0, 'not_done': 1, 'offline': 0})
        self.assertIsNone(model.project(disabled).percent)
        self.assertIsNone(model.project(model.apply_local_assessments(c, [])).percent)

    def test_local_pending_and_custom_assessment_weights(self):
        c = course([assignment(1, 100, 80)])
        record = {'id': 'local-test', 'group_id': 1, 'name': 'Manual test', 'points_possible': 20, 'score': None, 'status': 'submitted'}
        merged = model.apply_local_assessments(c, [record])
        local = merged['groups'][0]['assignments'][1]
        self.assertEqual(model.status(local), 'Submitted · awaiting grade')
        custom = model.apply_weights(merged, {'mode': 'assignments', 'values': {'1': 50, 'local-test': 50}})
        self.assertAlmostEqual(model.project(custom).percent, 90)
        self.assertAlmostEqual(model.project(custom, 0).percent, 40)
        pending = model.apply_local_assessments(c, [{**record, 'status': 'not_done'}])
        self.assertEqual(model.status(pending['groups'][0]['assignments'][1]), 'Not done yet')
        zero = model.apply_local_assessments(c, [{**record, 'score': 0}])
        self.assertEqual(model.status(zero['groups'][0]['assignments'][1]), 'Graded')

    def test_local_assessments_warn_about_duplicates_and_missing_groups(self):
        c = course([assignment(1, 10, 10)])
        record = {'id': 'local-work', 'group_id': 1, 'name': 'Work 1', 'points_possible': 10, 'score': 10}
        merged = model.apply_local_assessments(c, [record])
        self.assertTrue(any('double counting' in w for w in model.project(merged).warnings))
        missing = model.apply_local_assessments(c, [{**record, 'group_id': 999, 'group_name': 'Old group'}])
        self.assertTrue(any('unavailable' in w for w in model.project(missing).warnings))
        self.assertEqual(len(list(model.assignments(missing))), 2)
