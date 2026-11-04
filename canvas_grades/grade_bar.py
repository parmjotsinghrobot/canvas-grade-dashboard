# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact grade allocation bar with matching assessment-table colours."""
from dataclasses import dataclass, field
import math
from rich.text import Text
from rich.style import Style
from textual.widgets import Static

PALETTE = ('#f5c2e7', '#89b4fa', '#a6e3a1', '#fab387', '#cba6f7', '#94e2d5', '#f9e2af', '#b4befe')
LOST, UNKNOWN, MUTED = '#6c7086', '#f9e2af', '#a6adc8'


@dataclass
class Bucket:
    name: str
    parts: list = field(default_factory=list)

    @property
    def weight(self):
        return sum(p.weight for p in self.parts)


def buckets(parts):
    """Keep substantial assessments separate; combine small ones by group."""
    groups = {}
    for part in parts:
        key = ('group', part.group_id) if part.weight < 4 else ('assessment', part.assignment_id)
        if key not in groups:
            groups[key] = Bucket(part.group_name if key[0] == 'group' else part.name)
        groups[key].parts.append(part)
    result = list(groups.values())
    if len(result) > len(PALETTE):
        # Keep the largest assessments distinct without repeating colours.
        large = sorted(result, key=lambda b: b.weight, reverse=True)[:len(PALETTE)-1]
        other = Bucket('Other assessments', [p for b in result if all(b is not item for item in large) for p in b.parts])
        result = [*large, other]
    return result


class GradeBar(Static):
    def __init__(self, **kwargs):
        super().__init__('', markup=False, **kwargs)
        self.parts, self.groups, self.colours = [], [], {}
        self.available = False
        self.assumed = False
        self.highlighted_id = None
        self._segments = []
        self._layout_width = None
        self._layout = []

    def set_calculator(self, calculator):
        self.available = calculator.project().percent is not None
        self.parts = calculator.contributions()
        self.groups = buckets(self.parts)
        self.colours = {p.assignment_id: colour for group, colour in zip(self.groups, PALETTE) for p in group.parts}
        self.assumed = bool(calculator.overrides) or calculator.strict
        self._segments = []
        # Keep the group colours, but retain individual spans within each group
        # so selecting a small assessment lights up only its own contribution.
        for group, colour in zip(self.groups, PALETTE):
            for glyph in ('█', '░', '▒'):
                for part in group.parts:
                    amount = {'█': max(0, part.earned), '░': part.remaining, '▒': max(0, part.lost)}[glyph]
                    self._segments.append((amount, glyph, LOST if glyph == '▒' else colour, str(part.assignment_id)))
        unknown = max(0, 100 - sum(p.weight for p in self.parts))
        if unknown > .01:
            self._segments.append((unknown, '░', UNKNOWN, None))
        self._layout_width = None
        details = ['Course percentage points at the scenario ceiling. Drop choices may change with final marks.',
                   'Solid = counted mark; shaded = still available; grey = lost. Squares match assessment rows.']
        for group in self.groups:
            earned = sum(p.earned for p in group.parts)
            left = sum(p.remaining for p in group.parts)
            details.append(f'{group.name}: {earned:.2f}/{group.weight:.2f}% counted, {left:.2f}% available')
        self.tooltip = Text('\n'.join(details))
        self.update(self.bar_text())

    def on_resize(self):
        self.update(self.bar_text())

    def highlight(self, assignment_id):
        assignment_id = str(assignment_id) if assignment_id is not None else None
        if assignment_id != self.highlighted_id:
            self.highlighted_id = assignment_id
            self.update(self.bar_text())

    def segment_layout(self):
        """Cache cell allocation: hovering changes styling, not calculations."""
        width = max(1, self.content_size.width)
        if width != self._layout_width:
            scale = sum(amount for amount, _, _, _ in self._segments)
            sizes = [amount / scale * width for amount, _, _, _ in self._segments] if scale else []
            cells = [math.floor(size) for size in sizes]
            for i in sorted(range(len(cells)), key=lambda i: sizes[i] - cells[i], reverse=True)[:width - sum(cells)]:
                cells[i] += 1
            self._layout = [(glyph * count, colour, aid) for (_, glyph, colour, aid), count in zip(self._segments, cells) if count]
            self._layout_width = width
        return self._layout

    def bar_text(self):
        if not self.available:
            return Text('Grade contribution unavailable · review course warnings', style=MUTED)
        earned = sum(p.earned for p in self.parts)
        remaining = sum(p.remaining for p in self.parts)
        lost = sum(max(0, p.lost) for p in self.parts)
        unknown = max(0, 100 - sum(p.weight for p in self.parts))
        star = '*' if self.assumed else ''
        text = Text(f'Counted{star} {earned:.1f}% · Left {remaining:.1f}% · Lost {lost:.1f}%', style=MUTED)
        if unknown > .01:
            text.append(f' · Unallocated {unknown:.1f}%', style=UNKNOWN)
        text.append('\n')
        for glyphs, colour, aid in self.segment_layout():
            selected = self.highlighted_id is not None and aid == self.highlighted_id
            dimmed = self.highlighted_id is not None and not selected
            # Explicit muted colours also work on terminals without ANSI dim.
            text.append(glyphs, style=Style(color='#45475a' if dimmed else colour,
                                            dim=dimmed, bold=selected,
                                            underline=selected))
        part = next((p for p in self.parts if str(p.assignment_id) == self.highlighted_id), None)
        if part:
            label = Text(part.name, style=self.colours[part.assignment_id])
            amounts = f' · {part.earned:.2f}/{part.weight:.2f}% · {part.remaining:.2f}% left'
            label.truncate(max(1, min(24, self.content_size.width - len(amounts))), overflow='ellipsis')
            caption = label
            caption.append(amounts, style=MUTED)
        elif self.highlighted_id is not None:
            caption = Text('Selected assessment: no contribution (dropped or excluded)', style=MUTED)
        else:
            caption = Text('■ counted  ░ available  ▒ lost · ceiling drop choices', style=MUTED)
        scale = sum(amount for amount, _, _, _ in self._segments)
        if scale > 100.01:
            caption.append(f' · {scale:.1f}% scale', style=UNKNOWN)
        # Hovering must not reflow the table and move the row under the pointer.
        caption.truncate(max(1, self.content_size.width), overflow='ellipsis')
        text.append('\n')
        text.append(caption)
        return text
