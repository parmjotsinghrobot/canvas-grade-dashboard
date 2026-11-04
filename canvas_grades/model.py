# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""Pure grade calculations. What-if overrides use raw assessment marks."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math

GRADE_BANDS = (("A+", 89.5), ("A", 84.5), ("A-", 79.5), ("B+", 74.5),
               ("B", 69.5), ("B-", 64.5), ("C+", 59.5), ("C", 54.5),
               ("C-", 49.5), ("D+", 44.5), ("D", 39.5), ("D-", 0.0))


def letter(percent: float | None) -> str:
    if percent is None:
        return "—"
    return next(label for label, cutoff in GRADE_BANDS if percent + 1e-9 >= cutoff)


def title(course: dict) -> str:
    real = course.get("original_name") or course.get("name") or course.get("course_code", "Course")
    nick = course.get("nickname")
    return f"{nick} ({real})" if nick and nick != real else real


def submission(a: dict) -> dict:
    return a.get("submission") or {}


def submitted(a: dict) -> bool:
    s = submission(a)
    # A manually entered grade does not establish that a file was submitted.
    return bool(s.get("submitted_at") or s.get("attempt", 0) or
                s.get("workflow_state") in ("submitted", "pending_review"))


def fixed_score(a: dict) -> float | None:
    s = submission(a)
    value = s.get("score")
    if s.get("grade_matches_current_submission") is False and s.get("workflow_state") in ("submitted", "pending_review"):
        return None
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def due(a: dict) -> datetime | None:
    raw = submission(a).get("cached_due_date") or a.get("due_at")
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        return d.replace(tzinfo=timezone.utc) if d and not d.tzinfo else d
    except (ValueError, TypeError):
        return None


def overdue(a: dict, now: datetime | None = None) -> bool:
    deadline = due(a)
    return bool(deadline and deadline < (now or datetime.now(timezone.utc)) and not submitted(a)
                and fixed_score(a) is None and not submission(a).get("excused")
                and not set(a.get("submission_types", [])).issubset({"none", "on_paper"}))


def status_kind(a: dict) -> str:
    if a.get("_disabled"):
        return "disabled"
    if submission(a).get("excused"):
        return "excused"
    if fixed_score(a) is not None:
        return "graded"
    if submitted(a):
        return "submitted"
    if set(a.get("submission_types", [])).issubset({"none", "on_paper"}):
        return "offline"
    return "not_done"


def status(a: dict) -> str:
    s, kind = submission(a), status_kind(a)
    if kind == "disabled":
        return "Disabled · excluded from calculations"
    if kind == "excused":
        return "Excused"
    if kind == "graded":
        suffix = " · late" if s.get("late") else " · missing" if s.get("missing") else ""
        return "Graded" + suffix
    if kind == "submitted":
        return "Submitted · awaiting grade" + (" · late" if s.get("late") else "")
    if kind == "offline":
        return "Offline · status unknown"
    return "Not done yet" + (" · overdue" if overdue(a) or s.get("missing") else "")


def progress(course: dict) -> dict[str, int]:
    counts = dict.fromkeys(("graded", "submitted", "not_done", "offline"), 0)
    for _, a in assignments(course):
        kind = status_kind(a)
        if a.get("published", True) and kind in counts:
            counts[kind] += 1
    return counts


def eligible(a: dict) -> bool:
    return (not a.get("_disabled") and a.get("published", True) and not a.get("omit_from_final_grade")
            and a.get("grading_type") != "not_graded" and not submission(a).get("excused"))


def assignments(course: dict):
    for group in course.get("groups", []):
        for a in group.get("assignments", []):
            yield group, a


def _best_subset(rows: list[tuple], count: int, never: set, maximize: bool) -> list[tuple]:
    """Optimize sum(score)/sum(points), not individual percentages.

    Dinkelbach's fractional optimization: for a candidate ratio r, keeping
    the k largest score-r*points maximizes the residual. Mandatory rows stay.
    Handles unequal denominators in Canvas's drop-lowest rule.
    """
    mandatory = [r for r in rows if r[0] in never]
    options = [r for r in rows if r[0] not in never]
    keep = max(len(mandatory), len(rows) - min(count, len(options), len(rows) - 1))
    ratio = sum(r[1] for r in rows) / max(sum(r[2] for r in rows), 1e-12)
    chosen = rows
    for _ in range(100):
        ranked = sorted(options, key=lambda r: (r[1] - ratio * r[2], str(r[0])), reverse=maximize)
        chosen = mandatory + ranked[:max(0, keep - len(mandatory))]
        denom = sum(r[2] for r in chosen)
        if denom <= 0:
            return rows
        new = sum(r[1] for r in chosen) / denom
        if abs(new - ratio) < 1e-12:
            break
        ratio = new
    return chosen


@dataclass
class Projection:
    percent: float | None
    dropped: set
    warnings: list[str]


def project(course: dict, remaining: float = 100.0, *, strict: bool = False,
            overrides: dict | None = None) -> Projection:
    overrides = overrides or {}
    weighted = bool(course.get("apply_assignment_group_weights"))
    total, denominator = 0.0, 0.0
    warnings, dropped = [*course.get("_structure_warnings", []), *course.get("_local_warnings", []), *course.get("_weight_warnings", [])], set()
    incomplete = False
    groups = course.get("groups", [])
    if weighted:
        weight_sum = sum(float(g.get("group_weight") or 0) for g in groups)
        if abs(weight_sum - 100) > .01:
            warnings.append(f"Visible group weights total {weight_sum:g}%, not 100%; ceiling is provisional.")
    for g in groups:
        if weighted and not g.get("group_weight"):
            continue
        rows = []
        for a in g.get("assignments", []):
            if not eligible(a):
                continue
            points = float(a.get("points_possible") or 0)
            score = fixed_score(a)
            if a["id"] in overrides:
                score = overrides[a["id"]]
            elif score is None:
                score = 0 if strict and overdue(a) else points * remaining / 100
            if points == 0 and score:
                warnings.append(f"{g['name']}: zero-point extra credit is included only when the group has regular points.")
            rows.append((a["id"], score, points))
        if not rows or not sum(r[2] for r in rows):
            if weighted and g.get("group_weight"):
                warnings.append(f"{g['name']}: weighted group has no visible assessable points; its contribution is unknown.")
                incomplete = True
            continue
        rules = g.get("rules") or {}
        never = set(rules.get("never_drop", []))
        kept = rows
        for rule, maximize in (("drop_lowest", True), ("drop_highest", False)):
            count = int(rules.get(rule) or 0)
            if count:
                kept = _best_subset(kept, count, never, maximize)
        if rules.get("drop_lowest") and rules.get("drop_highest"):
            warnings.append(f"{g['name']}: combined highest/lowest drop rules require comparison with Canvas.")
        dropped.update({r[0] for r in rows} - {r[0] for r in kept})
        score, points = sum(r[1] for r in kept), sum(r[2] for r in kept)
        if weighted:
            total += float(g["group_weight"]) * score / points
            denominator = 100
        else:
            total += score
            denominator += points
    if not denominator:
        warnings.append("No assessable points are visible; no ceiling can be calculated.")
    for e in course.get("enrollments", []):
        if e.get("has_grading_periods"):
            warnings.append("Multiple grading periods are configured; period weighting is not modelled.")
            incomplete = True
    if course.get("hide_final_grades"):
        warnings.append("The instructor has hidden final grades.")
    if any(overdue(a) for _, a in assignments(course) if eligible(a)):
        warnings.append("Overdue unmarked work assumed recoverable." if not strict else "Overdue unsubmitted online work fixed at zero in this scenario.")
    return Projection(total / denominator * 100 if denominator and not incomplete else None, dropped, list(dict.fromkeys(warnings)))


def required(course: dict, target: float, *, strict=False, overrides=None) -> float | None:
    """Uniform mark needed on all unmarked work; drop rules are recalculated."""
    return Calculator(course, strict=strict, overrides=overrides).required(target)


@dataclass(frozen=True)
class Contribution:
    assignment_id: int | str
    name: str
    group_id: int | str
    group_name: str
    weight: float
    earned: float
    remaining: float
    assumed: bool = False

    @property
    def lost(self):
        return self.weight - self.earned - self.remaining


class Calculator:
    """Prepare a scenario once; reuse it for targets, navigation and resizing.

    Target searches need only numbers, not submission parsing or warnings on
    every iteration. Groups without drop rules reduce to a linear expression.
    Groups with rules still choose their retained items at every candidate mark.
    """
    def __init__(self, course, *, strict=False, overrides=None):
        self.course, self.strict, self.overrides = course, strict, dict(overrides or {})
        self.weighted = bool(course.get('apply_assignment_group_weights'))
        self.groups = []
        self._projections, self._percentages, self._targets = {}, {}, {}
        self._linear_score = self._linear_slope = self._linear_points = 0.0
        self._drop_groups = []
        for group in course.get('groups', []):
            weight = float(group.get('group_weight') or 0)
            if self.weighted and not weight:
                continue
            rows = []
            for a in group.get('assignments', []):
                if not eligible(a):
                    continue
                points = float(a.get('points_possible') or 0)
                score = self.overrides.get(a['id'], fixed_score(a))
                if score is None and strict and overdue(a):
                    score = 0.0
                rows.append((a, score, points))
            points = sum(row[2] for row in rows)
            if not points:
                continue
            rules = group.get('rules') or {}
            prepared = (group, rows, weight, rules, set(rules.get('never_drop', [])))
            self.groups.append(prepared)
            if rules.get('drop_lowest') or rules.get('drop_highest'):
                self._drop_groups.append(prepared)
            else:
                factor = weight / points if self.weighted else 1.0
                self._linear_score += sum(score or 0 for _, score, _ in rows) * factor
                self._linear_slope += sum(p for _, score, p in rows if score is None) * factor / 100
                self._linear_points += points

    def project(self, remaining=100.0):
        if remaining not in self._projections:
            self._projections[remaining] = project(self.course, remaining, strict=self.strict, overrides=self.overrides)
        return self._projections[remaining]

    def _percent(self, remaining):
        if remaining in self._percentages:
            return self._percentages[remaining]
        total = self._linear_score + self._linear_slope * remaining
        denominator = 100.0 if self.weighted else self._linear_points
        for _, prepared, weight, rules, never in self._drop_groups:
            rows = [(a['id'], points * remaining / 100 if score is None else score, points)
                    for a, score, points in prepared]
            for rule, maximize in (('drop_lowest', True), ('drop_highest', False)):
                count = int(rules.get(rule) or 0)
                if count:
                    rows = _best_subset(rows, count, never, maximize)
            score, points = sum(r[1] for r in rows), sum(r[2] for r in rows)
            total += weight * score / points if self.weighted else score
            if not self.weighted:
                denominator += points
        value = total / denominator * 100 if denominator else None
        self._percentages[remaining] = value
        return value

    def required(self, target):
        if target in self._targets:
            return self._targets[target]
        high, low = self.project(100).percent, self.project(0).percent
        if high is None or high + 1e-8 < target:
            value = None
        elif low is not None and low >= target - 1e-8:
            value = 0.0
        elif not self._drop_groups:
            value = min(100.0, math.nextafter((target - low) / (high - low) * 100, math.inf))
        else:
            left, right = 0.0, 100.0
            for _ in range(42):
                mid = (left + right) / 2
                if self._percent(mid) >= target:
                    right = mid
                else:
                    left = mid
            value = right
        self._targets[target] = value
        return value

    def contributions(self):
        """Course percentage points, using this scenario's ceiling drop choice."""
        projection = self.project()
        if projection.percent is None:
            return []
        kept_groups = [(g, [(a, score, p) for a, score, p in rows if a['id'] not in projection.dropped], weight)
                       for g, rows, weight, _, _ in self.groups]
        total_points = sum(p for _, rows, _ in kept_groups for _, _, p in rows)
        parts = []
        for group, rows, weight in kept_groups:
            denominator = sum(row[2] for row in rows) if self.weighted else total_points
            factor = (weight if self.weighted else 100) / denominator
            for a, score, points in rows:
                parts.append(Contribution(a['id'], a['name'], group.get('_source_group_id', group['id']), group['name'],
                                          points * factor, (score or 0) * factor,
                                          points * factor if score is None else 0,
                                          a['id'] in self.overrides))
        return parts


def official_score(course: dict) -> float | None:
    for e in course.get("enrollments", []):
        value = e.get("computed_current_score", (e.get("grades") or {}).get("current_score"))
        if value is not None:
            return float(value)
    return None


def apply_weights(course: dict, settings: dict | None) -> dict:
    """Return a calculation view; never mutate the downloaded Canvas snapshot."""
    if not settings or settings.get("mode") not in ("groups", "assignments") or course.get("error"):
        return course
    values = settings.get("values", {})
    mode = settings["mode"]
    warnings = []
    if mode == "groups":
        groups = [{**g, "group_weight": float(values.get(str(g["id"]), 0))} for g in course.get("groups", [])]
        new = [g["name"] for g in course.get("groups", []) if str(g["id"]) not in values]
    else:
        groups = []
        new = []
        for g, a in assignments(course):
            # Keep non-counting items visible in the assessment table.
            assessable = eligible(a) and (a.get("points_possible") or 0) > 0
            weight = float(values.get(str(a["id"]), 0)) if assessable else 0
            groups.append({"id": a["id"], "name": g["name"], "_source_group_id": g.get('_source_group_id', g['id']),
                           "group_weight": weight, "assignments": [a], "rules": {}})
            if assessable and str(a["id"]) not in values:
                new.append(a["name"])
        warnings.append("Custom assessment weights replace Canvas group weights and drop rules.")
    if new:
        warnings.append("New items have no saved weight (currently 0%): " + ", ".join(new) + ". Press g to review.")
    return {**course, "groups": groups, "apply_assignment_group_weights": True,
            "_weights_mode": mode, "_weight_warnings": warnings}


def apply_local_assessments(course: dict, records: list[dict] | None) -> dict:
    """Merge saved manual records into a calculation view, leaving Canvas untouched."""
    if not records or course.get('error'):
        return course
    groups = [{**g, 'assignments': [a for a in g.get('assignments', []) if not a.get('_local')]}
              for g in course.get('groups', []) if not g.get('_local_missing_group')]
    by_id = {g['id']: g for g in groups}
    warnings = []
    active = sum(r.get('enabled', True) for r in records)
    if active:
        warnings.append(f"Includes {active} enabled custom assessment(s); these entries are local, not official Canvas assessments.")
    for record in records:
        gid = record['group_id']
        if gid not in by_id:
            group = {'id': gid, 'name': record.get('group_name', 'Group no longer on Canvas'),
                     'group_weight': 0, 'rules': {}, 'assignments': [], '_local_missing_group': True}
            groups.append(group)
            by_id[gid] = group
        group = by_id[gid]
        enabled = record.get('enabled', True)
        if enabled and group.get('_local_missing_group'):
            warnings.append(f"Custom assessment {record['name']}: its Canvas group is unavailable; edit it to select a current group.")
        official = [a for a in group['assignments'] if not a.get('_local') and a['name'].strip().casefold() == record['name'].strip().casefold()]
        if enabled and official:
            warnings.append(f"Canvas now has an assessment named {record['name']}; check for double counting and disable/delete the custom copy if appropriate.")
        state = record.get('status', 'not_done')
        score = record.get('score')
        group['assignments'].append({
            'id': record['id'], 'name': record['name'], 'points_possible': record['points_possible'],
            'published': True, 'grading_type': 'points', '_local': True, '_disabled': not enabled,
            'submission_types': ['on_paper'] if state == 'offline' else ['manual'],
            'submission': {'score': score, 'grade_matches_current_submission': True,
                           'workflow_state': 'graded' if score is not None else 'submitted' if state == 'submitted' else 'unsubmitted'},
        })
    return {**course, 'groups': groups, '_local_warnings': list(dict.fromkeys(warnings))}


def apply_course_structure(course: dict, settings: dict | None) -> dict:
    """Apply persistent local group/points/rule fixes without altering Canvas data."""
    if not settings or not settings.get('enabled', True) or course.get('error'):
        return course
    groups = [{**g, 'assignments': [dict(a) for a in g.get('assignments', [])]}
              for g in course.get('groups', [])]
    by_id = {str(g['id']): g for g in groups}
    for extra in settings.get('extra_groups', []):
        key = str(extra['id'])
        if key not in by_id:
            g = {**extra, 'assignments': []}
            groups.append(g)
            by_id[key] = g
    warnings = []
    for key, patch in settings.get('groups', {}).items():
        if key not in by_id:
            warnings.append(f"Local grading fix refers to a missing group ({key}); review the course setup.")
            continue
        by_id[key].update({k: v for k, v in patch.items() if k in ('name', 'group_weight', 'rules')})
    items = [(str(g['id']), a) for g in groups for a in g['assignments']]
    for g in groups:
        g['assignments'] = []
    seen = set()
    for gid, a in items:
        key = str(a['id'])
        seen.add(key)
        patch = settings.get('assignments', {}).get(key, {})
        target = str(patch.get('group_id', gid))
        if target not in by_id:
            warnings.append(f"{a['name']}: requested local group is missing; kept in its previous group.")
            target = gid
        changes = []
        if target != gid:
            changes.append('assignment group')
        old_points = a.get('points_possible') or 0
        new_points = patch.get('points_possible', old_points)
        raw_score = submission(a).get('score')
        if (patch.get('normalize_score') and old_points > 0 and old_points != new_points
                and isinstance(raw_score, (int, float)) and math.isfinite(raw_score)):
            a['submission'] = {**submission(a), 'score': raw_score / old_points * new_points}
            changes.append('score normalised to new points')
        for field in ('points_possible', 'omit_from_final_grade'):
            if field in patch:
                if a.get(field) != patch[field]:
                    changes.append(field.replace('_', ' '))
                a[field] = patch[field]
        if patch:
            # Keep the local adjustment visible after subsequent reapplication.
            a['_structure_adjusted'] = list(dict.fromkeys([*a.get('_structure_adjusted', []), *changes]))
        by_id[target]['assignments'].append(a)
    missing = set(settings.get('assignments', {})) - seen
    if missing:
        warnings.append('Some locally configured assessments are absent from this snapshot; review the course setup.')
    order = {str(gid): i for i, gid in enumerate(settings.get('group_order', []))}
    if order:
        groups.sort(key=lambda g: order.get(str(g['id']), len(order)))
    return {**course, 'groups': groups,
            'apply_assignment_group_weights': settings.get('weighted', course.get('apply_assignment_group_weights', False)),
            '_structure_label': settings.get('label', 'Local grading structure'),
            '_structure_warnings': warnings}
