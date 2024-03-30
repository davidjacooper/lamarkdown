from __future__ import annotations
from lamarkdown.lib import lamd, directives
from ..util.mock_progress import MockProgress
from ..util.mock_cache import MockCache
import unittest
from unittest.mock import patch
from hamcrest import (assert_that, contains_exactly, empty, has_entries, instance_of, is_, is_not,
                      raises, same_instance)

import diskcache  # type: ignore

import os
from pathlib import Path
import stat
import tempfile


def make_mock_progress_fn():
    mock_progress = MockProgress(expect_error = True)
    return lambda: mock_progress


def make_mock_cache_fn():
    mock_cache = MockCache()
    return lambda *args: mock_cache


class MockExit(Exception):
    def __init__(self, code):
        super().__init__()
        self.code = code


def mock_exit(code):
    raise MockExit(code)


@patch('lamarkdown.lib.progress.Progress', new_callable = make_mock_progress_fn)
@patch('lamarkdown.lib.md_compiler.compile_all')
class LamdTestCase(unittest.TestCase):

    def setUp(self):
        self.orig_dir = Path.cwd()
        self.tmp_dir_context = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp_dir_context.__enter__())
        os.chdir(self.tmp_dir)


    def tearDown(self):
        os.chdir(self.orig_dir)
        self.tmp_dir_context.__exit__(None, None, None)


    def create_mock_file(self, path: str | Path):
        Path(path).write_text(f'Mock content for {path}')


    def assert_no_errors(self, mock_progress_fn):
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, empty())


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_okay_defaults(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        params = mock_compile.call_args.args[0][0]

        assert_that(
            params.build_files,
            contains_exactly(
                self.tmp_dir / 'md_build.py',
                self.tmp_dir / 'test_doc.py'
            ))
        assert_that(
            params.build_dir,
            is_(self.tmp_dir / 'build' / 'test_doc'))
        assert_that(params.src_file,            is_(self.tmp_dir / 'test_doc.md'))
        assert_that(params.target_file,         is_(self.tmp_dir / 'test_doc.html'))
        assert_that(params.build_defaults,      is_(True))
        assert_that(params.build_cache,         instance_of(diskcache.Cache))
        assert_that(params.fetch_cache,         instance_of(diskcache.Cache))
        assert_that(params.build_cache,         is_not(same_instance(params.fetch_cache)))
        assert_that(params.progress,            is_(mock_progress_fn()))
        assert_that(params.directives,          instance_of(directives.Directives))
        assert_that(params.is_live,             is_(False))
        assert_that(params.allow_exec_cmdline,  is_(False))


    @patch('sys.argv', ['lamd', 'test_doc1.md', 'test_doc2.md', 'test_doc3.md'])
    def test_multiple_input_files(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc1.md')
        self.create_mock_file('test_doc2.md')
        self.create_mock_file('test_doc3.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        for i, params in enumerate(mock_compile.call_args.args[0], 1):
            assert_that(
                params.build_files,
                contains_exactly(
                    self.tmp_dir / 'md_build.py',
                    self.tmp_dir / f'test_doc{i}.py'
                ))
            assert_that(
                params.build_dir,
                is_(self.tmp_dir / 'build' / f'test_doc{i}'))
            assert_that(params.src_file,            is_(self.tmp_dir / f'test_doc{i}.md'))
            assert_that(params.target_file,         is_(self.tmp_dir / f'test_doc{i}.html'))
            assert_that(params.build_defaults,      is_(True))
            assert_that(params.build_cache,         instance_of(diskcache.Cache))
            assert_that(params.fetch_cache,         instance_of(diskcache.Cache))
            assert_that(params.build_cache,         is_not(same_instance(params.fetch_cache)))
            assert_that(params.progress,            is_(mock_progress_fn()))
            assert_that(params.directives,          instance_of(directives.Directives))
            assert_that(params.is_live,             is_(False))
            assert_that(params.allow_exec_cmdline,  is_(False))


    @patch.multiple('sys', argv = ['lamd'], exit = mock_exit)
    def test_no_args(self, mock_compile, mock_progress_fn):
        assert_that(lamd.main, raises(MockExit))
        mock_compile.assert_not_called()
        self.assert_no_errors(mock_progress_fn)  # Handled as a help message


    @patch('sys.argv', ['lamd', 'test_doc'])
    def test_auto_correct1(self, *args):
        self._test_auto_correct(*args)

    @patch('sys.argv', ['lamd', 'test_doc.'])
    def test_auto_correct2(self, *args):
        self._test_auto_correct(*args)

    @patch('sys.argv', ['lamd', 'test_doc.html'])
    def test_auto_correct3(self, *args):
        self._test_auto_correct(*args)

    @patch('sys.argv', ['lamd', 'test_doc.py'])
    def test_auto_correct4(self, *args):
        self._test_auto_correct(*args)

    def _test_auto_correct(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        params = mock_compile.call_args.args[0][0]
        assert_that(params.src_file,    is_(self.tmp_dir / 'test_doc.md'))
        assert_that(params.target_file, is_(self.tmp_dir / 'test_doc.html'))


    @patch('sys.argv', ['lamd', 'test_doc'])
    def test_misnamed_input1(self, *args):
        self.create_mock_file('test_doc')
        self._test_misnamed_input(*args)

    @patch('sys.argv', ['lamd', 'test_doc.'])
    def test_misnamed_input2(self, *args):
        self.create_mock_file('test_doc.')
        self._test_misnamed_input(*args)

    @patch('sys.argv', ['lamd', 'test_doc.html'])
    def test_misnamed_input3(self, *args):
        self.create_mock_file('test_doc.html')
        self._test_misnamed_input(*args)

    @patch('sys.argv', ['lamd', 'test_doc.py'])
    def test_misnamed_input4(self, *args):
        self.create_mock_file('test_doc.py')
        self._test_misnamed_input(*args)

    @patch('sys.argv', ['lamd', 'test_doc1.md', 'test_doc2.py'])
    def test_misnamed_input5(self, *args):
        self.create_mock_file('test_doc1.md')
        self.create_mock_file('test_doc2.py')
        self._test_misnamed_input(*args)

    def _test_misnamed_input(self, mock_compile, mock_progress_fn):
        lamd.main()
        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_missing_input1(self, *args):
        self._test_missing_input(*args)

    @patch('sys.argv', ['lamd', 'test_doc1.md', 'test_doc2.md'])
    def test_missing_input2(self, *args):
        self.create_mock_file('test_doc1.md')
        self._test_missing_input(*args)

    def _test_missing_input(self, mock_compile, mock_progress_fn):
        lamd.main()
        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_unreadable_input(self, mock_compile, mock_progress_fn):
        '''
        This test won't work correctly on Windows filesystems.
        '''

        self.create_mock_file('test_doc.md')
        Path('test_doc.md').chmod(0)
        lamd.main()

        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_unwritable_target(self, mock_compile, mock_progress_fn):
        '''
        This test won't work correctly on Windows filesystems.
        '''

        self.create_mock_file('test_doc.md')
        self.create_mock_file('test_doc.html')
        Path('test_doc.html').chmod(0)
        lamd.main()

        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_missing_target_unwritable_directory(self, mock_compile, mock_progress_fn):
        '''
        This test won't work correctly on Windows filesystems.
        '''

        self.create_mock_file('test_doc.md')
        self.tmp_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
        lamd.main()

        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    def test_unwritable_build_directory(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        build_dir = self.tmp_dir / 'build'
        build_dir.mkdir()
        build_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
        lamd.main()

        mock_compile.assert_not_called()
        mock_progress = mock_progress_fn()
        assert_that(mock_progress.warning_messages, empty())
        assert_that(mock_progress.error_messages, is_not(empty()))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-o', str(Path('dir', 'different.html'))])
    def test_target_name1(self, *args):
        self._test_target_name(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--output', str(Path('dir', 'different.html'))])
    def test_target_name2(self, *args):
        self._test_target_name(*args)

    def _test_target_name(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        Path('dir').mkdir()
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        params = mock_compile.call_args.args[0][0]
        assert_that(params.src_file,    is_(self.tmp_dir / 'test_doc.md'))
        assert_that(params.target_file, is_(self.tmp_dir / 'dir' / 'different.html'))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-o', 'dir'])
    def test_target_directory1(self, *args):
        self._test_target_directory(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--output', 'dir'])
    def test_target_directory2(self, *args):
        self._test_target_directory(*args)

    def _test_target_directory(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        Path('dir').mkdir()
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        params = mock_compile.call_args.args[0][0]
        assert_that(params.src_file,    is_(self.tmp_dir / 'test_doc.md'))
        assert_that(params.target_file, is_(self.tmp_dir / 'dir' / 'test_doc.html'))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-b', 'b1.py', '-b', str(Path('dir', 'b2.py'))])
    def test_extra_build_files1(self, *args):
        self._test_extra_build_files(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md',
                        '--build', 'b1.py', '--build', str(Path('dir', 'b2.py'))])
    def test_extra_build_files2(self, *args):
        self._test_extra_build_files(*args)

    def _test_extra_build_files(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        self.create_mock_file('b1.py')
        Path('dir').mkdir()
        self.create_mock_file(Path('dir', 'b2.py'))
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(
            mock_compile.call_args.args[0][0].build_files,
            contains_exactly(
                self.tmp_dir / 'md_build.py',
                self.tmp_dir / 'test_doc.py',
                self.tmp_dir / 'b1.py',
                self.tmp_dir / 'dir' / 'b2.py'))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-B'])
    def test_no_std_build_files1(self, *args):
        self._test_no_std_build_files(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--no-auto-build-files'])
    def test_no_std_build_files2(self, *args):
        self._test_no_std_build_files(*args)

    def _test_no_std_build_files(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        lamd.main()
        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(mock_compile.call_args.args[0][0].build_files, empty())


    @patch('sys.argv', ['lamd', 'test_doc.md', '-B', '-b', 'b1.py', '-b', 'b2.py'])
    def test_only_extra_build_files1(self, *args):
        self._test_only_extra_build_files(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--no-auto-build-files',
                        '--build', 'b1.py', '--build', 'b2.py'])
    def test_only_extra_build_files2(self, *args):
        self._test_only_extra_build_files(*args)

    def _test_only_extra_build_files(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        self.create_mock_file('b1.py')
        self.create_mock_file('b2.py')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(
            mock_compile.call_args.args[0][0].build_files,
            contains_exactly(
                self.tmp_dir / 'b1.py',
                self.tmp_dir / 'b2.py'))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-e'])
    def test_allow_exec1(self, *args):
        self._test_allow_exec(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--allow-exec'])
    def test_allow_exec2(self, *args):
        self._test_allow_exec(*args)

    def _test_allow_exec(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        lamd.main()
        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(mock_compile.call_args.args[0][0].allow_exec, is_(True))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-D'])
    def test_no_defaults1(self, *args):
        self._test_no_defaults(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--no-build-defaults'])
    def test_no_defaults2(self, *args):
        self._test_no_defaults(*args)

    def _test_no_defaults(self, mock_compile, mock_progress_fn):
        self.create_mock_file('test_doc.md')
        lamd.main()
        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(mock_compile.call_args.args[0][0].build_defaults, is_(False))


    @patch('sys.argv', ['lamd', 'test_doc.md', '--clean'])
    @patch('diskcache.Cache', new_callable = make_mock_cache_fn)
    def test_clean(self, mock_cache_fn, mock_compile, mock_progress_fn):
        cache = mock_cache_fn()
        cache['mock_entry'] = 'mock_value'
        self.create_mock_file('test_doc.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(cache.items(), empty())  # Cleaned


    @patch('sys.argv', ['lamd', 'test_doc.md'])
    @patch('diskcache.Cache', new_callable = make_mock_cache_fn)
    def test_no_clean(self, mock_cache_fn, mock_compile, mock_progress_fn):
        cache = mock_cache_fn()
        cache['mock_entry'] = 'mock_value'
        self.create_mock_file('test_doc.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()
        assert_that(cache, has_entries(mock_entry = 'mock_value'))


    @patch('sys.argv', ['lamd', 'test_doc.md', '-l'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live1(self, *args):
        self._test_live(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '--live'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live2(self, *args):
        self._test_live(*args)

    @patch('sys.argv', ['lamd', 'test_doc.md', '-l', '--address', 'mock_address'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live3(self, *args):
        self._test_live(*args, address = 'mock_address')

    @patch('sys.argv', ['lamd', 'test_doc.md', '-l', '--port', '8765'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live4(self, *args):
        self._test_live(*args, port_range = range(8765, 8766))

    @patch('sys.argv', ['lamd', 'test_doc.md', '-l', '--port', '8765-8770'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live5(self, *args):
        self._test_live(*args, port_range = range(8765, 8771))

    @patch('sys.argv', ['lamd', 'test_doc.md', '-l', '-W'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live6(self, *args):
        self._test_live(*args, launch_browser = False)

    @patch('sys.argv', ['lamd', 'test_doc.md', '-l', '--no-browser'])
    @patch('lamarkdown.lib.live.LiveUpdater')
    def test_live7(self, *args):
        self._test_live(*args, launch_browser = False)

    def _test_live(self, mock_live_updater_fn, mock_compile, mock_progress_fn,
                   address = '127.0.0.1',
                   port_range = range(8000, 8020),
                   launch_browser = True):
        self.create_mock_file('test_doc.md')
        lamd.main()

        self.assert_no_errors(mock_progress_fn)
        mock_compile.assert_called_once()

        mock_progress = mock_progress_fn()
        params_list = mock_compile.call_args.args[0]
        assert_that(mock_compile.call_args.args[0][0].is_live, is_(True))

        complete_params = mock_compile()
        mock_live_updater_fn.assert_called_once_with(params_list,
                                                     complete_params,
                                                     mock_progress)

        live_updater = mock_live_updater_fn()
        live_updater.run.assert_called_once_with(
            address = address,
            port_range = port_range,
            launch_browser = launch_browser)
