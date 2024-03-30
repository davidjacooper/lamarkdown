from ..util.mock_progress import MockProgress
from ..util.mock_cache import MockCache
from lamarkdown.lib import build_params, live, md_compiler, directives

import unittest
from unittest.mock import patch

from hamcrest import (assert_that, contains_exactly, empty, equal_to, has_key, is_not)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import copy
import os
from pathlib import Path
import tempfile
from textwrap import dedent
import threading
import time
import urllib.request



class LiveTestCase(unittest.TestCase):

    def setUp(self):
        self.orig_dir = Path.cwd()

    def tearDown(self):
        os.chdir(self.orig_dir)


    @patch('lamarkdown.lib.resources.read_url')
    def test_watch_live(self, mock_read_url):
        mock_read_url.return_value = (False, b'', None)

        with tempfile.TemporaryDirectory() as dir:
            os.chdir(dir)

            browser_opts = webdriver.firefox.options.Options()
            browser_opts.add_argument('--headless')
            browser = webdriver.Firefox(options = browser_opts)
            update_n = [0]  # Singleton list, just to let wait_for_update() modify the value

            def find_attr(selector, attr):
                return [elem.get_attribute(attr)
                        for elem in browser.find_elements(By.CSS_SELECTOR, selector)]

            def wait_for_update(msg, timeout_secs = 2):
                update_n[0] += 1

                try:
                    WebDriverWait(browser, timeout_secs).until(
                        EC.text_to_be_present_in_element_attribute(
                            (By.CSS_SELECTOR, f'#{live.CONTROL_PANEL_ID}'),
                            'data-update-n',
                            str(update_n[0])))
                except TimeoutException as e:
                    raise AssertionError(
                        f'Timeout - document not refreshed after {timeout_secs} seconds: {msg}'
                    ) from e

            src_file = Path('doc.md')
            src_file.write_text(dedent('''
                # Doc Heading

                Paragraph 1
                {.class1}

                Paragraph 2
                {.class2}
            '''))

            build_file_a = Path('build_a.py')
            build_file_b = Path('build_b.py')
            build_file_a.write_text(dedent('''
                import lamarkdown as la
                la('attr_list')
            '''))

            subdir_a = Path('subdir_a')
            subdir_b = Path('subdir_b')
            subdir_c = Path('subdir_c')
            subdir_d = Path('subdir_d')

            extra_file_a = subdir_a / 'extra_a.txt'
            extra_file_b = subdir_b / 'extra_b.txt'
            extra_file_c = subdir_c / 'extra_c.txt'

            subdir_a.mkdir()
            subdir_b.mkdir()
            extra_file_a.write_text('A')

            build_cache = MockCache()
            fetch_cache = MockCache()
            progress = MockProgress()
            base_build_params = [build_params.BuildParams(
                src_file = src_file,
                target_file = Path('doc.html'),
                build_files = [build_file_a, build_file_b],
                build_dir = 'build',
                build_defaults = True,
                build_cache = build_cache,
                fetch_cache = fetch_cache,
                progress = progress,
                directives = directives.Directives(progress),
                is_live = True,
                allow_exec_cmdline = False,
                live_update_deps = {extra_file_a, extra_file_b, extra_file_c}
            )]
            complete_build_params = md_compiler.compile_all(base_build_params)

            updater = live.LiveUpdater(base_build_params, complete_build_params, progress)

            def run_server():
                updater.run(address = '127.0.0.1',
                            port_range = range(14100, 14101),
                            launch_browser = False)

            (server_thread := threading.Thread(target = run_server)).start()

            # The server needs a bit of time to start up (asynchronously) before we query it.
            time.sleep(0.5)

            try:
                browser.get('http://127.0.0.1:14100')

                assert_that(find_attr('title', 'textContent'), contains_exactly('Doc Heading'))
                assert_that(find_attr('h1', 'textContent'),    contains_exactly('Doc Heading'))
                assert_that(
                    find_attr('p', 'textContent'),
                    contains_exactly('Paragraph 1', 'Paragraph 2')
                )
                assert_that(find_attr(f'#{live.CONTROL_PANEL_ID}', 'data-update-n'), '0')


                # Test dependencies
                # -----------------

                src_file.write_text(dedent('''
                    # Doc Heading B

                    Paragraph 1
                    {.class1}

                    Paragraph 2
                    {.class2}
                '''))

                wait_for_update(f'Modified {src_file}')
                assert_that(find_attr('title', 'textContent'), contains_exactly('Doc Heading B'))
                assert_that(find_attr('h1',    'textContent'), contains_exactly('Doc Heading B'))

                build_file_a.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')
                    la.prune('.class1')
                '''))

                wait_for_update('Modified build_a.py')
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 2'))

                build_file_b.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')
                    la.with_html(lambda html: html + '<p>Paragraph 3</p>')
                '''))

                wait_for_update('Added new build_b.py')
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 2',
                                                                            'Paragraph 3'))

                build_file_a.unlink()
                wait_for_update('Deleted build_a.py')
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 1',
                                                                            'Paragraph 2',
                                                                            'Paragraph 3'))

                build_file_a.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')
                '''))
                wait_for_update('Added new build_a.py')
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 1',
                                                                            'Paragraph 2',
                                                                            'Paragraph 3'))

                build_file_b.unlink()
                wait_for_update('Deleted build_b.py')
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 1',
                                                                            'Paragraph 2'))

                # Modifying/creating extra dependency files

                extra_file_a.write_text('AA')
                wait_for_update(f'Modified {extra_file_a}')

                extra_file_b.write_text('BB')
                wait_for_update(f'Added new {extra_file_b}')

                subdir_c.mkdir()
                extra_file_c.write_text('CC')
                wait_for_update(f'Added new {extra_file_c} (including directory creation)')

                # Moving files and directories

                extra_file_a.rename(f'{extra_file_a}1')
                wait_for_update(f'Renamed {extra_file_a} to {extra_file_a}1')

                extra_file_b.rename(subdir_a / 'extra_b.txt')
                wait_for_update(f'Moved {extra_file_b} to subdir_a/ (monitored)')

                subdir_d.mkdir()
                extra_file_c.rename(subdir_d / 'extra_c.txt')
                wait_for_update(f'Moved {extra_file_c} to subdir_d/ (unmonitored)')

                # Restore one of the files, so we can see what happens when we rename the whole
                # parent directory
                extra_file_a.write_text('AA')
                wait_for_update(f'Restored {extra_file_a}')
                subdir_a.rename('subdir_a1')
                wait_for_update('Renamed subdir_a/ to subdir_a1/')


                # Test variants
                # -------------

                build_file_a.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')

                    def VariantA(): la.prune('.class2')
                    def VariantB(): la.prune('.class1')

                    la.variants(VariantA, VariantB)
                '''))

                wait_for_update('Modified build_a.py to specify VariantA and VariantB')

                urls = find_attr(f'#{live.CONTROL_PANEL_ID} a', 'href')
                assert_that(
                    urls,
                    contains_exactly('http://127.0.0.1:14100/VariantA/index.html',
                                     'http://127.0.0.1:14100/VariantB/index.html')
                )

                browser.get(urls[0])
                assert_that(find_attr(f'#{live.CONTROL_PANEL_ID} a', 'href'), equal_to(urls))
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 1'))

                browser.get(urls[1])
                assert_that(find_attr(f'#{live.CONTROL_PANEL_ID} a', 'href'), equal_to(urls))
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 2'))

                build_file_a.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')

                    def VariantA1(): la.with_html(lambda html: html + '<div id="x">A1</div>')
                    def VariantA2(): la.with_html(lambda html: html + '<div id="x">A2</div>')
                    def VariantB1(): la.with_html(lambda html: html + '<div id="x">B1</div>')
                    def VariantB2(): la.with_html(lambda html: html + '<div id="x">B2</div>')
                    def VariantA(): la.variants(VariantA1, VariantA2)
                    def VariantB(): la.variants(VariantB1, VariantB2)

                    la.variants(VariantA, VariantB)
                '''))

                wait_for_update(
                    'Modified build_a.py to specify variants A and B, '
                    'with sub-variants A1, A2, B1 and B2')

                urls = find_attr(f'#{live.CONTROL_PANEL_ID} a', 'href')
                assert_that(
                    urls,
                    contains_exactly('http://127.0.0.1:14100/VariantA1/index.html',
                                     'http://127.0.0.1:14100/VariantA2/index.html',
                                     'http://127.0.0.1:14100/VariantB1/index.html',
                                     'http://127.0.0.1:14100/VariantB2/index.html')
                )

                for i, name in enumerate(['A1', 'A2', 'B1', 'B2']):
                    browser.get(urls[i])
                    assert_that(find_attr('div#x', 'textContent'), contains_exactly(name))

                build_file_a.write_text(dedent('''
                    import lamarkdown as la
                    la('attr_list')
                '''))

                wait_for_update('Modified build_a.py to revert to no variants')
                assert_that(find_attr(f'#{live.CONTROL_PANEL_ID} a', 'href'), empty())
                assert_that(find_attr('p', 'textContent'), contains_exactly('Paragraph 1',
                                                                            'Paragraph 2'))
                assert_that(find_attr('div#x', 'textContent'), empty())


                # Clean builds
                # ------------

                build_cache['mock_key'] = 'mock_value'
                fetch_cache['mock_key'] = 'mock_value'
                browser.find_element(By.CSS_SELECTOR,
                                     f'#{live.CONTROL_PANEL_CLEAN_BUTTON_ID}').click()
                wait_for_update('Clean build')
                assert_that(build_cache, is_not(has_key('mock_key')))
                assert_that(fetch_cache, has_key('mock_key'))

            finally:
                browser.quit()
                updater.shutdown()
                server_thread.join()


    @patch('lamarkdown.lib.resources.read_url')
    @patch('lamarkdown.lib.md_compiler.compile_all')
    def test_404(self, mock_compile, mock_read_url):
        mock_read_url.return_value = (False, b'', None)

        with tempfile.TemporaryDirectory() as dir:
            os.chdir(dir)

            src_file = Path('doc.md')
            src_file.write_text('Mock markdown')

            target_file = Path('doc.html')
            target_file.write_text('<div>Mock HTML</div>')

            progress = MockProgress()
            base_build_params = [build_params.BuildParams(
                src_file = src_file,
                target_file = target_file,
                build_files = [],
                build_dir = Path('build'),
                build_defaults = True,
                build_cache = MockCache(),
                fetch_cache = MockCache(),
                progress = progress,
                directives = directives.Directives(progress),
                is_live = True,
                allow_exec_cmdline = False,
            )]

            updater = live.LiveUpdater(base_build_params, [copy.copy(base_build_params)], progress)

            def run_server():
                updater.run(address = '127.0.0.1',
                            port_range = range(14100, 14101),
                            launch_browser = False)

            (server_thread := threading.Thread(target = run_server)).start()

            def load(path):
                with urllib.request.urlopen(f'http://127.0.0.1:14100/{path}') as conn:
                    return (conn.status, conn.read())

            try:
                time.sleep(0.1)  # Wait for server to come up

                from urllib.request import HTTPError as Err
                self.assertRaisesRegex(Err, '404', load, 'doesntexist')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/index.html')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/doesntexist')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/doesntexist/doesntexist')

                new_complete_build_params = [copy.copy(base_build_params)]
                new_complete_build_params[0][0].name = 'new_name'
                mock_compile.return_value = new_complete_build_params

                # Trigger recompile
                src_file.write_text('Mock markdown!')
                time.sleep(0.1)  # Wait for updater to recompile

                self.assertRaisesRegex(Err, '404', load, 'doesntexist')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/index.html')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/doesntexist')
                self.assertRaisesRegex(Err, '404', load, 'doesntexist/doesntexist/doesntexist')

            finally:
                updater.shutdown()
                server_thread.join()
