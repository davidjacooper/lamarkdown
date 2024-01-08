'''
# Build File API

The functions here are to be used by build files and extensions.
'''

from .build_params import BuildParams, ExtendableValue, LateValue, Rule, Variant
from .resources import ContentResourceSpec, UrlResourceSpec
from . import fenced_blocks

from markdown.extensions import Extension
from lxml.cssselect import CSSSelector
from lxml.html import HtmlElement

import importlib
import os.path
from typing import *
from types import ModuleType


class BuildParamsException(Exception): pass

ValueFactory = Callable[[Set[str]],Optional[str]]
ResourceArg = Union[str,ValueFactory]
Condition = Union[str,Iterable[str]]
ResourceInfo = Tuple[List[str],ValueFactory]


def _callable(fn, which = 'argument'):
    if not callable(fn):
        raise ValueError(f'{which} expected to be a function/callable, but was {type(fn).__name__} (value {fn})')


def _res_values(value: ResourceArg,
                if_xpaths:    Condition = [],
                if_selectors: Condition = []) -> ResourceInfo:

    value_factory: ValueFactory

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

    xpaths: List[str] = []
    xpaths.extend(xpath_iterable)
    xpaths.extend(CSSSelector(sel).path for sel in selector_iterable)

    return (xpaths, value_factory)


def _url_resources(url_list: Iterable[str],
                   tag: str,
                   embed: Optional[bool] = None,
                   hash_type: Optional[str] = None,
                   mime_type: Optional[str] = None,
                   **kwargs):

    p = BuildParams.current
    assert p is not None

    for url in url_list:
        (xpaths_required, url_factory) = _res_values(url, **kwargs)

        if embed is None:
            if mime_type is None:
                embed_fn = lambda: p.embed_rule(url = url, tag = tag, attr = {})
            else:
                embed_fn = lambda: p.embed_rule(url = url, tag = tag, attr = {}, type = mime_type)
        else:
            embed_fn = lambda: embed

        if hash_type is None:
            if mime_type is None:
                hash_type_fn = lambda: p.resource_hash_rule(url = url, tag = tag, attr = {})
            else:
                hash_type_fn = lambda: p.resource_hash_rule(url = url, tag = tag, attr = {},
                                                            type = mime_type)
        else:
            hash_type_fn = lambda: hash_type


        yield UrlResourceSpec(
            xpaths_required = xpaths_required,
            url_factory  = url_factory,
            base_url     = p.resource_base_url,
            cache        = p.fetch_cache,
            embed_fn     = embed_fn,
            hash_type_fn = hash_type_fn)


def params():
    return BuildParams.current


def check_build_params(getter):
    '''
    @check_build_params decorates getter methods, to make them check whether the global BuildParams
    object has been initialised.

    This is important for unit testing, since 'unittest' unittest automatically discovers tests by
    traversing package/module structures, and ApiImpl is a kind of module. But the global
    BuildParams object doesn't exist during unit testing.

    This decorator is also separated out from '@property', because mypy needs '@property' to
    understand what the properties are.
    '''

    def get(self):
        if BuildParams.current is None:
            return NotImplemented
        return getter(self)

    return get


class BuildModuleDispatcher:
    def __getattr__(self, name):
        try:
            mod = importlib.import_module(f'lamarkdown.mods.{name}')
        except ModuleNotFoundError as e:
            raise AttributeError(f'No such build module - {name}')

        try:
            apply_fn = getattr(mod, 'apply')
        except AttributeError as e:
            raise AssertionError(f'No such attribute {name} (missing "apply" function)') from e

        return apply_fn


class ApiImpl(ModuleType):
    _m = BuildModuleDispatcher()

    def __init__(self):
        # See https://docs.python.org/3/library/types.html#types.ModuleType
        super().__init__('lamarkdown')
        self.__all__ = dir(ApiImpl)


    @property
    def m(self):
        return self._m

    def __call__(self, *extensions: Union[str,Extension], **config):
        if len(extensions) == 0:
            raise ValueError('Must supply at least one extension')

        if len(extensions) > 1 and len(config) > 0:
            raise ValueError('Cannot give config values for multiple extensions at the same time')

        p = params()
        ret_config = None

        for e in extensions:
            if isinstance(e, Extension):
                if len(config) > 0:
                    raise ValueError('Cannot give config values to an already-instantiated Extension')

                p.obj_extensions.append(e)
                ret_config = None

            else:
                all_config = p._named_extensions.setdefault(e, {})

                for key, value in config.items():
                    if key in all_config:
                        old_value = all_config[key]
                        if isinstance(old_value, ExtendableValue):
                            # Extend existing value
                            old_value.extend(value)

                        elif isinstance(value, ExtendableValue):
                            # New value is extendable; make existing value extendable and extend it.
                            old_value = self.extendable(old_value, value.join)
                            old_value.extend(value)
                            all_config[key] = old_value

                        else:
                            # Replace one simple value with another
                            all_config[key] = value

                    else:
                        all_config[key] = value

                ret_config = all_config

        return ret_config if len(extensions) == 1 else None


    def extendable(self, value, join = ''):
        return ExtendableValue(value, join)


    def late(self, fn):
        _callable(fn)
        return LateValue(fn)

    @property
    @check_build_params
    def params(self) -> BuildParams:
        return params()


    @property
    @check_build_params
    def build_dir(self) -> str:
        return params().build_dir


    @property
    @check_build_params
    def env(self):
        return params().env


    @property
    @check_build_params
    def name(self) -> str:
        return params().name


    @name.setter
    def name(self, name: str):
        params().name = name


    def target(self, fn: Callable[[str],str]):
        _callable(fn)
        params().output_namer = fn


    def base_name(self):
        params().output_namer = lambda t: t


    @property
    @check_build_params
    def allow_exec(self) -> bool:
        return params().allow_exec


    @allow_exec.setter
    def allow_exec(self, allow: bool):
        params().allow_exec = allow


    def fenced_block(self,
                     name: str,
                     formatter: Callable,
                     validator: Optional[Callable] = None,
                     css_class: Optional[str] = None,
                     cached: bool = True,
                     check_exec: bool = False,
                     set_attr: bool = True):

        _callable(formatter, 'formatter')
        if validator is not None:
            _callable(validator, 'validator')

        if cached:
            formatter = fenced_blocks.caching_formatter(params(), name, formatter)

        if check_exec:
            formatter = fenced_blocks.exec_formatter(params(), name, formatter)

        if set_attr:
            formatter = fenced_blocks.attr_formatter(formatter)

        self('pymdownx.superfences', custom_fences = self.extendable([{
            'name': name,
            'class': css_class if css_class is not None else name,
            'format': formatter,
            **({'validator': validator} if validator is not None else {})
        }]))



    def command_formatter(self, command: List[str]):
        return fenced_blocks.command_formatter(params(), command)


    def variants(self, *args, **kwargs):
        p = params()
        for variant_fn in args:
            _callable(variant_fn)
            p.variants.append(Variant(name = variant_fn.__name__,
                                      build_fn = variant_fn))

        for name, variant_fn in kwargs.items():
            _callable(variant_fn)
            p.variants.append(Variant(name = name, build_fn = variant_fn))


    def prune(self,
              selector: Optional[str] = None,
              xpath: Optional[str] = None):

        if selector is None and xpath is None:
            raise ValueError('Must specify at least one argument')

        hook = lambda elem: elem.getparent().remove(elem)

        if selector is not None:
            self.with_selector(selector, hook)

        if xpath is not None:
            self.with_xpath(xpath, hook)


    def with_selector(self,
                      selector: str,
                      fn: Callable[[HtmlElement],None]):
        self.with_xpath(CSSSelector(selector).path, fn)


    def with_xpath(self,
                   xpath: str,
                   fn: Callable[[HtmlElement],None]):
        _callable(fn)
        def hook(root):
            for element in root.xpath(xpath):
                fn(element)
        self.with_tree(hook)


    def with_tree(self,
                  fn: Callable[[HtmlElement],Optional[HtmlElement]]):
        _callable(fn)
        params().tree_hooks.append(fn)


    def with_html(self,
                  fn: Callable[[str],Optional[str]]):
        _callable(fn)
        params().html_hooks.append(fn)


    def css_rule(self, selectors: Condition, properties: str):
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

        def content_factory(found: Set[str]) -> Optional[str]:
            if not found: return None
            return ', '.join(xpath_to_sel[xp] for xp in sorted(found)) + ' { ' + properties + ' }'

        params().css.append(ContentResourceSpec(xpaths_required = list(xpath_to_sel.keys()),
                                                content_factory = content_factory))


    def css(self, content: ResourceArg, **kwargs):
        (xpaths_required, content_factory) = _res_values(content, **kwargs)
        params().css.append(ContentResourceSpec(xpaths_required = xpaths_required,
                                                content_factory = content_factory))

    @property
    @check_build_params
    def css_vars(self):
        return params().css_vars


    def js(self, content: ResourceArg, **kwargs):
        (xpaths_required, content_factory) = _res_values(content, **kwargs)
        params().js.append(ContentResourceSpec(xpaths_required = xpaths_required,
                                               content_factory = content_factory))


    def css_files(self, *url_list: str, **kwargs):
        params().css.extend(_url_resources(url_list,
                                           tag = 'style',
                                           mime_type = 'text/css',
                                           **kwargs))


    def js_files(self, *url_list: str, **kwargs):
        params().js.extend(_url_resources(url_list,
                                          tag = 'script',
                                          mime_type = 'application/javascript',
                                          **kwargs))

    R = TypeVar('R')
    RuleSpec = Union[R,Rule[R]]

    def embed(self, embed_spec: RuleSpec[bool]):
        p = params()
        if isinstance(embed_spec, bool):
            p.embed_rule = lambda **k: embed_spec

        elif callable(embed_spec):
            p.embed_rule = embed_spec

        else:
            raise ValueError(f'"embed_spec" expected to be a bool, or a fn(str,str,str)->bool, but was {embed_spec.__class__} ({embed_spec}).')


    def resource_hash_type(self, hash_spec: Rule[Optional[str]]):
        p = params()
        if hash_spec in [None, 'sha256', 'sha384', 'sha512']:
            p.resource_hash_rule = lambda **k: hash_spec

        elif callable(hash_spec):
            p.resource_hash_rule = hash_spec

        else:
            raise ValueError(f'"hash_spec" expected to be None, "sha256", "sha384", "sha512", or a fn(str,str,str)->str (returning one of these), but was {hash_spec.__class__} ({hash_spec}).')


    def scale(self, scale_spec: RuleSpec[float]):
        p = params()
        if isinstance(scale_spec, int) or isinstance(scale_spec, float):
            p.scale_rule = lambda **k: float(scale_spec)

        elif callable(scale_spec):
            p.scale_rule = scale_spec

        else:
            raise ValueError(f'"scale_spec" expected to be a number, or a fn(str,str,str)->float, but was {scale_spec.__class__} ({scale_spec}).')

