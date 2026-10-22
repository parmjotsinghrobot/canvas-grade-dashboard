# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from textual.widgets import Checkbox, DataTable, Input, Static
from canvas_grades import api, demo, store
from canvas_grades.app import CookieSetup, GradesApp


class Response:
    def __init__(self, raw, link=''):
        self.raw = raw.encode()
        self.headers = {'Link':link}
    def read(self): return self.raw
    def __enter__(self): return self
    def __exit__(self,*args): pass


class Cookies(unittest.TestCase):
    def test_cookie_auth_pagination_and_prefixed_json(self):
        client=api.CookieClient('https://canvas.example.edu','Cookie: _normandy_session=fake-session; _csrf_token=fake-csrf')
        responses=[Response('while(1);[{"id":1}]','<https://canvas.example.edu/api/v1/courses?page=2>; rel="next"'),
                   Response('for(;;);[{"id":2}]')]
        requests=[]
        def open(req,timeout):
            requests.append(req)
            return responses.pop(0)
        with patch.object(client.opener,'open',side_effect=open):
            self.assertEqual(client.pages('courses'),[{'id':1},{'id':2}])
        for req in requests:
            self.assertEqual(req.method,'GET')
            self.assertIn('_normandy_session=fake-session',req.headers['Cookie'])
            self.assertNotIn('Authorization',req.headers)
            self.assertNotIn('fake-session',req.full_url)
            self.assertEqual(req.headers['X-requested-with'],'XMLHttpRequest')

    def test_session_cannot_follow_other_origins_or_redirects(self):
        client=api.CookieClient('https://canvas.example.edu','session=fake-session')
        with patch.object(client.opener,'open',return_value=Response('[]','<https://other.example/api/v1/courses>; rel="next"')) as opened:
            with self.assertRaisesRegex(api.CanvasError,'pagination'):
                client.pages('courses')
            self.assertEqual(opened.call_count,1)
        for code in (302,401):
            with patch.object(client.opener,'open',side_effect=HTTPError(client.base+'/api/v1/courses',code,'fake-session must not leak',{'Location':'https://other.example/login'},None)):
                with self.assertRaisesRegex(api.CanvasError,'session expired') as caught:
                    client.pages('courses')
                self.assertNotIn('fake-session',str(caught.exception))
        with patch.object(client.opener,'open',return_value=Response('<html>Sign in</html>')):
            with self.assertRaisesRegex(api.CanvasError,'press k'):
                client.pages('courses')

    def test_invalid_headers_reject_without_echoing_secrets(self):
        for header in ('','not-a-header','session=fake-session\r\nAuthorization: injected','session=fake-session\n','session=é',None):
            with self.subTest(header_type=type(header).__name__):
                with self.assertRaises(api.CanvasError) as caught:
                    api.normalize_cookies(header)
                self.assertNotIn('fake-session',str(caught.exception))
        self.assertEqual(api.normalize_cookies('cookie: session=abc%3D; theme=dark'),'session=abc%3D; theme=dark')

    def test_cookie_never_enters_snapshot(self):
        client=api.CookieClient('https://canvas.example.edu','session=fake-session')
        def pages(path,params=None):
            if path.endswith('assignment_groups'):
                return [{'id':2,'name':'Work','group_weight':100}]
            return [{'id':3,'name':'Test','assignment_group_id':2,'points_possible':10,'submission':{'score':8}}]
        with tempfile.TemporaryDirectory() as directory,patch.object(store,'DATA',Path(directory)),patch.object(client,'pages',side_effect=pages):
            asyncio.run(client.snapshot([{'id':1,'name':'Course'}]))
            text=(Path(directory)/'snapshot.json').read_text()
            self.assertNotIn('fake-session',text)
            self.assertEqual((Path(directory)/'snapshot.json').stat().st_mode & 0o777,0o600)


async def fake_courses(client):
    return demo.snapshot()['courses'],[]


async def fake_snapshot(client,courses,warnings=None):
    value={**demo.snapshot(),'courses':courses}
    store.write('snapshot.json',value)
    return value


class CookieApp(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_cookie_login_direct_refresh_and_session_only(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(store,'DATA',Path(directory)),patch.dict('os.environ',{'CANVAS_TOKEN':'','CANVAS_COOKIE':''}),patch.object(api.Client,'courses',fake_courses),patch.object(api.Client,'snapshot',fake_snapshot),patch('canvas_grades.browser_sync.webbrowser.open') as browser:
            config={'base_url':'https://canvas.example.edu','course_ids':[1],
                    'course_structure':{'unrelated-course':{'enabled':False}},
                    'weights':{'https://canvas.example.edu|1':{'mode':'groups','values':{'1':30,'2':25,'3':5,'4':40}}}}
            store.write('config.json',config)
            app=GradesApp()
            async with app.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                await pilot.click('#cookie-login')
                await pilot.pause()
                self.assertIsInstance(app.screen,CookieSetup)
                self.assertTrue(app.screen.query_one('#cookie-value',Input).password)
                self.assertFalse(app.screen.query_one('#cookie-remember',Checkbox).value)
                app.screen.query_one('#cookie-value',Input).value='session=fake-session'
                await pilot.click('#cookie-connect')
                await pilot.pause()
                self.assertIsInstance(app.client,api.CookieClient)
                self.assertEqual(app.query_one('#courses',DataTable).row_count,1)
                self.assertEqual(app.config['auth_mode'],'cookie')
                self.assertIn('COOKIE SESSION',str(app.query_one('#connection',Static).render()))
                self.assertFalse((Path(directory)/'session.json').exists())
                self.assertEqual(app.config['weights'],config['weights'])
                self.assertEqual(app.config['course_structure'],config['course_structure'])
                await pilot.press('r')
                await pilot.pause()
                browser.assert_not_called()
                self.assertFalse(app.loading)
                self.assertNotIn('fake-session',(Path(directory)/'snapshot.json').read_text())
                self.assertNotIn('fake-session',(Path(directory)/'config.json').read_text())
            restarted=GradesApp()
            async with restarted.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                self.assertIsInstance(restarted.screen,CookieSetup)

    async def test_remembered_session_reconnects_and_is_origin_bound(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(store,'DATA',Path(directory)),patch.dict('os.environ',{'CANVAS_TOKEN':'','CANVAS_COOKIE':''}),patch.object(api.Client,'courses',fake_courses),patch.object(api.Client,'snapshot',fake_snapshot):
            store.write('config.json',{'auth_mode':'cookie','base_url':'https://canvas.example.edu','course_ids':[1]})
            app=GradesApp()
            async with app.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                app.screen.query_one('#cookie-value',Input).value='session=fake-session'
                app.screen.query_one('#cookie-remember',Checkbox).value=True
                await pilot.click('#cookie-connect')
                await pilot.pause()
                self.assertEqual(store.read('session.json')['cookie'],'session=fake-session')
                self.assertEqual((Path(directory)/'session.json').stat().st_mode & 0o777,0o600)
            restarted=GradesApp()
            async with restarted.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                self.assertIsInstance(restarted.client,api.CookieClient)
                self.assertEqual(restarted.query_one('#courses',DataTable).row_count,1)
                await pilot.press('k')
                await pilot.pause()
                restarted.screen.query_one('#cookie-value',Input).value='session=updated-fake-session'
                await pilot.click('#cookie-connect')
                await pilot.pause()
                self.assertEqual(store.read('session.json'),{})
            store.write('session.json',{'base_url':'https://other.example','cookie':'session=wrong-host'})
            different=GradesApp()
            async with different.run_test(size=(120,40)) as pilot:
                await pilot.pause()
                self.assertIsInstance(different.screen,CookieSetup)
                self.assertIsNone(different.client)
