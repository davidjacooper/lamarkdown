from . import build_params, md_compiler, live, progress as prog, directives as direc

import diskcache  # type: ignore
import platformdirs

import argparse
import os
from pathlib import Path
import re


VERSION = '0.11'

DIRECTORY_BUILD_FILE = 'md_build.py'
NAME = 'lamd'  # For errors/warnings


def port_range_type(s: str) -> range:
    match = re.fullmatch('(?P<start>[0-9]+)(-(?P<end>[0-9]+))?', s)
    if not match:
        raise argparse.ArgumentTypeError(
            'Must be a non-negative integer (e.g., 8000), or integer range (e.g., 8000-8010)')

    start = int(match['start'])
    end = int(match['end'] or start)
    if not (1024 <= start <= end <= 65535):
        # Should we restrict ports less than 1024 (privileged ports)? This can't affect ordinary
        # use, particularly as users don't have access to such ports anyway. It may help to hint
        # at the fact that live-update mode is not designed to be a public-facing web server.
        raise argparse.ArgumentTypeError(
            'Port range must be within the range 1024-65535, with start <= end')

    return range(start, end + 1)


def get_fetch_cache_dir() -> str:
    return platformdirs.user_cache_dir(appname = 'lamarkdown', version = VERSION)


def main():
    fetch_cache_dir = get_fetch_cache_dir()

    parser = argparse.ArgumentParser(
        prog        = 'lamd',
        description = ('Compile .md (markdown) files to .html using the Python Markdown library. '
                       'See README.md for key details.'),
        formatter_class = argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        '-v', '--version', action = 'version',
        version = f'Lamarkdown {VERSION}\n(fetch cache: {fetch_cache_dir})')

    parser.add_argument(
        'input', metavar = 'INPUT.md', type = str,
        help = 'Input markdown (.md) file')

    parser.add_argument(
        '-o', '--output', metavar = 'OUTPUT.html', type = str,
        help = 'Output HTML file. (By default, this is based on the input filename.)')

    parser.add_argument(
        '-b', '--build', metavar = 'BUILD.py', type = str, action = 'append',
        help = ('Manually specify a build (.py) file, which itself specifies extensions (to '
                'Python-Markdown), CSS, JavaScript, etc.'))

    parser.add_argument(
        '-B', '--no-auto-build-files', action = 'store_true',
        help = ('Suppresses build file auto-detection, so that only build files specified with '
                '-b/--build will be loaded. Lamarkdown will not automatically read "md_build.py" '
                'or "<source>.py" in this case.'))

    parser.add_argument(
        '-e', '--allow-exec', action = 'store_true',
        help = ('Allows execution of code from a markdown document, if/when requested (not just '
                'from the build files).'))

    parser.add_argument(
        '-D', '--no-build-defaults', action = 'store_true',
        help = ('Suppresses the automatic default settings in case no build files exist. Has no '
                'effect if any build files are found and read.'))

    parser.add_argument(
        '--clean', action = 'store_true',
        help = 'Clear the build cache before compiling the document.')

    parser.add_argument(
        '-l', '--live', action = 'store_true',
        help = ('Keep running, recompile automatically when source changes are detected, and '
                'serve the resulting file from a local web server.'))

    parser.add_argument(
        '--address', metavar = 'IP_HOST|"any"', type = str,
        help = ('In live mode, have the server listen at the given address, or all addresses if '
                '"any" is specified. By default, the server listens only on 127.0.0.1 (loopback). '
                '*USE WITH CAUTION!* Do not use this option to expose the built-in web server to '
                'the public internet, or other untrusted parties. (Upload the output HTML file to '
                'a proper production web server for that.)'))

    parser.add_argument(
        '--port', metavar = 'PORT[-PORT]', type = port_range_type,
        help = ('In live mode, listen on the first available port in this range. By default, this '
                f'is {live.DEFAULT_PORT_RANGE.start}-{live.DEFAULT_PORT_RANGE.stop}.'))

    parser.add_argument(
        '-W', '--no-browser', action = 'store_true',
        help = 'Do not automatically launch a web browser when starting live mode with -l/--live.')


    args = parser.parse_args()

    src_file = Path(args.input).absolute()
    if args.input.endswith('.') and not src_file.is_dir():
        src_file = Path(args.input[:-1]).absolute()

    if (src_file.suffix.lower() in ['', '.html', '.py']
            and (f := src_file.with_suffix('.md')).exists()):
        src_file = f

    build_dir = src_file.parent / 'build' / src_file.stem
    build_cache_dir = build_dir / 'cache'
    extra_build_files = [Path(f).absolute() for f in args.build] if args.build else []

    progress = prog.Progress()
    if args.output:
        target_file = Path(args.output).absolute()
        if target_file.is_dir():
            target_file = (target_file / src_file.stem).with_suffix('.html')
    else:
        target_file = src_file.with_suffix('.html')

    go = True

    if not src_file.suffix.lower() == '.md':
        go = False
        progress.error(NAME, msg = f'"{src_file}" must end in ".md"')

    for in_file in [src_file, *extra_build_files]:
        if not in_file.exists():
            go = False
            progress.error(NAME, msg = f'"{in_file}" not found')

        elif not in_file.is_file():
            go = False
            progress.error(NAME, msg = f'"{in_file}" is not a file')

        elif not os.access(in_file, os.R_OK):
            go = False
            progress.error(NAME, msg = f'"{in_file}" is not readable')


    if target_file.exists():
        if not os.access(target_file, os.W_OK):
            go = False
            progress.error(NAME, msg = f'cannot write output: "{target_file}" is not writable')
    else:
        if not os.access(directory := target_file.parent, os.W_OK):
            go = False
            progress.error(NAME, msg = f'cannot write output: "{directory}" is not writable')

    try:
        build_dir.mkdir(parents = True, exist_ok = True)
    except Exception as e:
        progress.error(NAME, msg = f'cannot create/open build directory: {e}')

    try:
        build_cache = diskcache.Cache(str(build_cache_dir))
    except Exception as e:
        go = False
        progress.error(NAME, msg = f'cannot create/open build cache: {e}')

    try:
        fetch_cache = diskcache.Cache(fetch_cache_dir)
    except Exception as e:
        go = False
        progress.error(NAME, msg = f'cannot create/open fetch cache: {e}')

    if go:
        # Changing into the source directory (in case we're not in it) means that further file paths
        # referenced during the build process will be relative to the source file, and not
        # (necessarily) whatever arbitrary directory we started in.
        os.chdir(src_file.parent)

        base_build_params = build_params.BuildParams(
            src_file = src_file,
            target_file = target_file,
            build_files = (
                extra_build_files if args.no_auto_build_files
                else [
                    src_file.parent / DIRECTORY_BUILD_FILE,
                    src_file.with_suffix('.py'),
                    *extra_build_files
                ]),
            build_dir = build_dir,
            build_defaults = not args.no_build_defaults,
            build_cache = build_cache,
            fetch_cache = fetch_cache,
            progress = progress,
            directives = direc.Directives(progress),
            is_live = args.live is True,
            allow_exec_cmdline = args.allow_exec is True,
            allow_exec         = args.allow_exec is True
        )

        if args.clean:
            base_build_params.build_cache.clear()

        complete_build_params = md_compiler.compile(base_build_params)

        if args.live:
            address = (
                live.ANY_ADDRESS
                if args.address == 'any'
                else (args.address or live.LOOPBACK_ADDRESS))
            port_range = args.port or live.DEFAULT_PORT_RANGE

            live.LiveUpdater(
                base_build_params,
                complete_build_params
            ).run(
                address = address,
                port_range = port_range,
                launch_browser = args.no_browser is not True
            )


if __name__ == "__main__":
    main()
