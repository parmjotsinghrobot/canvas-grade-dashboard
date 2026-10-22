# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from canvas_grades import api, store


class Response:
    def __init__(self, value, link=""):
        self.data = json.dumps(value).encode()
        self.headers = {"Link": link}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.data


class API(unittest.TestCase):
    def test_pagination_get_and_authorization(self):
        client = api.Client("https://canvas.example.edu", "test-secret")
        responses = [Response([1], '<https://canvas.example.edu/api/v1/courses?page=2>; rel="next"'), Response([2])]
        requests = []
        def open(req, timeout):
            requests.append(req)
            return responses.pop(0)
        with patch.object(client.opener, "open", side_effect=open):
            self.assertEqual(client.pages("courses"), [1, 2])
        for req in requests:
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.headers["Authorization"], "Bearer test-secret")
            self.assertNotIn("test-secret", req.full_url)

    def test_no_cross_origin_or_non_api_pagination(self):
        for bad in ["https://evil.example/api/v1/courses", "http://canvas.example.edu/api/v1/courses",
                    "https://canvas.example.edu/login", "https://user@canvas.example.edu/api/v1/courses"]:
            client = api.Client("https://canvas.example.edu", "secret")
            with patch.object(client.opener, "open", return_value=Response([], f'<{bad}>; rel="next"')) as mocked:
                with self.assertRaises(api.CanvasError):
                    client.pages("courses")
                self.assertEqual(mocked.call_count, 1)

    def test_redirect_is_not_followed(self):
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_safe_error(self):
        client = api.Client("https://canvas.example.edu", "secret")
        error = HTTPError("https://canvas.example.edu/api/v1/courses", 401, "secret must not leak", {}, None)
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaisesRegex(api.CanvasError, "Token expired") as caught:
                client.pages("courses")
            self.assertNotIn("secret", str(caught.exception))

    def test_nicknames_and_original_names(self):
        client = api.Client("https://canvas.example.edu", "secret")
        def pages(path, params=None):
            if path == "courses":
                return [{"id": 1, "name": "Signals crew", "course_code": "ELECTENG331"}]
            return [{"course_id": 1, "name": "ELECTENG 331 Signals", "nickname": "Signals crew"}]
        with patch.object(client, "pages", side_effect=pages):
            courses, warnings = asyncio.run(client.courses())
        self.assertEqual(courses[0]["original_name"], "ELECTENG 331 Signals")
        self.assertEqual(courses[0]["nickname"], "Signals crew")
        self.assertFalse(warnings)

    def test_private_files_and_cache_never_contains_token(self):
        client = api.Client("https://canvas.example.edu", "test-secret")
        with tempfile.TemporaryDirectory() as directory, patch.object(store, "DATA", Path(directory)):
            store.write("credentials.json", {"token": "test-secret"})
            self.assertEqual((Path(directory)/"credentials.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(directory).stat().st_mode & 0o777, 0o700)
            def pages(path, params=None):
                if path.endswith("assignment_groups"):
                    return [{"id": 2, "name": "Work", "group_weight": 100}]
                return [{"id": 3, "assignment_group_id": 2, "points_possible": 10, "submission": {"score": 9}}]
            with patch.object(client, "pages", side_effect=pages):
                result = asyncio.run(client.snapshot([{"id": 1, "name": "Course"}]))
            raw = (Path(directory)/"snapshot.json").read_text()
            self.assertNotIn("test-secret", raw)
            self.assertEqual(result["courses"][0]["groups"][0]["assignments"][0]["submission"]["score"], 9)
            saved = raw
            with patch.object(client, "pages", side_effect=api.CanvasError("Failed")):
                result = asyncio.run(client.snapshot([{"id": 1, "name": "Course"}]))
            self.assertTrue(result["courses"][0]["error"])
            self.assertEqual((Path(directory)/"snapshot.json").read_text(), saved)
