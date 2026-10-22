# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""Build explicit local correction settings from a reviewed Canvas snapshot."""
import re
from . import model


def ee331_structure(course: dict, test2_points: float = 30) -> dict:
    def group(name):
        matches = [g for g in course.get('groups', []) if g['name'].strip().casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError(f'Expected one {name} group; review the course before applying the fix.')
        return matches[0]
    test1, test2 = group('Test 1'), group('Test 2')
    labs, ice, exam = group('Laboratories'), group('In-Class Exercise (ICE)'), group('Exam (Lane 1)')
    tests = [a for _, a in model.assignments(course) if re.search(r'\bTest\s+2\b', a['name'], re.I)]
    exams = [a for _, a in model.assignments(course) if re.search(r'\bexam\b', a['name'], re.I)
             and not re.search(r'practice|mock|sample|lane\s*2', a['name'], re.I)]
    if len(tests) != 1 or len(exams) != 1:
        raise ValueError('Test 2 or the final exam is ambiguous; review the assignments before applying the fix.')
    weeks = {}
    for _, a in model.assignments(course):
        match = re.search(r'\bICE\s+Week\s+(\d+)\b', a['name'], re.I)
        if match:
            week = int(match[1])
            if week in weeks:
                raise ValueError('Multiple ICE assessments for one week; review the course before applying the fix.')
            weeks[week] = a
    if set(weeks) != set(range(1, 13)):
        raise ValueError('Expected ICE weeks 1 through 12 before applying the best-three-per-half rule.')
    second_id = f"ice-second-half-{ice['id']}"
    groups = {str(g['id']): {'group_weight': 0} for g in course.get('groups', [])}
    for g, weight in ((test1, 15), (test2, 15), (labs, 24), (exam, 40)):
        groups[str(g['id'])] = {'group_weight': weight}
    groups[str(ice['id'])] = {'name': 'ICE weeks 1–6 · best 3/6', 'group_weight': 3,
                            'rules': {'drop_lowest': 3, 'drop_highest': 0, 'never_drop': []}}
    extra = {'id': second_id, 'name': 'ICE weeks 7–12 · best 3/6', 'group_weight': 3,
             'rules': {'drop_lowest': 3, 'drop_highest': 0, 'never_drop': []}}
    assignments = {
        str(tests[0]['id']): {'group_id': test2['id'], 'points_possible': test2_points},
        str(exams[0]['id']): {'group_id': exam['id'], 'omit_from_final_grade': False},
    }
    for week, a in weeks.items():
        assignments[str(a['id'])] = {'group_id': ice['id'] if week <= 6 else second_id,
                                      'points_possible': 1, 'normalize_score': True, 'omit_from_final_grade': False}
    return {'enabled': True, 'label': 'EE331 local structure', 'weighted': True,
            'groups': groups, 'extra_groups': [extra], 'assignments': assignments,
            'group_order': [test1['id'], test2['id'], labs['id'], ice['id'], second_id, exam['id']],
            'notes': ['User-supplied course weights: 15/15/24/6/40.',
                      'ICE weeks 1–6 and 7–12 are best three of six each, 3% per half.',
                      'ICE assessments are normalised to one point; Test 2 is out of 30.',
                      'Exam moved locally to the 40% Lane 1 group.']}
