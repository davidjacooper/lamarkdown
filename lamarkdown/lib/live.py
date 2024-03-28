'''
Implements the '--live/-l' mode, to give the user immediate feedback while editing.

We launch a simple web server, open a web browser, monitor source files (both the .md file and .py
build modules), and reload the page when anything changes.

*DO NOT* make this web server publically accessible. It is intended only as a productivity
improvement for a single local user, and is not designed for security or performance.
'''

from __future__ import annotations
from lamarkdown.lib import md_compiler
from lamarkdown.lib.build_params import BuildParams

import watchdog.observers
import watchdog.events

from dataclasses import dataclass
import http.server
import json
from pathlib import Path
import re
import string
import threading
import time
import webbrowser

NAME = 'live updating'  # For progress/error messages

LOOPBACK_ADDRESS = '127.0.0.1'
DEFAULT_PORT_RANGE = range(8000, 8020)

# The empty string will cause the server to listen on all interfaces, as per the socket
# documentation https://docs.python.org/3/library/socket.html
ANY_ADDRESS = ''

CONTROL_PANEL_ID = '_lamd_control_panel'
CONTROL_PANEL_TIMESTAMP_ID = '_lamd_timestamp'
CONTROL_PANEL_CLEAN_BUTTON_ID = '_lamd_cleanbuild_btn'
CONTROL_PANEL_MESSAGE_ID = '_lamd_msg'

CHECK_INTERVAL       = 500  # milliseconds
ERROR_COUNTDOWN      = 5    # times the check interval
DISCONNECT_COUNTDOWN = 30   # times the check interval

POST_RESPONSE = 'ok'

VARIANT_QUERY_REGEX = re.compile('/(?P<variant>[^/]*)/?index.html')
VARIANT_FILE_QUERY_REGEX = re.compile('/(?P<variant>[^/]*)/(?P<file>.+)')
BASE_FILE_QUERY_REGEX = re.compile('/(?P<file>.+)')


CONTROL_PANEL_STYLE = re.sub(
    r'(\n\s+)+', ' ',
    fr'''
    <style>
        @media print {{
            #{CONTROL_PANEL_ID} {{ display: none; }}
        }}
        @media screen {{
            #{CONTROL_PANEL_ID} {{
                position: fixed;
                background: white;
                color: black;
                font-family: sans-serif;
                font-size: small;
                line-height: 1.5;
                border-radius: 0.5ex;
                padding: 1em;
                right: 1ex;
                top: 1ex;
                overflow-wrap: anywhere;
                overflow-y: auto;
                max-width: 20%;
                max-height: 90%;
                z-index: 1000;
            }}
            #{CONTROL_PANEL_ID} button {{
                margin-top: 1ex;
            }}
        }}
    </style>
    '''
).strip()


# Observe the '$update_n' and '$escaped_variant_name' placeholders.
# (Note that '${text}' is _not_ a placeholder on the Python side, but just part of the script.)
UPDATE_SCRIPT_TEMPLATE = string.Template(
    f'''
    <script>
    (() => {{
        let errorCountdown = {ERROR_COUNTDOWN};
        let disconnectCountdown = {DISCONNECT_COUNTDOWN};

        function showError(user_msg, internal_detail)
        {{
            console.log(user_msg);
            console.log(internal_detail);
            document.getElementById('{CONTROL_PANEL_MESSAGE_ID}').dataset.msg = user_msg;
        }}

        function update()
        {{
            if(disconnectCountdown > 0)
            {{
                fetch('/query')
                    .then(response => response.json())
                    .then(json =>
                    {{
                        if(json.update_n != $update_n)
                        {{
                            if(json.names.includes('$escaped_variant_name'))
                            {{
                                document.location.reload();
                            }}
                            else
                            {{
                                document.location.assign('/');
                            }}
                        }}
                        setTimeout(update, {CHECK_INTERVAL});
                        errorCountdown = {ERROR_COUNTDOWN};
                        disconnectCountdown = {DISCONNECT_COUNTDOWN};
                    }})
                    .catch(error =>
                    {{
                        if(errorCountdown > 0)
                        {{
                            errorCountdown--;
                            if(errorCountdown == 0)
                            {{
                                showError('Unable to contact server.', error.message);
                            }}
                        }}
                        else
                        {{
                            disconnectCountdown--;
                            if(disconnectCountdown == 0)
                            {{
                                showError(
                                    'Disconnected from server. Reload the page to resume, once the'
                                    + 'server is running again.',
                                    error.message);
                            }}
                        }}
                    }});
            }}
        }};
        setTimeout(update, {CHECK_INTERVAL});

        document.getElementById('{CONTROL_PANEL_CLEAN_BUTTON_ID}').onclick = (event) =>
        {{
            fetch('/cleanbuild', {{method: 'POST'}})
                .then(response => response.text())
                .then(text =>
                {{
                    if(text != '{POST_RESPONSE}')
                    {{
                        showError('Server returned unexpected response', `"$${{text}}"`);
                    }}
                }})
                .catch(error => showError('Unable to contact server.', error.message));
            event.preventDefault();
        }};

        document.getElementById('{CONTROL_PANEL_TIMESTAMP_ID}').innerHTML = 'Last updated:<br/>' +
            new Date().toLocaleString();
    }})();
    </script>
    '''.strip())


FAVICON_PNG_DATA = (
    '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')

FAVICON_LINK = f'<link rel="icon" type="image/png" href="data:;base64,{FAVICON_PNG_DATA}" />'


@dataclass
class OutputDoc:
    name: str
    full_html: str
    filename: str
    path: Path


class LiveUpdater(watchdog.events.FileSystemEventHandler):
    HOME = Path.home()

    def __init__(self,
                 base_build_params: BuildParams,
                 complete_build_params: list[BuildParams]):
        self._base_build_params = base_build_params
        self._complete_build_params = complete_build_params
        self._output_docs: dict[str, OutputDoc] = {}
        self._base_variant = complete_build_params[0].name

        self._server: http.server.HTTPServer | None = None
        self._server_thread: threading.Thread | None = None

        self._dependency_files: set[Path] = set()
        self._dependency_paths: set[Path] = set()
        self._fs_observer: watchdog.observers.Observer | None = None

        self._update_n = 0
        self._update_event: threading.Event | None = None

        self._compile_lock = threading.Lock()
        self._compile_thread: threading.Thread | None = None


    @property
    def update_n(self):
        return self._update_n


    def wait_for_update(self, timeout = 1):
        if self._update_event is None:
            self._update_event = threading.Event()
        return self._update_event.wait(timeout)


    def read_and_instrument(self):
        self._output_docs = {}

        for p in self._complete_build_params:
            name = p.name
            output_file = p.output_file
            self._output_docs[name] = OutputDoc(name = name,
                                                full_html = output_file.read_text(),
                                                filename = output_file.name,
                                                path = output_file.parent)


    def watch_dependencies(self):
        if self._fs_observer is None:
            self._fs_observer = watchdog.observers.Observer()
            self._fs_observer.start()
        else:
            self._fs_observer.unschedule_all()

        self._dependency_files = {
            dep_file.absolute()
            for params in self._complete_build_params
            for dep_file in [params.src_file, *params.build_files, *params.live_update_deps]
        }

        self._dependency_paths = set()
        for path in self._dependency_files:
            while True:

                parent = path.parent
                if parent in self._dependency_paths or parent == path:
                    # Either 'parent' was already seen, or we've hit the root directory
                    break

                path = parent
                self._dependency_paths.add(path)
                if path.exists():
                    self._fs_observer.schedule(self, str(path))

                if path == self.HOME:
                    # Don't go outside the HOME directory (if we started inside of it).
                    break


    def on_closed(self, event):
        '''
        Event handler (watchdog.events.FileSystemEventHandler), called when something else finishes
        writing to a file.

        We have to watch entire directory(ies), but we only want to know about the specific set of
        files.

        Once we call recompile(), the set of dependencies will be recalculated.
        '''
        if Path(event.src_path) in self._dependency_files:
            self.recompile()

    def on_created(self, event):
        '''
        Event handler (watchdog.events.FileSystemEventHandler), fired when a file/dir is created.
        We're specifically looking for intermediate path components, previously missing, that have
        just been created.

        We take this as a hint to recompile right away, even though we don't immediately know
        whether any new dependency file(s) exist in that new directory, because:
        (a) New files might appear in the directory before we can start monitoring it (basically a
            race condition), and
        (b) This probably won't happen _that_ often.
        '''
        if Path(event.src_path) in self._dependency_paths:
            self.recompile()


    def on_modified(self, event):
        '''
        Event handler (watchdog.events.FileSystemEventHandler). Included for completeness, but I
        don't _think_ there's any benefit to acting on this event. For files, 'on_closed()' yields
        more intuitive results, and for directories, on_created(), on_deleted() and on_moved()
        allow more fine-grained control.'''
        pass


    def on_deleted(self, event):
        p = Path(event.src_path)
        if p in self._dependency_files or p in self._dependency_paths:
            self.recompile()


    def on_moved(self, event):
        self.on_deleted(event)


    def run(self,
            address: str = LOOPBACK_ADDRESS,
            port_range: range = DEFAULT_PORT_RANGE,
            launch_browser: bool  = True):

        with self._compile_lock:
            if self._server_thread is not None:
                raise RuntimeError('Cannot run LiveUpdater() multiple times concurrently')
            self._server_thread = threading.current_thread()

        self.read_and_instrument()
        self.watch_dependencies()

        try:
            # Iterate over a port range, and pick the first free port.
            port = None
            for try_port in port_range:
                try:
                    # Create the server. This attempts to bind to the given port.
                    self._server = http.server.HTTPServer((address, try_port), self.make_handler())
                    port = try_port
                    break
                except OSError:  # Port in use; try next one.
                    self._base_build_params.progress.warning(
                        NAME, msg = f'Port {try_port} appears to be in use.')

            if port is not None:
                assert self._server is not None
                self._base_build_params.progress.progress(
                    NAME,
                    msg = ('Launching server and browser, and monitoring changes to source/build'
                           'files.'),
                    advice = (f'Browse to http://{address or "localhost"}:{port}\nPress Ctrl-C to '
                              'quit.'))

                if launch_browser:
                    # We want to open a web browser at the address we're serving, but not before
                    # the server is running. Hence, we start a new thread, which waits 0.5 secs
                    # while the main thread calls serve_forever(), then runs the browser.
                    def open_browser():
                        time.sleep(0.5)
                        webbrowser.open(f'http://localhost:{port}')

                    threading.Thread(target = open_browser).start()

                self._server.serve_forever()

            else:
                self._base_build_params.progress.error(
                    NAME,
                    msg = ('Cannot launch server: all ports in range '
                           f'{port_range.start}-{port_range.stop - 1} are in use.'))

        except KeyboardInterrupt:  # Ctrl-C
            pass

        finally:
            with self._compile_lock:
                compile_thread = self._compile_thread
                fs_observer = self._fs_observer
                if fs_observer is not None:
                    fs_observer.stop()
                    self._fs_observer = None
                self._server_thread = None

            if fs_observer is not None:
                fs_observer.join()
            if compile_thread is not None:
                compile_thread.join()


    def shutdown(self):
        with self._compile_lock:
            assert self._server_thread is not None
            if self._server is None:
                raise ValueError('Live updater not currently running')
            self._server.server_close()
            self._server.shutdown()
            self._server = None
            server_thread = self._server_thread
        server_thread.join()


    def clear_cache(self):
        self._base_build_params.progress.warning(NAME, msg = 'Clearing cache')
        self._base_build_params.build_cache.clear()


    def recompile(self):
        with self._compile_lock:
            assert self._fs_observer is not None
            self._fs_observer.stop()
            self._fs_observer = None
            self._compile_thread = threading.current_thread()

            try:
                # Note: we don't generally expect any exceptions here, but P > 0, and we must try to
                # keep the interface working as much as we can.

                try:
                    self._complete_build_params = md_compiler.compile(self._base_build_params)
                except Exception as e:
                    self._base_build_params.progress.error(NAME, exception = e)

                self._base_variant = self._complete_build_params[0].name
                self._update_n += 1

                try:
                    self.read_and_instrument()
                    self.watch_dependencies()
                except Exception as e:
                    self._base_build_params.progress.error(NAME, exception = e)

                if self._update_event is not None:
                    self._update_event.set()

            finally:
                self._compile_thread = None


    def make_handler(self):
        updater_self = self
        encode_json = json.JSONEncoder().encode

        class _handler(http.server.BaseHTTPRequestHandler):

            def send_main_content(self, variant_name: str):
                self.send_response(200)
                self.send_header('ContentType', 'text/html')
                self.end_headers()

                update_script = UPDATE_SCRIPT_TEMPLATE.substitute(
                    {
                        'update_n':             updater_self._update_n,
                        'escaped_variant_name': (variant_name
                                                 .replace('\\', '\\\\')
                                                 .replace("'", "\\'")
                                                 .replace('\n', '\\n'))
                    })

                control_panel = re.sub(
                    r'(\n\s+)+', ' ', rf'''
                    <div id="{CONTROL_PANEL_ID}" data-update-n="{updater_self._update_n}">
                        <div id="{CONTROL_PANEL_TIMESTAMP_ID}"></div>
                        <div id="{CONTROL_PANEL_MESSAGE_ID}"></div>
                        <form>
                            <button id="{CONTROL_PANEL_CLEAN_BUTTON_ID}">Clean Build</button>
                        </form>
                    ''')
                if len(updater_self._output_docs) >= 2:
                    control_panel += (
                        '<hr/><strong>Variants</strong><br/>'
                        + '<br/>'.join(
                            f'<a href="/{doc.name}{"/" if doc.name else ""}index.html">'
                            f'{doc.filename}</a>'
                            for doc in updater_self._output_docs.values())
                    )
                control_panel += '</div>'

                message = (
                    updater_self._output_docs[variant_name].full_html
                    .replace('</head>', f'{FAVICON_LINK}\n{CONTROL_PANEL_STYLE}\n</head>')
                    .replace('<body>', f'<body>\n{control_panel}')
                    .replace('</body>', f'{update_script}\n</body>')
                )

                self.wfile.write(message.encode('utf-8'))


            def send_file(self, path: Path):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(path.read_bytes())


            def do_POST(self):
                if self.path == '/cleanbuild':
                    self.send_response(200)
                    self.send_header('ContentType', 'text/plain')
                    self.end_headers()
                    self.wfile.write(POST_RESPONSE.encode('utf-8'))

                    def clean_build():
                        updater_self.clear_cache()
                        updater_self.recompile()

                    threading.Thread(target = clean_build).start()
                else:
                    self._no()


            def do_GET(self):

                default_variant_name = (
                    updater_self._base_variant
                    or next(iter(updater_self._output_docs.keys())))

                if self.path == '/':
                    self.send_main_content(default_variant_name)
                    return

                if self.path == '/query':
                    self.send_response(200)
                    self.send_header('ContentType', 'application/json')
                    self.end_headers()

                    self.wfile.write(encode_json({
                        'update_n': updater_self._update_n,
                        'names': list(updater_self._output_docs.keys())
                    }).encode())
                    return

                re_match = VARIANT_QUERY_REGEX.fullmatch(self.path)
                if re_match:
                    variant_name = re_match['variant']
                    if variant_name in updater_self._output_docs:
                        self.send_main_content(variant_name)
                        return

                re_match = VARIANT_FILE_QUERY_REGEX.fullmatch(self.path)
                if re_match:
                    variant_name = re_match['variant']
                    if variant_name in updater_self._output_docs:
                        full_path = Path(
                            updater_self._output_docs[variant_name].path,
                            *re_match['file'].split('/'))
                        if full_path.is_file():
                            self.send_file(full_path)
                            return


                re_match = BASE_FILE_QUERY_REGEX.fullmatch(self.path)
                if re_match:
                    full_path = Path(
                        updater_self._output_docs[default_variant_name].path,
                        *re_match['file'].split('/'))
                    if full_path.is_file():
                        self.send_file(full_path)
                        return

                self._no()

            def _no(self):
                self.send_response(404)
                self.send_header('ContentType', 'text/plain')
                self.end_headers()
                self.wfile.write('404 - Yeah nah mate.'.encode('utf-8'))

            def log_message(self, format, *args):
                pass

        return _handler
