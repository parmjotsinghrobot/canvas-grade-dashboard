# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""Synthetic example data only. Never interpreted as the user's results."""
from datetime import datetime, timezone


def snapshot():
    def a(id, name, points, score=None, submitted=False, due=None, **extra):
        return {"id": id, "name": name, "points_possible": points, "published": True,
                "submission_types": ["online_upload"], "due_at": due, **extra,
                "submission": {"score": score, "workflow_state": "graded" if score is not None else "submitted" if submitted else "unsubmitted",
                               "submitted_at": "2026-10-20T10:00:00Z" if submitted else None,
                               "grade_matches_current_submission": True}}
    def g(id, name, weight, items, rules=None):
        return {"id": id, "name": name, "group_weight": weight, "assignments": items, "rules": rules or {}}
    names = [("COMPSYS 301", None, "Design Project"), ("COMPSYS 303", None, "Embedded Systems"),
             ("COMPSYS 304", None, "Computer Architecture"), ("ELECTENG 331", "Signals crew", "Signals and Systems")]
    courses = []
    for i, (code, nick, name) in enumerate(names, 1):
        groups = [g(1, "Coursework", 30, [a(i*100+1, "Assignment 1", 20, 18, True),
                                             a(i*100+2, "Assignment 2", 30, None, True)]),
                  g(2, "Tests", 25, [a(i*100+3, "Mid-semester test", 50, 41-i*2)]),
                  g(3, "Quizzes · best 3 of 4", 5, [a(i*100+10+j, f"Quiz {j+1}", 10, mark)
                                                    for j, mark in enumerate([9, 6, 10, None])], {"drop_lowest": 1}),
                  g(4, "Exam", 40, [a(i*100+4, "Final examination", 100, submission_types=["on_paper"])])]
        courses.append({"id": i, "name": f"{code} · {name}", "original_name": f"{code} · {name}",
                        "nickname": nick, "course_code": code, "term": {"name": "2026 Semester Two · EXAMPLE"},
                        "apply_assignment_group_weights": True, "groups": groups,
                        "enrollments": [{"computed_current_score": 82.3-i}]})
    return {"fetched_at": datetime.now(timezone.utc).isoformat(), "courses": courses,
            "warnings": [], "base_url": "https://canvas.example.edu", "demo": True}
