'''
# Build Module API

The functions here are to be used by build modules (md_build.py, etc) to define extensions,
variants, css styles, etc. Build modules just need to 'import lamarkdown'.

(The get_params() function further exposes the BuildParams object directly, which permits greater
flexibility.)
'''

from .lib.build_params import BuildParams, Resource, Variant
from markdown.extensions import Extension
from lxml.cssselect import CSSSelector

import importlib
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Union


class BuildParamsException(Exception): pass

def _params():
    if BuildParams.current is None:
        raise BuildParamsException(f'Build params not yet initialised')
    return BuildParams.current


def get_build_dir():
    return _params().build_dir

def get_env():
    return _params().env

def get_params():
    return _params()


def name(n: str):
    _params().name = n

def _callable(fn):
    if not callable(fn):
        raise ValueError(f'Expected a function/callable, but received {type(fn).__name__} (value {fn})')

def target(fn: Callable[[str],str]):
    _callable(fn)
    _params().output_namer = fn

def base_name():
    _params().output_namer = lambda t: t

def variants(*args, **kwargs):
    p = _params()
    for variant_fn in args:
        _callable(variant_fn)
        p.variants.append(Variant(name = variant_fn.__name__,
                                  build_fn = variant_fn))

    for name, variant_fn in kwargs.items():
        _callable(variant_fn)
        p.variants.append(Variant(name = name, build_fn = variant_fn))

def prune(selector: Optional[str] = None,
          xpath: Optional[str] = None):

    if selector is None and xpath is None:
        raise ValueError('Must specify at least one argument')

    hook = lambda elem: elem.getparent().remove(elem)

    if selector is not None:
        with_selector(selector, hook)

    if xpath is not None:
        with_xpath(xpath, hook)

def with_selector(selector: str, fn: Callable):
    with_xpath(CSSSelector(selector).path, fn)

def with_xpath(xpath: str, fn: Callable):
    _callable(fn)
    def hook(root):
        for element in root.xpath(xpath):
            fn(element)
    with_tree(hook)

def with_tree(fn: Callable):
    _callable(fn)
    _params().tree_hooks.append(fn)

def extensions(*extensions: Union[str,Extension]):
    for e in extensions:
        extension(e)

def extension(extension: Union[str,Extension], cfg_dict = {}, **cfg_kwargs):
    p = _params()
    new_config = {**cfg_dict, **cfg_kwargs}

    if isinstance(extension, Extension):
        if new_config:
            raise ValueError('Cannot supply configuration values to an already-instantiated Extension')
        else:
            p.obj_extensions.append(extension)
        return None

    else:
        config = p.named_extensions.get(extension)
        if config:
            config.update(new_config)
            return config
        else:
            p.named_extensions[extension] = new_config
            return new_config


def _res(value: Union[str,Callable[[Set[str]],Optional[str]]],
         if_xpaths:    Union[str,Iterable[str]] = [],
         if_selectors: Union[str,Iterable[str]] = [],
         embed:        Optional[bool] = None):
    '''
    Creates a Resource object, based on either a value or a value factory, and a set of
    zero-or-more XPath expressions and/or CSS selectors (which are compiled to XPaths).
    '''

    # FIXME: this arrangement doesn't allow value factories to query selectors properly, because
    # it's expected to supply the xpath equivalent, which it never sees.

    value_factory: Callable[[Set[str]],Optional[str]]

    if callable(value):
        value_factory = value
    elif if_xpaths or if_selectors:
        # If a literal value is given as well as one or more XPath expressions, we'll produce that
        # value if any of the expressions are found.
        value_factory = lambda subset_found: value if subset_found else None
    else:
        # If a literal value is given with no XPaths, then we'll produce that value unconditionally.
        value_factory = lambda _: value

    xpath_iterable    = [if_xpaths]    if isinstance(if_xpaths,    str) else if_xpaths
    selector_iterable = [if_selectors] if isinstance(if_selectors, str) else if_selectors

    #if isinstance(if_xpaths, str):
        #if_xpaths = [if_xpaths]

    #if isinstance(if_selectors, str):
        #if_selectors = [if_selectors]

    xpaths = []
    xpaths.extend(xpath_iterable)
    xpaths.extend(CSSSelector(sel).path for sel in selector_iterable)
    return Resource(value_factory, xpaths, embed = embed)


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

def css_files(*values: List[str], embed: Optional[bool] = None, **kwargs):
    _params().css_files.extend(
        _res(value, embed = embed, **kwargs)
        for value in values
    )

def js_files(*values: List[str], embed: Optional[bool] = None, **kwargs):
    _params().js_files.extend(
        _res(value, embed = embed, **kwargs)
        for value in values
    )

def wrap_content(start: str, end: str):
    p = _params()
    p.content_start = start + p.content_start
    p.content_end += end

def wrap_content_inner(start: str, end: str):
    p = _params()
    p.content_start += start
    p.content_end = end + p.content_end

def embed_resources(embed: Optional[bool] = True):
    _params().embed_resources = embed


def __getattr__(name):
    try:
        mod = importlib.import_module(f'lamarkdown.mods.{name}')
    except ModuleNotFoundError as e:
        raise AttributeError(f'No such attribute {name} (no such module)') from e

    try:
        apply_fn = getattr(mod, 'apply')
    except AttributeError as e:
        raise AttributeError(f'No such attribute {name} (missing "apply" function)') from e

    return apply_fn
