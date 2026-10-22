# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from textual.widgets import DataTable, Static
from canvas_grades import model, store
from canvas_grades.app import GradesApp
from canvas_grades.course_fixes import ee331_structure


def assessment(id, name, points, score=None, omitted=False):
    return {'id':id, 'name':name, 'points_possible':points, 'omit_from_final_grade':omitted,
            'submission_types':['on_paper'], 'submission':{'score':score, 'workflow_state':'graded' if score is not None else 'unsubmitted'}}


def example():
    def group(id,name,weight,items):
        return {'id':id,'name':name,'group_weight':weight,'rules':{},'assignments':items}
    weeks = [assessment(200+i,f'ICE Week {i} (Lane 2)',1 if i==1 else 0,
                        1 if i in [2,3,4,5,7,8,9] else None,omitted=i==1) for i in range(1,13)]
    return {'id':123,'name':'Example signals course','course_code':'ELECTENG 331','apply_assignment_group_weights':True,
            'groups':[group(1,'Test 1',15,[assessment(101,'Test 1 (Lane 1)',25,20)]),
                      group(2,'Test 2',15,[assessment(102,'Test 2 (Lane 1)',0)]),
                      group(3,'Laboratories',24,[assessment(110+i,f'Lab {i}',6) for i in range(1,5)]),
                      group(4,'In-Class Exercise (ICE)',6,weeks),group(5,'Exam (Lane 1)',40,[]),
                      group(6,'Final Exam 2026 S2',0,[assessment(300,'In-person invigilated exam on paper',100)])]}


class Structure(unittest.TestCase):
    def test_ee331_fixes_groups_points_drops_and_preserves_source(self):
        original = example()
        frozen = copy.deepcopy(original)
        settings = ee331_structure(original,30)
        c = model.apply_course_structure(original,settings)
        self.assertEqual(original,frozen)
        by_id = {g['id']:g for g in c['groups']}
        self.assertEqual(by_id[2]['assignments'][0]['points_possible'],30)
        self.assertIsNone(model.fixed_score(by_id[2]['assignments'][0]))
        self.assertEqual(by_id[5]['assignments'][0]['id'],300)
        self.assertEqual(by_id[6]['assignments'],[])
        self.assertEqual(sum(g['group_weight'] for g in c['groups']),100)
        for gid in (4,'ice-second-half-4'):
            g = by_id[gid]
            self.assertEqual(len(g['assignments']),6)
            self.assertEqual(g['group_weight'],3)
            self.assertEqual(g['rules']['drop_lowest'],3)
            self.assertTrue(all(a['points_possible']==1 and not a['omit_from_final_grade'] for a in g['assignments']))
        self.assertAlmostEqual(model.project(c).percent,97)
        self.assertAlmostEqual(model.project(c,0).percent,18)
        self.assertAlmostEqual(model.required(c,89.5),(89.5-18)/79*100)
        self.assertFalse(model.project(c).warnings)
        again = model.apply_course_structure(c,settings)
        self.assertEqual(len(list(model.assignments(again))),len(list(model.assignments(c))))
        self.assertAlmostEqual(model.project(again).percent,97)
        exam = next(g for g in again['groups'] if g['id'] == 5)
        self.assertTrue(exam['assignments'][0]['_structure_adjusted'])
        # If Canvas later publishes real ICE denominators, keep their fractions.
        future = copy.deepcopy(original)
        future['groups'][3]['assignments'][1]['points_possible'] = 10
        future['groups'][3]['assignments'][1]['submission']['score'] = 10
        normalised = model.apply_course_structure(future,settings)
        item = next(a for _,a in model.assignments(normalised) if a['id'] == 202)
        self.assertEqual(item['submission']['score'],1)
        self.assertEqual(future['groups'][3]['assignments'][1]['submission']['score'],10)
        self.assertAlmostEqual(model.project(normalised).percent,97)

    def test_best_three_are_independent_in_each_half(self):
        original=example()
        for _, a in model.assignments(original):
            if a['name'].startswith('ICE Week'):
                week=int(a['name'].split()[2])
                a['submission']['score']=0 if week<=6 else 1
        c=model.apply_course_structure(original,ee331_structure(original))
        self.assertAlmostEqual(model.project(c).percent,94)
        self.assertAlmostEqual(model.project(c,0).percent,15)
        ice_drops=[a['id'] for g,a in model.assignments(c) if a['id'] in model.project(c).dropped]
        self.assertEqual(len(ice_drops),6)

    def test_correction_can_be_disabled_and_missing_items_warn(self):
        original=example()
        settings=ee331_structure(original)
        self.assertIs(model.apply_course_structure(original,{**settings,'enabled':False}),original)
        original['groups'][-1]['assignments']=[]
        c=model.apply_course_structure(original,settings)
        self.assertTrue(any('absent' in w for w in model.project(c).warnings))
        self.assertIsNone(model.project(c).percent)


class StructureApp(unittest.IsolatedAsyncioTestCase):
    async def test_saved_structure_applies_on_launch_and_fresh_import(self):
        original=example()
        snapshot={'base_url':'https://canvas.example.edu','fetched_at':'2026-10-21T10:00:00+00:00','courses':[original],'warnings':[]}
        key='https://canvas.example.edu|123'
        with tempfile.TemporaryDirectory() as directory, patch.object(store,'DATA',Path(directory)):
            store.write('snapshot.json',snapshot)
            store.write('config.json',{'base_url':snapshot['base_url'],'course_structure':{key:ee331_structure(original)}})
            app=GradesApp(offline=True)
            async with app.run_test(size=(150,45)) as pilot:
                await pilot.pause()
                self.assertAlmostEqual(model.project(app.course()).percent,97)
                self.assertIn('EE331 local structure',str(app.query_one('#summary',Static).render()))
                table=app.query_one('#assignments',DataTable)
                self.assertEqual(table.row_count,19)
                self.assertEqual(app.raw_course()['groups'][1]['assignments'][0]['points_possible'],0)
                app.accept_browser_snapshot(snapshot)
                await pilot.pause()
                self.assertAlmostEqual(model.project(app.course()).percent,97)
                self.assertEqual(table.row_count,19)
                self.assertIn(key,store.read('config.json')['course_structure'])
