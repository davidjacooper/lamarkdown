from ..util.mock_progress import MockProgress
from lamarkdown.lib import resources

import unittest
from unittest.mock import patch, Mock, PropertyMock

import base64
import email.utils
import os
import tempfile


class ResourcesTestCase(unittest.TestCase):

    def setUp(self):
        self.orig_dir = os.getcwd()

    def tearDown(self):
        os.chdir(self.orig_dir)


    def test_read_url_local_file(self):

        progress = MockProgress(expect_error = False)
        cache = Mock()

        with tempfile.TemporaryDirectory() as dir:
            os.chdir(dir)
            Path('testfile.txt').write_text('test content')

            testdir = Path('testdir')
            testdir.mkdir()
            (testdir / 'testfile2').write_text('test content 2')

            for url,                          expected in [
                ('testfile.txt',              (False, b'test content', 'text/plain')),
                ('file:testfile.txt',         (False, b'test content', 'text/plain')),
                ('testdir/testfile2.md',      (False, b'test content 2', 'text/markdown')),
                ('file:testdir/testfile2.md', (False, b'test content 2', 'text/markdown')),
            ]:
                output = resources.read_url(url, cache, progress)
                self.assertEqual(expected, output)
                cache.assert_not_called()


    def test_read_url_data(self):

        progress = MockProgress(expect_error = False)
        cache = Mock()

        content = b'p { color: green }'
        url = 'data:text/css;base64,' + base64.b64encode(content).decode()
        result = resources.read_url(url, cache, progress)
        self.assertEqual((False, content, 'text/css'), result)
        cache.assert_not_called()


    @patch('urllib.request.urlopen')
    def test_read_url_cached(self, mock_urlopen):

        progress = MockProgress(expect_error = False)
        cache = Mock()

        cached_url = 'http://cached.example.com/file.txt'
        cache.get.side_effect = \
            lambda key: {cached_url: ('cached_content', 'text/mock')}.get(key)

        result = resources.read_url(cached_url, cache, progress)
        mock_urlopen.assert_not_called()
        self.assertEqual((True, 'cached_content', 'text/mock'), result)


    @patch('urllib.request.urlopen')
    @patch('time.time', lambda: 1_000_000_000)
    def test_read_url_remote(self, mock_urlopen):

        progress = MockProgress(expect_error = True)
        cache = Mock()
        type(cache).get = PropertyMock(return_value = lambda k: None)

        # Read a URL that ought to provoke network access (though patched here), with results
        # affected by the server return status and the 'cache-control' and 'date' headers.
        url = 'http://example.com/file.txt'
        content = b'mock_remote_content'
        mime = 'text/plain'
        fd = email.utils.formatdate

        for status, headers,                             exp_result,            exp_cache_time in [
            (200,   {},                                  (True, content, mime), 86400),
            (500,   {},                                  (True, None,    None), None),
            (200,   {'cache-control':
                     'aa,no-cache,bb'},                  (True, content, mime), None),
            (200,   {'cache-control':
                     'aa,no-store,bb'},                  (True, content, mime), None),
            (200,   {'cache-control':
                     'aa,max-age=-1,bb'},                (True, content, mime), None),
            (200,   {'cache-control':
                     'aa,max-age=0,bb'},                 (True, content, mime), None),

            (200,   {'cache-control':
                     'aa,max-age=1,bb'},                 (True, content, mime), 1),
            (200,   {'cache-control':
                     'aa,no-store,max-age=1,bb'},        (True, content, mime), None),

            (200,   {'cache-control': 'aa,max-age=1,bb',
                     'date': fd(1_000_000_000)},         (True, content, mime), 1),

            (200,   {'cache-control': 'aa,max-age=3,bb',
                     'date': fd(1_000_000_000 - 1)},     (True, content, mime), 2),

            (200,   {'cache-control': 'aa,max-age=3,bb',
                     'date': fd(1_000_000_000 - 3)},     (True, content, mime), None),
        ]:
            conn = Mock()
            conn.read.return_value = content
            type(conn).status = PropertyMock(return_value = status)
            type(conn).headers = PropertyMock(return_value = headers)

            mock_urlopen.return_value.__enter__.return_value = conn

            result = resources.read_url(url, cache, progress)
            self.assertEqual(exp_result, result)

            # Caching
            if exp_cache_time is None:
                cache.set.assert_not_called()
            else:
                cache.set.assert_called_with(url, (content, mime), expire = exp_cache_time)
            cache.reset_mock()
