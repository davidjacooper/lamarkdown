'''
# Build Module API

The functions here are to be used by build modules (md_build.py, etc) to define extensions,
variants, css styles, etc. Build modules just need to 'import lamarkdown'.

(The get_params() function further exposes the BuildParams object directly, which permits greater
flexibility.)
'''

from lamarkdown.lib.build_params import BuildParams, Resource
import markdown
from lxml.cssselect import CSSSelector

import importlib
from typing import Any, Callable, Dict, List, Optional, Set, Union
from collections.abc import Iterable


class BuildParamsException(Exception): pass

def _params():
    if BuildParams.current is None:
        raise BuildParamsException(f'Build params not yet initialised')
    return BuildParams.current


def include(*module_names: str, pkg = 'lamarkdown'):
    """
    Applies a build module, or modules, by name. You can also use the standard 'import' statement,
    but that breaks on live updating, because we need build modules to reload in that case.
    """

    for name in module_names:
        if pkg is None or pkg == '':
            module_spec = importlib.util.find_spec(name)
        else:
            module_spec = importlib.util.find_spec('.' + name, package = pkg)

        if module_spec is None:
            raise BuildParamsException(f'Cannot find module "{name}"')

        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)


def get_build_dir():
    return _params().build_dir

def get_env():
    return _params().env

def get_params():
    return _params()

def variant(name: str, classes: Union[str, List[str], None]):
    if classes is None:
        classes = []
    elif isinstance(classes, str):
        classes = [classes]
    else:
        classes = list(classes)
    _params().variants[name] = classes

def base_variant(classes: Union[str, List[str], None]):
    variant('', classes)

def variants(variant_dict = {}, **variant_kwargs):
    for name, classes in variant_dict.items():
        variant(name, classes)
    for name, classes in variant_kwargs.items():
        variant(name, classes)

def extensions(*extensions: Union[str,markdown.extensions.Extension]):
    _params().extensions.extend(extensions)

def config(configs: Dict[str,Dict[str,Any]]):
    p = _params()
    exts = set(p.extensions)
    for key in configs.keys():
        if key not in exts:
            raise BuildParamsException(f'config(): "{key}" is not an applied markdown extension.')

    p.extension_configs.update(configs)


def _res(value: Union[str,Callable[[Set[str]],Optional[str]]],
         if_xpaths:    Union[str,Iterable[str]] = [],
         if_selectors: Union[str,Iterable[str]] = []):
    '''
    Creates a Resource object, based on either a value or a value factory, and a set of
    zero-or-more XPath expressions and/or CSS selectors (which are compiled to XPaths).
    '''

    # FIXME: this arrangement doesn't allow value factories to query selectors properly, because
    # it's expected to supply the xpath equivalent, which it never sees.

    if callable(value):
        value_factory = value
    elif if_xpaths or if_selectors:
        # If a literal value is given as well as one or more XPath expressions, we'll produce that
        # value if any of the expressions are found.
        value_factory = lambda subset_found: value if subset_found else None
    else:
        # If a literal value is given with no XPaths, then we'll produce that value unconditionally.
        value_factory = lambda _: value

    if isinstance(if_xpaths, str):
        if_xpaths = [if_xpaths]

    if isinstance(if_selectors, str):
        if_selectors = [if_selectors]

    xpaths = []
    xpaths.extend(if_xpaths)
    xpaths.extend(CSSSelector(sel).path for sel in if_selectors)
    return Resource(value_factory, xpaths)


def css_rule(selectors: Union[str,Iterable[str]], properties: str):
    '''
    Sets a CSS rule, consisting of one or more selectors and a set of properties (together in a
    single string).

    The selector(s) are used at 'compile-time' as well as 'load-time', to determine whether the
    rule becomes part of the output document at all. Only selectors that actually match the
    document are included in the output.
    '''
    if isinstance(selectors, str):
        selectors = [selectors]

    xpath_to_sel = {CSSSelector(sel).path: sel for sel in selectors}

    def value_factory(found: Set[str]) -> Optional[str]:
        if not found: return None
        return ', '.join(xpath_to_sel[xp] for xp in sorted(found)) + ' { ' + properties + ' }'

    _params().css.append(_res(value_factory, if_xpaths = xpath_to_sel.keys()))


def css(value: str, **kwargs):
    _params().css.append(_res(value, **kwargs))

def js(value: str, **kwargs):
    _params().js.append(_res(value, **kwargs))

def css_files(*values: List[str], **kwargs):
    _params().css_files.extend(_res(value, **kwargs) for value in values)

def js_files(*values: List[str], **kwargs):
    _params().js_files.extend(_res(value, **kwargs) for value in values)

def wrap_content(start: str, end: str):
    p = _params()
    p.content_start = start + p.content_start
    p.content_end += end

def wrap_content_inner(start: str, end: str):
    p = _params()
    p.content_start += start
    p.content_end = end + p.content_end
