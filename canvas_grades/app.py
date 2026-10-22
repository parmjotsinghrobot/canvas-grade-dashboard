# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
from __future__ import annotations
import math
import os
from datetime import datetime
from uuid import uuid4
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input,
                             Label, LoadingIndicator, Select, SelectionList, Static)
from pathlib import Path
from . import api, browser_sync, demo, model, store

PINK = "#f5c2e7"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
MUTED = "#a6adc8"
RED = "#f38ba8"
TZ = None  # Use the operating system timezone for each displayed date.


def fmt(value):
    return "—" if value is None else f"{value:.2f}%"


def colored(value, color=PINK):
    return Text(value, style=color)


class Setup(ModalScreen):
    def __init__(self, base=""):
        super().__init__()
        self.base = base

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Connect to Canvas", classes="dialog-title")
            yield Static("Create a token in Canvas → Account → Settings → New Access Token.\nPaste it below. Access is read-only; this app only sends GET requests.", classes="explanation")
            yield Input(value=self.base, id="url", placeholder="https://canvas.example.edu")
            yield Input(password=True, id="token", placeholder="Canvas access token")
            yield Checkbox("Remember token locally (private file, mode 0600)", id="remember", value=True)
            yield Static("", id="setup-error")
            with Horizontal(classes="buttons"):
                yield Button("Connect", variant="primary", id="connect")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self.query_one("#token", Input).focus()

    @on(Input.Submitted)
    @on(Button.Pressed, "#connect")
    def connect(self):
        try:
            url = api.base_url(self.query_one("#url", Input).value)
            token = self.query_one("#token", Input).value.strip()
            api.Client(url, token)
        except api.CanvasError as e:
            self.query_one("#setup-error", Static).update(str(e))
            return
        self.dismiss((url, token, self.query_one("#remember", Checkbox).value))

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(None)


class BrowserConnect(ModalScreen):
    def __init__(self, base=""):
        super().__init__()
        self.base = base

    def compose(self):
        with Vertical(id="dialog"):
            yield Static("Connect using your browser", classes="dialog-title")
            yield Static("Use your default browser and normal Canvas login.\nInstall the sync bookmark once, then click it on Canvas to download grades. The TUI picks up the download automatically. No access token needed.", classes="explanation")
            yield Input(value=self.base, id="browser-url", placeholder="https://canvas.example.edu")
            yield Static("", id="browser-error")
            with Horizontal(classes="buttons"):
                yield Button("Open browser login", id="browser-connect", variant="primary")
                yield Button("Use cookies", id="cookie-login")
            with Horizontal(classes="buttons"):
                yield Button("Use a token", id="token-login")
                yield Button("Cancel", id="browser-cancel")

    @on(Button.Pressed, "#browser-connect")
    @on(Input.Submitted)
    def connect(self):
        try:
            base = api.base_url(self.query_one(Input).value)
        except api.CanvasError as e:
            self.query_one("#browser-error", Static).update(str(e))
            return
        self.dismiss(base)

    @on(Button.Pressed, "#token-login")
    def token(self):
        self.dismiss(("token", self.query_one(Input).value))

    @on(Button.Pressed, "#cookie-login")
    def cookies(self):
        self.dismiss(("cookie", self.query_one(Input).value))

    @on(Button.Pressed, "#browser-cancel")
    def cancel(self):
        self.dismiss(None)


class CookieSetup(ModalScreen):
    def __init__(self, base=''):
        super().__init__()
        self.base = base

    def compose(self):
        with Vertical(id='cookie-dialog'):
            yield Static('Connect with Canvas cookies', classes='dialog-title')
            yield Static('Sign in to Canvas in your normal browser. In F12 → Network, reload Canvas and select a Canvas request. Copy its Cookie request-header value below.\n\nThe app reads grades directly using that session. Cookies grant account access: keep them local and replace them when the session expires.', classes='explanation')
            yield Input(value=self.base, id='cookie-url', placeholder='Canvas URL')
            yield Input(password=True, id='cookie-value', placeholder='Cookie request-header value')
            yield Checkbox('Remember cookies locally (private unencrypted file, mode 0600)', id='cookie-remember', value=False)
            yield Static('', id='cookie-error')
            with Horizontal(classes='buttons'):
                yield Button('Connect', id='cookie-connect', variant='primary')
                yield Button('Open Canvas', id='cookie-browser')
                yield Button('Cancel', id='cookie-cancel')

    def on_mount(self):
        self.query_one('#cookie-value', Input).focus()

    @on(Button.Pressed, '#cookie-browser')
    def open_canvas(self):
        try:
            base = api.base_url(self.query_one('#cookie-url', Input).value)
            if not browser_sync.open_canvas(base):
                self.query_one('#cookie-error', Static).update('Could not open the default browser. Open Canvas manually.')
        except (api.CanvasError, OSError) as e:
            self.query_one('#cookie-error', Static).update(str(e))

    @on(Button.Pressed, '#cookie-connect')
    @on(Input.Submitted)
    def connect(self):
        try:
            base = api.base_url(self.query_one('#cookie-url', Input).value)
            cookies = api.normalize_cookies(self.query_one('#cookie-value', Input).value)
        except api.CanvasError as e:
            self.query_one('#cookie-error', Static).update(str(e))
            return
        self.dismiss((base, cookies, self.query_one('#cookie-remember', Checkbox).value))

    @on(Button.Pressed, '#cookie-cancel')
    def cancel(self):
        self.dismiss(None)


class ImportSnapshot(ModalScreen):
    def compose(self):
        with Vertical(id="dialog"):
            yield Static("Import browser snapshot", classes="dialog-title")
            yield Static("Snapshots saved in Downloads are imported automatically.\nFor other folders, enter the downloaded canvas-grades-….json path.", classes="explanation")
            yield Input(id="snapshot-path", placeholder="/path/to/canvas-grades-….json")
            with Horizontal(classes="buttons"):
                yield Button("Import", id="import-file", variant="primary")
                yield Button("Cancel", id="cancel-import")

    @on(Button.Pressed, "#import-file")
    @on(Input.Submitted)
    def import_file(self):
        value = self.query_one(Input).value.strip()
        if value:
            self.dismiss(Path(value).expanduser())

    @on(Button.Pressed, "#cancel-import")
    def cancel(self):
        self.dismiss(None)


class Picker(ModalScreen):
    def __init__(self, courses, chosen=()):
        super().__init__()
        self.courses = courses
        self.chosen = set(chosen)

    def compose(self):
        with Vertical(id="picker-dialog"):
            yield Static("Choose this semester’s courses", classes="dialog-title")
            yield Static("Space toggles a course · select the correct semester from the term shown.\nYour selection is saved for future launches.", classes="explanation")
            options = []
            for c in self.courses:
                term = (c.get("term") or {}).get("name", "Term not supplied")
                options.append((f"{model.title(c)}  /  {term}", c["id"], c["id"] in self.chosen))
            yield SelectionList(*options, id="course-options")
            yield Static("", id="picker-error")
            with Horizontal(classes="buttons"):
                yield Button("Use selected courses", id="choose", variant="primary")
                yield Button("Cancel", id="cancel-picker")

    @on(Button.Pressed, "#choose")
    def choose(self):
        ids = self.query_one(SelectionList).selected
        if not ids:
            self.query_one("#picker-error", Static).update("Select at least one course.")
            return
        self.dismiss(ids)

    @on(Button.Pressed, "#cancel-picker")
    def cancel(self):
        self.dismiss(None)


class WhatIf(ModalScreen):
    def __init__(self, assignment, value=None):
        super().__init__()
        self.assignment = assignment
        self.value = value

    def compose(self):
        with Vertical(id="dialog"):
            yield Static("What if…", classes="dialog-title")
            yield Static(self.assignment["name"], markup=False)
            yield Static("Enter a percentage for this assessment (0–100).\nThis changes a local scenario only. Leave blank to restore Canvas data.", classes="explanation")
            yield Input(value="" if self.value is None else str(self.value), placeholder="e.g. 85", id="whatif-value")
            yield Static("", id="whatif-error")
            with Horizontal(classes="buttons"):
                yield Button("Apply", id="apply", variant="primary")
                yield Button("Cancel", id="cancel-whatif")

    def on_mount(self):
        self.query_one(Input).focus()

    @on(Input.Submitted)
    @on(Button.Pressed, "#apply")
    def apply(self):
        raw = self.query_one(Input).value.strip()
        if not raw:
            self.dismiss((self.assignment["id"], None))
            return
        try:
            value = float(raw)
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError
        except ValueError:
            self.query_one("#whatif-error", Static).update("Enter a number from 0 to 100.")
            return
        self.dismiss((self.assignment["id"], value))

    @on(Button.Pressed, "#cancel-whatif")
    def cancel(self):
        self.dismiss(None)


class Dashboard(Screen):
    def on_resize(self):
        self.call_after_refresh(self.fit_tables)

    def on_screen_resume(self):
        self.call_after_refresh(self.fit_tables)

    def fit_tables(self):
        if self.is_mounted and self.app.snapshot and self.app.screen is self:
            self.app.render_snapshot()


class GradesApp(App):
    TITLE = "Canvas Grades"
    SUB_TITLE = "semester outlook"
    CSS_PATH = "style.tcss"
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("r", "refresh", "Refresh"),
                Binding("c", "courses", "Courses"), Binding("w", "whatif", "What if"),
                Binding("m", "strict", "Overdue = 0"), Binding("x", "reset", "Reset scenario"),
                Binding("g", "weights", "Weights"), Binding("a", "assessment_weights", "Assessment weight", show=False),
                Binding("n", "new_assessment", "Add assessment"),
                Binding("e", "edit_assessment", "Edit custom", show=False),
                Binding("d", "toggle_assessment", "Enable/disable custom", show=False),
                Binding("delete", "delete_assessment", "Delete custom", show=False),
                Binding("b", "browser", "Browser"), Binding("i", "import", "Import"),
                Binding("k", "cookies", "Cookies", show=False),
                Binding("t", "token", "Token", show=False), Binding("?", "help", "Help")]

    def __init__(self, *, demo_mode=False, offline=False):
        super().__init__()
        self.demo_mode, self.offline = demo_mode, offline
        self.snapshot = None
        self.catalog = []
        self.client = None
        self.strict = False
        self.overrides = {}
        self.current_id = None
        self.loading = False
        self.config = {}
        self.seen_downloads = set()
        self.browser_timer = None
        self.register_theme(Theme(name="mocha-pink", primary=PINK, secondary="#cba6f7", accent="#89b4fa",
                                  background="#1e1e2e", surface="#181825", panel="#313244",
                                  foreground="#cdd6f4", success=GREEN, warning=YELLOW, error=RED, dark=True))
        self.theme = "mocha-pink"

    def compose(self):
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Horizontal(id="masthead"):
                yield Static("CANVAS / SEMESTER OUTLOOK", id="brand")
                yield Static("", id="connection", markup=False)
            yield Static("", id="sync", markup=False)
            yield LoadingIndicator(id="loading")
            yield DataTable(id="courses", cursor_type="row", zebra_stripes=True)
            with Horizontal(id="detail"):
                with Vertical(id="work-panel"):
                    yield Static("Select a course", id="course-title", markup=False)
                    yield Static("", id="summary", markup=False)
                    yield DataTable(id="assignments", cursor_type="row", zebra_stripes=True)
                    yield Static("", id="assignment-detail", markup=False)
                with VerticalScroll(id="target-panel"):
                    yield Static("GRADE TARGETS", classes="section-label")
                    yield Static("Average needed on unmarked work", classes="muted")
                    yield DataTable(id="targets", cursor_type="row")
                    yield Static("", id="warnings", markup=False)
            yield Static("", id="assumptions", markup=False)
        yield Footer()

    def get_default_screen(self):
        return Dashboard(id="_default")

    def on_mount(self):
        self.query_one("#courses", DataTable).add_columns("Course", "Canvas current", "Ceiling", "Grade", "Scenario", "Graded", "Submitted", "Not done")
        self.query_one("#assignments", DataTable).add_columns("Assessment", "Status", "Mark", "Weight")
        targets = self.query_one("#targets", DataTable)
        for label, width in (("Grade", 4), ("Cutoff", 6), ("Need", 12)):
            targets.add_column(label, width=width)
        self.query_one("#loading").display = False
        try:
            self.config = store.read("config.json", {})
            if self.demo_mode:
                self.snapshot = demo.snapshot()
                self.render_snapshot()
            elif self.offline:
                self.snapshot = store.read("snapshot.json")
                if not self.snapshot:
                    self.set_message("No saved snapshot yet. Launch without --offline to connect.")
                else:
                    self.render_snapshot()
            else:
                token = os.environ.get("CANVAS_TOKEN") or store.read("credentials.json", {}).get("token")
                if self.config.get('auth_mode') == 'cookie' or os.environ.get('CANVAS_COOKIE'):
                    saved = store.read('session.json', {})
                    base = self.canvas_url()
                    cookies = os.environ.get('CANVAS_COOKIE') or (saved.get('cookie') if saved.get('base_url') == base else None)
                    if cookies:
                        self.client = api.CookieClient(base, cookies)
                        self.load()
                    else:
                        self.snapshot = store.read('snapshot.json')
                        if self.snapshot:
                            self.render_snapshot()
                        self.push_screen(CookieSetup(base), self.cookies_connected)
                elif token and self.config.get("auth_mode") != "browser":
                    self.client = api.Client(self.canvas_url(), token)
                    self.load()
                else:
                    self.start_browser_watch()
                    if self.config.get("auth_mode") == "browser":
                        self.snapshot = store.read("snapshot.json")
                        if self.snapshot:
                            self.render_snapshot()
                        else:
                            self.set_message("Press r to open Canvas, then use the sync bookmark. Press b for bookmark setup.")
                        self.poll_browser_downloads()
                    else:
                        self.push_screen(BrowserConnect(self.canvas_url()), self.browser_connected)
        except (ValueError, api.CanvasError) as e:
            self.set_message(str(e))

    def set_message(self, text):
        self.query_one("#sync", Static).update(text)

    def set_loading(self, value):
        self.loading = value
        self.query_one("#loading").display = value

    @work(exclusive=True, group="network", exit_on_error=False)
    async def load(self, choose=False):
        if not self.client or self.loading:
            return
        self.set_loading(True)
        self.set_message("Fetching courses and your Canvas nicknames…")
        try:
            self.catalog, warnings = await self.client.courses()
            selected = self.config.get("course_ids", [])
            if choose or not selected:
                self.set_loading(False)
                self.push_screen(Picker(self.catalog, selected), self.chosen)
                return
            courses = [c for c in self.catalog if c["id"] in selected]
            if not courses:
                raise api.CanvasError("Saved courses are unavailable. Press c to choose this semester’s courses.")
            self.set_message(f"Fetching grades and submissions for {len(courses)} courses…")
            result = await self.client.snapshot(courses, warnings)
            missing = set(selected) - {c["id"] for c in courses}
            if missing:
                result["warnings"].append("Some selected courses are no longer accessible. Press c to review the selection.")
            self.snapshot = result
            self.offline = False
            self.render_snapshot()
        except (api.CanvasError, ValueError, OSError) as e:
            self.set_message(str(e))
            self.notify(str(e), severity="error", timeout=8)
        finally:
            self.set_loading(False)

    def chosen(self, ids):
        if ids:
            self.config["course_ids"] = ids
            try:
                store.write("config.json", self.config)
            except OSError:
                self.notify("Could not save course selection.", severity="warning")
            self.load()
        else:
            self.set_message("Course selection cancelled. Press c to choose courses.")

    def connected(self, credentials):
        if not credentials:
            self.set_message("Connection cancelled. Press t to enter a token, or run --demo.")
            return
        base, token, remember = credentials
        self.client = api.Client(base, token)
        if self.config.get("base_url", base) != base:
            self.config.pop("course_ids", None)
        self.config["base_url"] = base
        self.config["auth_mode"] = "token"
        try:
            store.write("config.json", self.config)
            # Overwrite any old token even when choosing not to remember this one.
            store.write("credentials.json", {"token": token} if remember else {})
        except OSError:
            self.notify("Could not save settings; this session can still connect.", severity="warning")
        self.load()

    def render_snapshot(self):
        if not self.snapshot:
            return
        courses = self.snapshot["courses"]
        table = self.query_one("#courses", DataTable)
        table.styles.height = min(9, max(4, len(courses) + 3))
        selected = self.current_id
        table.clear(columns=True)
        # Keep long course names from pushing progress counts off-screen.
        widths = (9, 9, 5, 9, 6, 9, 8)
        available = max(0, table.content_size.width - 2)
        name_width = max(14, available - sum(widths) - 16)
        for label, width in zip(("Course", "Current", "Ceiling", "Grade", "Scenario", "Graded", "Submitted", "Not done"), (name_width, *widths)):
            table.add_column(label, width=width)
        for raw in courses:
            c = self.with_weights(raw)
            if c.get("error"):
                table.add_row(model.title(c), "—", colored("Fetch failed", RED), "—", "—", "—", "—", "—", key=str(c["id"]))
                continue
            ceiling = model.project(c)
            scenario = model.project(c, strict=self.strict, overrides=self.overrides.get(c["id"], {}))
            progress = model.progress(c)
            grade_color = GREEN if ceiling.percent is not None and ceiling.percent >= 79.5 else YELLOW
            estimate = "~" if ceiling.warnings and ceiling.percent is not None else ""
            table.add_row(model.title(c), fmt(model.official_score(c)), colored(estimate + fmt(ceiling.percent), PINK),
                          colored(model.letter(ceiling.percent), grade_color), fmt(scenario.percent),
                          colored(str(progress["graded"]), GREEN), colored(str(progress["submitted"]), YELLOW),
                          colored(str(progress["not_done"]), MUTED), key=str(c["id"]))
        if courses:
            row = next((i for i, c in enumerate(courses) if c["id"] == selected), 0)
            table.move_cursor(row=row)
            self.current_id = courses[row]["id"]
            self.render_course()
        label = "DEMO · SYNTHETIC DATA" if self.demo_mode else "OFFLINE · SAVED SNAPSHOT" if self.offline else "COOKIE SESSION · GET ONLY" if self.client and self.client.auth_mode == 'cookie' else "BROWSER · SAVED SNAPSHOT" if self.snapshot.get("source") == "browser" else "CONNECTED · GET ONLY"
        self.query_one("#connection", Static).update(label)
        stamp = datetime.fromisoformat(self.snapshot["fetched_at"]).astimezone(TZ).strftime("%d %b %Y, %H:%M %Z")
        self.set_message(f"Last fetched {stamp}" + (" · Sample results, not your marks" if self.demo_mode else ""))
        self.query_one("#assumptions", Static).update(
            "Ceiling = posted + 100% on unmarked work. ~ review warnings; course hurdles/scaling may apply.\n"
            + ("Scenario: overdue online work = 0. " if self.strict else "Scenario: overdue work recoverable. ")
            + "n add · a weights · w what-if · ? notes")

    def course(self):
        c = self.raw_course()
        return self.with_weights(c) if c else None

    def raw_course(self):
        return next((c for c in (self.snapshot or {}).get("courses", []) if c["id"] == self.current_id), None)

    def canvas_url(self):
        return self.config.get("base_url") or os.environ.get("CANVAS_URL", "")

    def weights_key(self, course):
        base = (self.snapshot or {}).get("base_url", self.canvas_url())
        return f"{'demo|' if self.demo_mode else ''}{base}|{course['id']}"

    def with_weights(self, course):
        return model.apply_weights(self.with_locals(course), self.config.get("weights", {}).get(self.weights_key(course)))

    def with_locals(self, course):
        structured = model.apply_course_structure(course, self.config.get("course_structure", {}).get(self.weights_key(course)))
        return model.apply_local_assessments(structured, self.config.get("local_assessments", {}).get(self.weights_key(course), []))

    @on(DataTable.RowHighlighted, "#courses")
    def course_highlighted(self, event):
        if event.row_key.value:
            self.current_id = int(event.row_key.value)
            self.render_course()

    def render_course(self):
        c = self.course()
        if not c:
            return
        self.query_one("#course-title", Static).update(model.title(c))
        items_table = self.query_one("#assignments", DataTable)
        selected = None
        if items_table.row_count:
            selected = items_table.coordinate_to_cell_key(items_table.cursor_coordinate).row_key.value
        items_table.clear(columns=True)
        # Four bounded columns fit together even with long assessment titles.
        available = max(0, items_table.content_size.width - 2)
        name_width = max(12, available - 10 - 9 - 7 - 8)
        for label, width in (("Assessment", name_width), ("Status", 10), ("Mark", 9), ("Weight", 7)):
            items_table.add_column(label, width=width)
        targets = self.query_one("#targets", DataTable)
        targets.clear()
        if c.get("error"):
            self.query_one("#warnings", Static).update(c["error"])
            self.query_one("#summary", Static).update("No grade calculated: the course data could not be fetched.")
            self.query_one("#assignment-detail", Static).update("")
            return
        overrides = self.overrides.get(c["id"], {})
        ceiling = model.project(c)
        scenario = model.project(c, strict=self.strict, overrides=overrides)
        floor = model.project(c, 0)
        all_items = list(model.assignments(c))
        progress = model.progress(c)
        heading = Text.assemble((f"{progress['graded']} graded", GREEN), " · ",
                                (f"{progress['submitted']} submitted", YELLOW), " · ",
                                (f"{progress['not_done']} not done yet", MUTED))
        if progress["offline"]:
            heading.append(f" · {progress['offline']} offline", style=MUTED)
        heading.append("\n" + (f"Custom {'group' if c['_weights_mode'] == 'groups' else 'assessment'} weights" if c.get('_weights_mode') else c.get('_structure_label', "Canvas weights"))
                       + f" · Zero on remaining: {fmt(floor.percent)}", style=MUTED)
        self.query_one("#summary", Static).update(heading)
        for g, a in all_items:
            score = model.fixed_score(a)
            points = a.get("points_possible") or 0
            mark = f"{score:g}/{points:g}" if score is not None else f"—/{points:g}"
            kind = model.status_kind(a)
            state = {"graded": "Graded", "submitted": "Submitted", "not_done": "Not done", "offline": "Offline", "excused": "Excused", "disabled": "Disabled"}[kind]
            if not model.eligible(a):
                state += " –"
            elif a["id"] in ceiling.dropped:
                state += " ↓"
            if a["id"] in overrides:
                state += " *"
            color = GREEN if kind == "graded" else YELLOW if kind == "submitted" else RED if kind == "not_done" and (model.overdue(a) or model.submission(a).get("missing")) else MUTED
            weight = f"{g.get('group_weight', 0):g}%" if c.get("_weights_mode") == "assignments" else "group" if c.get("apply_assignment_group_weights") else "points"
            name = Text(a["name"])
            if a.get("_local"):
                name.truncate(max(1, name_width - 9), overflow="ellipsis")
                name.append(" [custom]", style=PINK)
            items_table.add_row(name, colored(state, color), mark, colored(weight, PINK), key=str(a["id"]))
        if all_items:
            row = next((i for i, (_, a) in enumerate(all_items) if str(a["id"]) == selected), 0)
            items_table.move_cursor(row=row)
        for grade, cutoff in model.GRADE_BANDS[:-1]:
            need = model.required(c, cutoff, strict=self.strict, overrides=overrides)
            # Round upward: displayed required mark must actually meet the target.
            text = "Unknown" if scenario.percent is None else "Out of reach" if need is None else "Secured*" if need == 0 else f"{math.ceil(need * 100 - 1e-7)/100:.2f}%"
            targets.add_row(grade, f"{cutoff:g}%", colored(text, RED if need is None else GREEN if need == 0 else PINK))
        warnings = list(dict.fromkeys([*self.snapshot.get("warnings", []), *ceiling.warnings, *scenario.warnings]))
        if c.get('_structure_label'):
            warnings.insert(0, c['_structure_label'] + ': local group, points and drop-rule corrections are applied. Canvas itself is unchanged.')
        notes = "\n\n".join(warnings) if warnings else "Visible weights and assessment points are available."
        if overrides:
            notes = f"{len(overrides)} local what-if override(s). Targets use the scenario.\n\n" + notes
        notes += "\n\n*Secured assumes the displayed assessment model; exam hurdles and grade caps are not supplied by Canvas."
        self.query_one("#warnings", Static).update(notes)
        self.show_assignment_detail()

    @on(DataTable.RowHighlighted, "#assignments")
    def assignment_highlighted(self):
        self.show_assignment_detail()

    def selected_assignment(self):
        c = self.course()
        table = self.query_one("#assignments", DataTable)
        if not c or not table.row_count:
            return None
        try:
            key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            return next((a for _, a in model.assignments(c) if str(a["id"]) == key), None)
        except (KeyError, IndexError):
            return None

    def show_assignment_detail(self):
        a = self.selected_assignment()
        text = ""
        if a:
            s = model.submission(a)
            handed = s.get("submitted_at")
            if handed:
                try:
                    handed = datetime.fromisoformat(handed.replace("Z", "+00:00")).astimezone(TZ).strftime("%d %b %Y %H:%M %Z")
                except ValueError:
                    handed = "Timestamp unavailable"
            c = self.course()
            g = next(g for g, item in model.assignments(c) if item["id"] == a["id"])
            d = model.due(a)
            due = d.astimezone(TZ).strftime("%d %b %H:%M %Z") if d else "not supplied"
            weight = f" · group weight {g.get('group_weight', 0):g}%" if c.get("apply_assignment_group_weights") and c.get("_weights_mode") != "assignments" else ""
            state = model.status(a)
            if not model.eligible(a):
                state += " · excluded from grade"
            elif a["id"] in model.project(c).dropped:
                state += " · dropped at ceiling"
            override = self.overrides.get(c["id"], {}).get(a["id"])
            scenario = f" · what-if {override:g}%" if override is not None else ""
            if a.get("_local"):
                toggle = "enable" if a.get("_disabled") else "disable"
                text = f"{a['name']} [custom] · {state}{scenario}\n{g['name']}{weight} · Entered locally; not an official Canvas assessment\ne edit · d {toggle} · Delete remove · a assessment weights"
            else:
                text = f"{a['name']} · {state}{scenario}\n{g['name']}{weight} · Due: {due}\nSubmitted: {handed or 'No online submission recorded'} · Attempt: {s.get('attempt') or '—'} · a: edit assessment weights"
            if a.get("locked_for_user"):
                text += " · Canvas currently locks this item"
            if s.get("grade_matches_current_submission") is False:
                text += " · Latest attempt awaits a new grade"
            if a.get('_structure_adjusted'):
                text += "\nLocal correction: " + ', '.join(a['_structure_adjusted'])
        self.query_one("#assignment-detail", Static).update(text)

    def action_refresh(self):
        if self.demo_mode:
            self.render_snapshot()
        elif self.config.get("auth_mode") == "browser":
            self.open_browser_canvas()
        elif not self.client:
            self.action_cookies() if self.config.get('auth_mode') == 'cookie' else self.action_browser()
        elif not self.loading:
            self.load()

    def action_courses(self):
        if self.demo_mode:
            self.notify("Course selection is available when connected to Canvas.")
        elif self.config.get("auth_mode") == "browser":
            self.open_browser_canvas()
            self.notify("Choose courses in the Canvas sync bookmark.")
        elif not self.client:
            self.action_cookies() if self.config.get('auth_mode') == 'cookie' else self.action_browser()
        elif not self.loading:
            self.load(choose=True)

    def action_token(self):
        if not self.loading:
            self.push_screen(Setup(self.canvas_url()), self.connected)

    def action_cookies(self):
        if self.demo_mode:
            self.notify('Cookie login is available outside demo mode.')
        elif not self.loading:
            self.push_screen(CookieSetup(self.canvas_url()), self.cookies_connected)

    def cookies_connected(self, credentials):
        if not credentials:
            self.set_message('Cookie login cancelled. Press k to enter Canvas cookies.')
            return
        base, cookies, remember = credentials
        self.client = api.CookieClient(base, cookies)
        updated = {**self.config, 'base_url': base, 'auth_mode': 'cookie'}
        if self.config.get('base_url', base) != base:
            updated.pop('course_ids', None)
        try:
            store.write('config.json', updated)
            if remember:
                store.write('session.json', {'base_url': base, 'cookie': self.client.cookie_header})
            elif (store.DATA/'session.json').exists():
                store.write('session.json', {})
        except OSError:
            self.notify('Could not save settings. This session can still connect.', severity='warning')
        self.config = updated
        self.load()

    def action_browser(self):
        if self.loading:
            return
        if self.demo_mode:
            self.notify("Browser sync is available outside demo mode.")
        elif self.config.get("auth_mode") == "browser":
            self.browser_connected(self.canvas_url())
        else:
            self.push_screen(BrowserConnect(self.canvas_url()), self.browser_connected)

    def browser_connected(self, base):
        if isinstance(base, tuple):
            mode, address = base
            if mode == "token":
                self.push_screen(Setup(address), self.connected)
            else:
                self.push_screen(CookieSetup(address), self.cookies_connected)
            return
        if base == "token":
            self.action_token()
            return
        if base == 'cookie':
            self.action_cookies()
            return
        if not base:
            self.set_message("Connection cancelled. Press b for browser login or t for a token.")
            return
        try:
            updated = {**self.config, "base_url": base, "auth_mode": "browser"}
            store.write("config.json", updated)
            self.config = updated
            self.client = None
            opened = browser_sync.open_setup(base)
            self.set_message("Browser setup opened. Add the sync bookmark, sign in to Canvas and sync. Waiting for the download…" if opened else f"Could not open the default browser. Open {store.DATA / 'browser-setup.html'} manually.")
            self.start_browser_watch()
        except (OSError, api.CanvasError) as e:
            self.set_message(str(e))

    def open_browser_canvas(self):
        try:
            if browser_sync.open_canvas(self.canvas_url()):
                self.set_message("Canvas opened in your default browser. Sign in if needed, then click Canvas Grades Sync. Waiting for download…")
            else:
                self.notify("Could not open your default browser. Press b for setup.", severity="error")
        except (OSError, api.CanvasError) as e:
            self.notify(str(e), severity="error")

    def start_browser_watch(self):
        if self.browser_timer is None:
            self.browser_timer = self.set_interval(2, self.poll_browser_downloads)

    def poll_browser_downloads(self):
        if self.demo_mode or self.offline or self.config.get("auth_mode") != "browser" or len(self.screen_stack) > 1:
            return
        for path in browser_sync.candidates()[:10]:
            try:
                stat = path.stat()
                key = (str(path), stat.st_mtime_ns, stat.st_size)
                if key in self.seen_downloads:
                    continue
                self.seen_downloads.add(key)
                snapshot = browser_sync.read_export(path, self.config.get("base_url"))
                if self.snapshot and datetime.fromisoformat(snapshot["fetched_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(self.snapshot["fetched_at"].replace("Z", "+00:00")):
                    continue
                self.accept_browser_snapshot(snapshot)
                return
            except (OSError, ValueError, api.CanvasError):
                continue

    def accept_browser_snapshot(self, snapshot):
        updated = {**self.config, "auth_mode": "browser", "base_url": snapshot["base_url"], "course_ids": [c["id"] for c in snapshot["courses"]]}
        store.write("snapshot.json", snapshot)
        store.write("config.json", updated)
        self.config, self.snapshot, self.client = updated, snapshot, None
        self.offline = False
        self.render_snapshot()
        self.notify("Browser grades imported.")

    def action_import(self):
        if not self.demo_mode:
            self.push_screen(ImportSnapshot(), self.import_browser_file)

    def import_browser_file(self, path):
        if path is None:
            return
        try:
            snapshot = browser_sync.read_export(path, self.config.get("base_url"))
            self.accept_browser_snapshot(snapshot)
            self.start_browser_watch()
        except (OSError, ValueError, api.CanvasError) as e:
            self.notify(str(e), severity="error", timeout=8)

    def action_strict(self):
        self.strict = not self.strict
        self.render_snapshot()

    def action_reset(self):
        self.overrides.clear()
        self.strict = False
        self.render_snapshot()

    def action_whatif(self):
        a = self.selected_assignment()
        c = self.course()
        if a and model.eligible(a):
            self.push_screen(WhatIf(a, self.overrides.get(c["id"], {}).get(a["id"])), self.apply_whatif)
        else:
            self.notify("Select an assessment that counts toward the grade.")

    def apply_whatif(self, result):
        if result is None:
            return
        id, value = result
        overrides = self.overrides.setdefault(self.current_id, {})
        if value is None:
            overrides.pop(id, None)
        else:
            overrides[id] = value
        self.render_snapshot()

    def action_help(self):
        self.push_screen(Help())

    def action_weights(self):
        c = self.raw_course()
        if c and not c.get("error"):
            c = self.with_locals(c)
            settings = self.config.get("weights", {}).get(self.weights_key(c))
            self.push_screen(WeightChoice(c, settings), self.weight_mode_chosen)
        else:
            self.notify("Select a loaded course first.")

    def action_assessment_weights(self):
        c, a = self.raw_course(), self.selected_assignment()
        if not c or not a or c.get("error"):
            self.notify("Select an assessment first.")
            return
        c = self.with_locals(c)
        settings = self.config.get("weights", {}).get(self.weights_key(c))
        source = self.with_weights(c) if settings and settings.get("mode") == "groups" else c
        self.push_screen(WeightEditor(source, "assignments", settings, focus_id=a["id"]), self.weight_values_chosen)

    def weight_mode_chosen(self, mode):
        if mode is None:
            return
        if mode == "canvas":
            self.save_weights(None)
        else:
            c = self.with_locals(self.raw_course())
            settings = self.config.get("weights", {}).get(self.weights_key(c))
            self.push_screen(WeightEditor(c, mode, settings), self.weight_values_chosen)

    def weight_values_chosen(self, settings):
        if settings is not None:
            self.save_weights(settings)

    def action_new_assessment(self):
        c = self.raw_course()
        if not c or c.get("error") or not c.get("groups"):
            self.notify("Select a loaded course with an assignment group first.")
            return
        self.push_screen(LocalAssessmentEditor(self.with_locals(c)), self.local_assessment_edited)

    def selected_local_record(self):
        a, c = self.selected_assignment(), self.raw_course()
        if not a or not c or not a.get("_local"):
            self.notify("Select a [custom] assessment first.")
            return None
        return next((r for r in self.config.get("local_assessments", {}).get(self.weights_key(c), []) if r['id'] == a['id']), None)

    def action_edit_assessment(self):
        record = self.selected_local_record()
        if record:
            if not self.raw_course().get('groups'):
                self.notify('No current Canvas group is available. You can disable or delete this custom entry.')
                return
            self.push_screen(LocalAssessmentEditor(self.with_locals(self.raw_course()), record), self.local_assessment_edited)

    def local_assessment_edited(self, record):
        if record is None:
            return
        key = self.weights_key(self.raw_course())
        records = [r for r in self.config.get('local_assessments', {}).get(key, []) if r['id'] != record['id']]
        records.append(record)
        self.save_local_records(records, record['id'])

    def save_local_records(self, records, selected_id=None, deleted_id=None):
        key = self.weights_key(self.raw_course())
        updated = {**self.config, 'local_assessments': {**self.config.get('local_assessments', {}), key: records}}
        if deleted_id is not None:
            weights = self.config.get('weights', {}).get(key)
            if weights and weights.get('mode') == 'assignments':
                values = {k:v for k,v in weights['values'].items() if k != str(deleted_id)}
                updated['weights'] = {**self.config.get('weights', {}), key: {**weights, 'values': values}}
        if not self.demo_mode:
            try:
                store.write('config.json', updated)
            except OSError:
                self.notify('Could not save the custom assessment; nothing changed.', severity='error')
                return
        self.config = updated
        if deleted_id is not None:
            self.overrides.get(self.current_id, {}).pop(deleted_id, None)
        self.render_snapshot()
        if selected_id is not None:
            rows = list(model.assignments(self.course()))
            row = next((i for i, (_, a) in enumerate(rows) if a['id'] == selected_id), 0)
            self.query_one('#assignments', DataTable).move_cursor(row=row)
        self.notify('Custom assessments updated' + (' for this demo session.' if self.demo_mode else ' and saved locally.'))

    def action_toggle_assessment(self):
        record = self.selected_local_record()
        if record:
            self.local_assessment_edited({**record, 'enabled': not record.get('enabled', True)})

    def action_delete_assessment(self):
        record = self.selected_local_record()
        if record:
            key = self.weights_key(self.raw_course())
            records = [r for r in self.config.get('local_assessments', {}).get(key, []) if r['id'] != record['id']]
            self.save_local_records(records, deleted_id=record['id'])

    def save_weights(self, settings):
        c = self.raw_course()
        updated = {**self.config, "weights": dict(self.config.get("weights", {}))}
        key = self.weights_key(c)
        if settings is None:
            updated["weights"].pop(key, None)
        else:
            updated["weights"][key] = settings
        if not self.demo_mode:
            try:
                store.write("config.json", updated)
            except OSError:
                self.notify("Could not save weightings. Settings were not changed.", severity="error")
                return
        self.config = updated
        self.render_snapshot()
        self.notify("Weightings updated" + (" for this demo session." if self.demo_mode else " and saved locally."))


class Help(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self):
        with Vertical(id="help-dialog"):
            yield Static("How the numbers work", classes="dialog-title")
            with VerticalScroll():
                yield Static(
                    "Canvas current is Canvas’s own graded-work average. It may be inflated by leaving unmarked assessments out.\n\n"
                    "Ceiling holds visible posted scores fixed (including zeros), gives unmarked work 100%, and applies Canvas group weights and drop rules. "
                    "Excused and excluded assessments do not count. Missing ungraded work remains recoverable in this optimistic ceiling.\n\n"
                    "The scenario lets you change individual results with w, including posted marks. Press m to treat overdue, unsubmitted online assessments as zero. "
                    "The ceiling remains unchanged; the Scenario column and target table use your assumptions. Press x to reset all scenarios.\n\n"
                    "Press g to save custom course weights: edit the existing assignment groups, or assign each assessment a percentage of the course. "
                    "Group mode keeps best-N rules; assessment mode replaces group and drop rules. Weights must total 100%. "
                    "Custom weights affect the ceiling and scenario, persist after refresh/restart, and can be restored to Canvas defaults.\n\n"
                    "Press n to add a custom assessment to any existing group, including an empty group. Enter maximum points and, if known, its mark. "
                    "Local entries are tagged [custom]. Select one and press e to edit, d to disable/enable, or Delete to remove it. "
                    "Disabled entries remain visible but are excluded from calculations. All custom entries survive Canvas refreshes and restarts. "
                    "If the only assessment in a weighted group is disabled or removed, that group becomes unknown again.\n\n"
                    "Targets give the same percentage to every remaining unmarked assessment and solve for the smallest percentage meeting the cutoff, "
                    "recalculating drop rules each time. Overrides are held fixed. They are a planning estimate, not a prediction.\n\n"
                    "Graded means a visible mark is available, including zero. Submitted means an attempt is recorded but its latest grade is pending. "
                    "Not done means no grade or online submission is recorded. Offline items have unknown completion status until Canvas records a mark or submission. "
                    "The table keeps status, marks and weights visible together; select a row for its full name, due date and submission details. "
                    "Weight shows a custom assessment percentage, or group/points for Canvas weighting. Press a to edit individual assessment weights. "
                    "A down arrow marks a ceiling drop, a dash marks exclusion, and an asterisk marks a what-if override.\n\n"
                    "No calculation can see unpublished assessments, withheld marks, external grades, exam pass requirements, late-penalty caps or final scaling. "
                    "A group with no visible points, weights not totalling 100%, or multiple grading periods produces a warning. "
                    "Review those warnings before relying on a ceiling.\n\n"
                    "r refresh · c choose semester courses · g weights · Tab move panels · arrows select rows · w what-if · m overdue policy · x reset · t replace token · q quit\n\n"
                    "Dates use your system timezone. No grade or submission changes are sent to Canvas. "
                    "Press b for default-browser login and sync bookmark setup. Press r to open Canvas, then use the sync bookmark. "
                    "Downloads are imported automatically; i imports a snapshot from another folder. Browser passwords and cookies stay in your browser. "
                    "Alternatively press k to supply your own Canvas Cookie request header locally for direct refreshes. "
                    "In cookie mode r fetches directly; cookies are held in memory unless you choose to remember them. Expired sessions need new cookies. "
                    "Local settings, snapshots and optional credentials are stored in the app data directory with private permissions. "
                    "What-if assumptions last only for this session.\n\n"
                    "Canvas Grades · Copyright (C) 2026 Canvas Grades contributors. "
                    "GPLv3 or later; no warranty. See LICENSE.", markup=False)
            yield Button("Close", id="close-help", variant="primary")

    @on(Button.Pressed, "#close-help")
    def close_help(self):
        self.dismiss()


class WeightChoice(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, course, settings):
        super().__init__()
        self.course_data, self.settings = course, settings

    def compose(self):
        with Vertical(id="dialog"):
            yield Static("Course weightings", classes="dialog-title")
            yield Static(model.title(self.course_data), markup=False)
            active = (self.settings or {}).get("mode", self.course_data.get('_structure_label', "Canvas defaults"))
            yield Static(f"Using: {active}\n\nGroup weights keep Canvas’s within-group points and best-N rules.\nAssessment weights give each assessment its own course percentage, replacing group and drop rules.\n\nOverrides are saved locally for this course and reused after refresh.", classes="explanation", markup=False)
            yield Button("Edit group weights", id="weight-groups", variant="primary")
            yield Button("Edit assessment weights", id="weight-assignments")
            yield Button("Restore course defaults" if self.course_data.get('_structure_label') else "Restore Canvas weights", id="weight-canvas")
            yield Button("Cancel", id="weight-cancel")

    @on(Button.Pressed)
    def choose(self, event):
        modes = {"weight-groups": "groups", "weight-assignments": "assignments", "weight-canvas": "canvas"}
        self.dismiss(modes.get(event.button.id))


class WeightEditor(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, course, mode, settings=None, focus_id=None):
        super().__init__()
        self.course_data, self.mode = course, mode
        self.focus_id = focus_id
        groups = course.get("groups", [])
        if mode == "groups":
            self.rows = [(str(g["id"]), g["name"], float(g.get("group_weight") or 0)) for g in groups]
        else:
            rows = []
            for g in groups:
                items = [a for a in g.get("assignments", []) if model.eligible(a) and (a.get("points_possible") or 0) > 0]
                total = sum(a["points_possible"] for a in items)
                for a in items:
                    weight = float(g.get("group_weight") or 0) * a["points_possible"] / total if total else 0
                    rows.append((str(a["id"]), a["name"], weight, a["points_possible"]))
            if not course.get("apply_assignment_group_weights") or not sum(r[2] for r in rows):
                total = sum(r[3] for r in rows)
                rows = [(id, name, points / total * 100 if total else 0, points) for id, name, _, points in rows]
            self.rows = [(id, name, weight) for id, name, weight, _ in rows]
        if settings and settings.get("mode") == mode:
            self.rows = [(id, name, float(settings["values"].get(id, default))) for id, name, default in self.rows]

    def compose(self):
        with Vertical(id="weights-dialog"):
            yield Static(f"Edit {'group' if self.mode == 'groups' else 'assessment'} weights", classes="dialog-title")
            yield Static(model.title(self.course_data), markup=False)
            yield Static("Enter each share of the final course grade as a percentage. Use 0 to exclude an item. Total must be 100%.\n" +
                         ("Within-group points and drop rules are preserved." if self.mode == "groups" else "Group and drop rules are replaced. Zero-point items cannot have an individual weight."),
                         classes="explanation")
            with VerticalScroll(id="weight-fields"):
                for id, name, value in self.rows:
                    with Horizontal(classes="weight-row"):
                        yield Label(name, markup=False)
                        yield Input(value=f"{value:.4f}".rstrip("0").rstrip("."), id=f"weight-{id}", type="number")
                        yield Label("%", classes="percent-label")
            yield Static("", id="weight-total")
            yield Static("", id="weight-error")
            with Horizontal(classes="buttons"):
                yield Button("Save weights", id="weight-save", variant="primary")
                yield Button("Cancel", id="weight-edit-cancel")

    def on_mount(self):
        self.update_total()
        if self.focus_id is not None:
            try:
                self.query_one(f"#weight-{self.focus_id}", Input).focus()
            except NoMatches:
                pass

    def values(self):
        values = {}
        for id, _, _ in self.rows:
            raw = self.query_one(f"#weight-{id}", Input).value.strip()
            value = float(raw) if raw else 0
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError
            values[id] = value
        return values

    @on(Input.Changed)
    def changed(self):
        if self.is_mounted:
            self.update_total()

    def update_total(self):
        try:
            total = sum(self.values().values())
            text = f"Total: {total:g}%" + ("  ✓" if abs(total - 100) < .005 else f"  ·  {100-total:+g}% to allocate")
        except (ValueError, NoMatches):
            # Initial input-mount events can precede later fields.
            text = "Enter valid percentages from 0 to 100."
        self.query_one("#weight-total", Static).update(text)

    @on(Button.Pressed, "#weight-save")
    def save(self):
        try:
            values = self.values()
            if abs(sum(values.values()) - 100) >= .005:
                self.query_one("#weight-error", Static).update("Weights must total 100% before saving.")
                return
        except ValueError:
            self.query_one("#weight-error", Static).update("Each weight must be a number from 0 to 100.")
            return
        self.dismiss({"mode": self.mode, "values": values})

    @on(Button.Pressed, "#weight-edit-cancel")
    def cancel(self):
        self.dismiss(None)


class LocalAssessmentEditor(ModalScreen):
    BINDINGS = [('escape', 'dismiss', 'Cancel')]

    def __init__(self, course, record=None):
        super().__init__()
        self.course_data, self.record = course, record
        self.groups = [g for g in course.get('groups', []) if not g.get('_local_missing_group')]

    def compose(self):
        record = self.record or {}
        preferred = next((g['id'] for g in self.groups if not g.get('assignments')), self.groups[0]['id'])
        gid = record.get('group_id', preferred)
        if gid not in {g['id'] for g in self.groups}:
            gid = preferred
        with Vertical(id='local-dialog'):
            yield Static('Edit custom assessment' if self.record else 'Add custom assessment', classes='dialog-title')
            yield Static('Add a local assessment to an existing group, including an empty one. It inherits that group’s weighting. Marks and completion are entered by you; nothing is sent to Canvas.', classes='explanation')
            with VerticalScroll(id='local-fields'):
                yield Label('Assignment group')
                yield Select([(f"{g['name']} ({g.get('group_weight', 0):g}%)" + (' · empty' if not g.get('assignments') else ''), g['id']) for g in self.groups], value=gid, allow_blank=False, id='local-group')
                yield Label('Assessment name')
                yield Input(value=record.get('name', ''), placeholder='e.g. Benchmark test', id='local-name')
                with Horizontal(id='local-points-row'):
                    with Vertical():
                        yield Label('Maximum points')
                        yield Input(value=f"{record.get('points_possible', 100):g}", type='number', id='local-points')
                    with Vertical():
                        yield Label('Mark received (blank if ungraded)')
                        yield Input(value='' if record.get('score') is None else f"{record['score']:g}", type='number', id='local-score')
                yield Label('Completion when no mark is entered')
                yield Select([('Not done yet', 'not_done'), ('Submitted / completed; awaiting grade', 'submitted'), ('Offline; completion unknown', 'offline')], value=record.get('status', 'not_done'), allow_blank=False, id='local-status')
                yield Checkbox('Enabled in grade calculations', value=record.get('enabled', True), id='local-enabled')
            yield Static('', id='local-error')
            with Horizontal(classes='buttons'):
                yield Button('Save assessment', id='local-save', variant='primary')
                yield Button('Cancel', id='local-cancel')

    def on_mount(self):
        self.query_one('#local-name', Input).focus()

    @on(Button.Pressed, '#local-save')
    def save(self):
        name = self.query_one('#local-name', Input).value.strip()
        try:
            if not name or len(name) > 200:
                raise ValueError('Enter an assessment name (up to 200 characters).')
            try:
                points = float(self.query_one('#local-points', Input).value)
                raw = self.query_one('#local-score', Input).value.strip()
                score = float(raw) if raw else None
            except ValueError:
                raise ValueError('Enter valid numeric points and a mark, or leave the mark blank.') from None
            if not math.isfinite(points) or points <= 0:
                raise ValueError('Maximum points must be greater than zero.')
            if score is not None and (not math.isfinite(score) or score < 0):
                raise ValueError('The mark must be zero or greater. Leave it blank if ungraded.')
            gid = self.query_one('#local-group', Select).value
            group = next(g for g in self.groups if g['id'] == gid)
            record = {'id': self.record['id'] if self.record else 'local-' + uuid4().hex,
                      'group_id': gid, 'group_name': group['name'], 'name': name,
                      'points_possible': points, 'score': score,
                      'status': self.query_one('#local-status', Select).value,
                      'enabled': self.query_one('#local-enabled', Checkbox).value}
        except ValueError as e:
            self.query_one('#local-error', Static).update(str(e))
            return
        self.dismiss(record)

    @on(Button.Pressed, '#local-cancel')
    def cancel(self):
        self.dismiss(None)
