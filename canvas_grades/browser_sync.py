# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""Default-browser sync through an explicit bookmarklet and local JSON download.

No browser profiles, cookies or credentials are read by the TUI.
"""
from datetime import datetime
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote
import webbrowser
from . import api, store

MAX_BYTES = 20 * 1024 * 1024


def downloads_dir() -> Path:
    custom = os.environ.get('CANVAS_GRADES_DOWNLOADS')
    if custom:
        return Path(custom).expanduser()
    dirs = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config')) / 'user-dirs.dirs'
    try:
        for line in dirs.read_text().splitlines():
            if line.startswith('XDG_DOWNLOAD_DIR='):
                value = line.split('=', 1)[1].strip().strip('"').replace('${HOME}', str(Path.home())).replace('$HOME', str(Path.home()))
                if Path(value).is_absolute():
                    return Path(value)
    except OSError:
        pass
    return Path.home()/'Downloads'


def setup_page(base: str) -> Path:
    base = api.base_url(base)
    source = Path(__file__).with_name('browser_export.js').read_text(encoding='utf-8').replace('__BASE_URL__', json.dumps(base))
    bookmark = 'javascript:void ' + quote(source, safe="()!~*'-._")
    markup = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Canvas Grades — browser login</title><style>
body{{font:17px/1.6 system-ui;max-width:800px;margin:60px auto;padding:0 25px;background:#1e1e2e;color:#cdd6f4}}
h1,a{{color:#f5c2e7}}li{{margin:18px 0}}.bookmark,.open{{display:inline-block;padding:12px 20px;border-radius:8px;background:#f5c2e7;color:#1e1e2e;text-decoration:none;font-weight:600}}.note{{color:#a6adc8}}code{{background:#313244;padding:2px 5px}}
</style><h1>Canvas Grades</h1><p>Use your usual browser and Canvas login.</p>
<ol><li>Drag this link onto your browser’s bookmarks toolbar:<br><a class="bookmark" href="{html.escape(bookmark, quote=True)}">Canvas Grades Sync</a><br><small class="note">Install it as a bookmark; clicking it on this setup page will not sync. Show the bookmarks toolbar with Ctrl+Shift+B if needed.</small></li>
<li><a class="open" href="{html.escape(base)}" target="_blank" rel="noopener">Open Canvas and sign in</a></li>
<li>While on Canvas, click <strong>Canvas Grades Sync</strong> in your bookmarks. Choose your semester’s courses and click <strong>Sync selected courses</strong>.</li>
<li>Save the downloaded JSON in <strong>{html.escape(str(downloads_dir()))}</strong>. The TUI imports it automatically. If you save elsewhere, press <code>i</code> in the TUI and enter its path.</li></ol>
<p class="note">Next time, press <code>r</code> in the TUI to open Canvas, then use the sync bookmark. Existing login sessions work normally. The app does not receive passwords, cookies or tokens; it only imports the downloaded grades. The downloaded JSON contains your private marks.</p></html>'''
    store.write_text('browser-setup.html', markup)
    return store.DATA/'browser-setup.html'


def open_setup(base: str) -> bool:
    return webbrowser.open(setup_page(base).resolve().as_uri(), new=2)


def open_canvas(base: str) -> bool:
    return webbrowser.open(api.base_url(base), new=2)


def _id(obj):
    value = obj.get('id')
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('Invalid course, group or assessment ID in snapshot.')
    return value


def validate(value: dict, expected_base: str | None = None) -> dict:
    """Validate untrusted downloaded JSON before saving or calculating anything."""
    def require(ok, message='Invalid Canvas Grades snapshot.'):
        if not ok:
            raise ValueError(message)
    def number(x, *, nullable=False, nonnegative=False):
        require((nullable and x is None) or (not isinstance(x, bool) and isinstance(x, (int,float)) and math.isfinite(x) and (not nonnegative or x>=0)))
    def text(x, nullable=False):
        require((nullable and x is None) or (isinstance(x, str) and len(x) < 100000))
    def timestamp(x, nullable=False):
        if nullable and x is None:
            return
        text(x)
        stamp = datetime.fromisoformat(x.replace('Z', '+00:00'))
        require(stamp.tzinfo is not None, 'Snapshot timestamps must include a timezone.')
    require(isinstance(value, dict) and value.get('format')=='canvas-grades/v1' and value.get('source')=='browser')
    base = api.base_url(value.get('base_url', ''))
    require(not expected_base or base==api.base_url(expected_base), 'This snapshot belongs to a different Canvas address.')
    timestamp(value.get('fetched_at'))
    courses = value.get('courses')
    require(isinstance(courses,list) and 0<len(courses)<=200)
    warnings = value.get('warnings', [])
    require(isinstance(warnings,list) and all(isinstance(w,str) for w in warnings))
    cids = set()
    for c in courses:
        require(isinstance(c,dict)); cid=_id(c)
        require(cid not in cids); cids.add(cid)
        for key in ('name','original_name','course_code','nickname'):
            text(c.get(key), nullable=key!='name')
        for key in ('apply_assignment_group_weights','hide_final_grades'):
            require(isinstance(c.get(key,False),bool))
        require(isinstance(c.get('enrollments',[]),list))
        for e in c.get('enrollments',[]):
            require(isinstance(e,dict))
            for key in ('computed_current_score','computed_final_score'):
                number(e.get(key),nullable=True)
            require(isinstance(e.get('grades',{}),dict))
            for score in e.get('grades',{}).values():
                number(score,nullable=True)
        groups = c.get('groups')
        require(isinstance(groups,list) and len(groups)<=1000)
        gids, aids = set(), set()
        for g in groups:
            require(isinstance(g,dict)); gid=_id(g)
            require(gid not in gids); gids.add(gid)
            text(g.get('name')); number(g.get('group_weight',0),nonnegative=True)
            rules = g.get('rules') or {}
            require(isinstance(rules,dict))
            for key in ('drop_lowest','drop_highest'):
                n = rules.get(key,0)
                require(isinstance(n,int) and not isinstance(n,bool) and 0<=n<=10000)
            never = rules.get('never_drop',[])
            require(isinstance(never,list) and all(isinstance(n,int) for n in never))
            require(isinstance(g.get('assignments'),list) and len(g['assignments'])<=10000)
            for a in g['assignments']:
                require(isinstance(a,dict)); aid=_id(a)
                require(aid not in aids); aids.add(aid)
                text(a.get('name')); number(a.get('points_possible'),nullable=True,nonnegative=True)
                require(isinstance(a.get('submission_types',[]),list) and all(isinstance(t,str) for t in a.get('submission_types',[])))
                timestamp(a.get('due_at'),nullable=True)
                s = a.get('submission') or {}
                require(isinstance(s,dict)); number(s.get('score'),nullable=True)
                timestamp(s.get('submitted_at'),nullable=True); timestamp(s.get('cached_due_date'),nullable=True)
                if s.get('attempt') is not None:
                    require(isinstance(s['attempt'],int) and s['attempt']>=0)
    return value


def read_export(path: Path, expected_base: str | None = None) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Snapshot is too large (maximum 20 MB).')
    try:
        value = json.loads(path.read_text())
        return validate(value, expected_base)
    except (TypeError, KeyError, AttributeError, RecursionError) as e:
        raise ValueError('Invalid Canvas Grades snapshot.') from e


def candidates() -> list[Path]:
    directory = downloads_dir()
    try:
        return sorted(directory.glob('canvas-grades-*.json'), key=lambda p:p.stat().st_mtime_ns, reverse=True)
    except OSError:
        return []
