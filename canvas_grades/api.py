# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""GET-only Canvas clients. Credentials never follow redirects or origins."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import json
import re
import time
from http.cookies import CookieError, SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
from . import store


class CanvasError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise CanvasError("Use an HTTPS Canvas address, e.g. https://canvas.example.edu (no path).")
    return value.strip().rstrip("/")


class Client:
    auth_mode = 'token'
    def __init__(self, base: str, token: str):
        self.base = base_url(base)
        self.origin = urlsplit(self.base).netloc.lower()
        self.token = token.strip()
        if not self.token or any(c.isspace() for c in self.token):
            raise CanvasError("Enter a valid Canvas access token without spaces.")
        self.opener = build_opener(NoRedirect())

    def request_headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def auth_error(self):
        return "Token expired or invalid. Press t to replace it."

    def _get(self, url: str):
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc.lower() != self.origin
                or not parts.path.startswith("/api/v1/") or parts.username or parts.password):
            raise CanvasError("Canvas returned an unexpected pagination address; request stopped.")
        req = Request(url, headers=self.request_headers(), method="GET")
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=25) as response:
                    try:
                        raw = response.read().decode('utf-8-sig')
                        raw = re.sub(r'^\s*(?:while\(1\);|for\(;;\);)\s*', '', raw)
                        return json.loads(raw), response.headers.get("Link", "")
                    except (ValueError, UnicodeError) as e:
                        if self.auth_mode == 'cookie':
                            raise CanvasError("Canvas returned a login page or invalid response. Sign in and press k to replace cookies.") from None
                        raise CanvasError("Canvas returned a non-JSON response. Check the Canvas address.") from e
            except HTTPError as e:
                e.close()
                if e.code in (429, 502, 503, 504) and attempt < 2:
                    try:
                        delay = min(max(float(e.headers.get("Retry-After", 2 ** attempt)), 0), 5)
                    except ValueError:
                        delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                if self.auth_mode == 'cookie' and e.code in (301, 302, 303, 307, 308):
                    raise CanvasError(self.auth_error()) from None
                messages = {401: self.auth_error(),
                            403: "Canvas denied access. Check your session or course access." if self.auth_mode == 'cookie' else "Canvas denied access. Check token permissions or course access.",
                            404: "Canvas resource not found; check the course and Canvas address.",
                            429: "Canvas is rate limiting requests; try again shortly."}
                raise CanvasError(messages.get(e.code, f"Canvas request failed (HTTP {e.code}).")) from None
            except (URLError, TimeoutError, OSError):
                raise CanvasError("Cannot reach Canvas. Check your connection; use --offline for the saved snapshot.") from None

    def get(self, path: str, params: dict | None = None):
        query = urlencode(params or {}, doseq=True)
        url = self.base + "/api/v1/" + path.lstrip("/") + ("?" + query if query else "")
        data, _ = self._get(url)
        return data

    def pages(self, path: str, params: dict | None = None) -> list:
        query = urlencode({"per_page": 100, **(params or {})}, doseq=True)
        url = self.base + "/api/v1/" + path.lstrip("/") + "?" + query
        results, seen = [], set()
        while url:
            if url in seen:
                raise CanvasError("Canvas pagination repeated a page; stopped to avoid incomplete results.")
            seen.add(url)
            data, link = self._get(url)
            if not isinstance(data, list):
                raise CanvasError("Unexpected Canvas response; expected a list.")
            results.extend(data)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = urljoin(url, match[1]) if match else None
        return results

    async def courses(self) -> tuple[list, list]:
        courses = await asyncio.to_thread(self.pages, "courses", {
            "enrollment_type": "student", "include[]": ["term", "total_scores", "current_grading_period_scores"]})
        warnings = []
        try:
            names = await asyncio.to_thread(self.pages, "users/self/course_nicknames")
        except CanvasError:
            names = []
            warnings.append("Course nicknames could not be fetched; showing the names Canvas supplied.")
        nicknames = {str(n["course_id"]): n for n in names}
        for c in courses:
            n = nicknames.get(str(c["id"]), {})
            c["nickname"] = n.get("nickname")
            c["original_name"] = n.get("name") or c.get("original_name") or c.get("name")
        return [c for c in courses if c.get("name")], warnings

    async def snapshot(self, courses: list, warnings: list | None = None) -> dict:
        semaphore = asyncio.Semaphore(3)

        async def fetch(c):
            c = dict(c)
            async with semaphore:
                try:
                    groups = await asyncio.to_thread(self.pages, f"courses/{c['id']}/assignment_groups")
                    items = await asyncio.to_thread(self.pages, f"courses/{c['id']}/assignments", {
                        "include[]": ["submission"], "override_assignment_dates": "true"})
                    by_group = {g["id"]: {**g, "assignments": []} for g in groups}
                    for a in items:
                        gid = a["assignment_group_id"]
                        if gid not in by_group:
                            raise CanvasError("An assignment group is unavailable; cannot calculate a complete ceiling.")
                        by_group[gid]["assignments"].append(a)
                    c["groups"] = list(by_group.values())
                except CanvasError as e:
                    c["error"] = str(e)
            return c

        result = {"fetched_at": datetime.now(timezone.utc).isoformat(), "base_url": self.base,
                  "warnings": warnings or [], "courses": await asyncio.gather(*(fetch(c) for c in courses))}
        # A failed refresh must not replace a complete offline snapshot.
        if not any(c.get("error") for c in result["courses"]):
            store.write("snapshot.json", result)
        return result


class CookieClient(Client):
    auth_mode = 'cookie'

    def __init__(self, base: str, cookie_header: str):
        self.base = base_url(base)
        self.origin = urlsplit(self.base).netloc.lower()
        self.cookie_header = normalize_cookies(cookie_header)
        self.opener = build_opener(NoRedirect())

    def request_headers(self):
        return {'Cookie': self.cookie_header, 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}

    def auth_error(self):
        return 'Canvas session expired or invalid. Sign in to Canvas and press k to replace cookies.'


def normalize_cookies(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 65536 or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise CanvasError('Paste only the Cookie request-header value from your Canvas session, on one line.')
    value = re.sub(r'^Cookie:\s*', '', value.strip(), flags=re.I)
    cookies = SimpleCookie()
    try:
        cookies.load(value)
    except CookieError:
        raise CanvasError('Invalid cookie header. Copy the Cookie request-header value from Canvas.') from None
    if not cookies or not any(m.value for m in cookies.values()):
        raise CanvasError('No cookies found. Copy the Cookie request-header value from Canvas.')
    return '; '.join(f'{m.key}={m.coded_value}' for m in cookies.values())
