'''
The 'build parameters' are all the information (apart from the source markdown file) needed to
build a completed HTML document.

This file also maintains a global instance of this state, BuildParams.current, which is accessed by
build modules.
'''

from __future__ import annotations
from .resources import ResourceSpec
from .progress import Progress
from .directives import Directives
from markdown.extensions import Extension
import diskcache  # type: ignore

from copy import copy, deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Protocol, TypeVar


class ResourceError(Exception):
    pass


class LateValue:
    def __init__(self, callback):
        self._callback = callback

    @property
    def value(self):
        return self._callback()


class ExtendableValue:
    def __init__(self, init_part, join = ''):
        self._value_parts = []
        self._join = join
        self.extend(init_part)

    def extend(self, new_part):
        if isinstance(new_part, type(self)):
            # Extend with another extendable
            self._value_parts.extend(new_part._value_parts)
        else:
            self._value_parts.append(new_part)

    @property
    def join(self):
        return self._join

    @property
    def value(self):
        val = self._value_parts[0]
        if isinstance(val, LateValue):
            val = val.value

        val = copy(val)

        for part in self._value_parts[1:]:
            if isinstance(part, LateValue):
                part = part.value

            if isinstance(val, str):
                val += self.join + part

            elif isinstance(val, list):
                val.extend(part)

            elif isinstance(val, dict) or isinstance(val, set):
                val.update(part)

            else:
                raise TypeError('Expected "expandable" value of type str, list, dict or set, but '
                                f'received {type(val)}')

        return val


@dataclass
class Variant:
    name: str
    build_fn: Callable[[], None]

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)


class Environment(dict):
    def __deepcopy__(self, memo):
        new_env = Environment()
        for key, value in self.items():
            try:
                new_env[key] = deepcopy(value, memo)
            except TypeError:
                # Some types (like module) cannot be deep-copied, so we just reuse the reference.
                new_env[key] = value
        return new_env

    def __repr__(self):
        return '...'  # To avoid cluttering error messages too much.

    def repr(self):
        return super().__repr__()


R = TypeVar('R', covariant = True)


class Rule(Protocol[R]):
    def __call__(self, *,
                 url: str | None,
                 mime: str | None,
                 tag: str | None,
                 attr: dict[str, str] | None,
                 **kwargs) -> R:
        ...


# Note: all 'rule' callbacks should accept a '**kwargs' parameter. The actual keyword arguments
# supplied include _some subset_ of: 'url', 'mime' (mime type), 'tag' and 'attr', and possibly
# others in the future.


def default_embed_rule(mime: str | None, tag: str | None, **kwargs) -> bool:
    if tag in ('audio', 'video', 'iframe'):
        return False

    if mime and (mime.startswith('audio/') or mime.startswith('video/')):
        return False

    return True


def default_resource_hash_rule(**kwargs) -> str | None:
    return None


def default_scale_rule(**kwargs) -> float:
    return 1.0


def default_output_namer(target: Path) -> Path:
    return target



@dataclass
class BuildParams:
    current: ClassVar['BuildParams' | None] = None

    # These fields are not intended to be modified once set:
    src_file: Path
    target_file: Path
    build_files: list[Path]
    build_dir: Path
    build_defaults: bool
    build_cache: diskcache.Cache
    fetch_cache: diskcache.Cache
    progress: Progress
    directives: Directives
    is_live: bool
    allow_exec_cmdline: bool

    # These fields *are* modifiable by build modules (or even extensions):
    name:                 str                           = ''
    variant_name_sep:     str                           = '_'
    variants:             list[Variant]                 = field(default_factory=list)
    meta:                 dict[str, str]                = field(default_factory=dict)
    _named_extensions:    dict[str, dict[str, Any]]     = field(default_factory=dict)
    obj_extensions:       list[Extension]               = field(default_factory=list)
    tree_hooks:           list[Callable]                = field(default_factory=list)
    html_hooks:           list[Callable]                = field(default_factory=list)
    font_codepoints:      set[int]                      = field(default_factory=set)
    css_vars:             dict[str, str]                = field(default_factory=dict)
    css:                  list[ResourceSpec]            = field(default_factory=list)
    js:                   list[ResourceSpec]            = field(default_factory=list)
    resource_base_url:    str                           = ''
    embed_rule:           Rule[bool]                    = default_embed_rule
    resource_hash_rule:   Rule[str | None]              = default_resource_hash_rule
    scale_rule:           Rule[float]                   = default_scale_rule
    env:                  dict[str, Any]                = field(default_factory=Environment)
    output_namer:         Callable[[Path], str | Path]  = default_output_namer
    allow_exec:           bool                          = False
    live_update_deps:     set[Path]                     = field(default_factory=set)

    def set_current(self) -> BuildParams | None:
        existing = BuildParams.current
        BuildParams.current = self
        return existing

    # @property
    # def src_base(self) -> Path:
    #     # return self.src_file.rsplit('.', 1)[0]
    #     return self.src_file.with_suffix('')
    #
    # @property
    # def target_base(self) -> Path:
    #     # return self.target_file.rsplit('.', 1)[0]
    #     return self.target_file.with_suffix('')

    @property
    def output_file(self) -> Path:
        return Path(self.output_namer(self.target_file))

    @property
    def resource_xpaths(self) -> set[str]:
        'The set of all XPath expressions specified by all CSS/JS resources.'
        return {xpath
                for res_list in (self.css, self.js)
                for res in res_list
                for xpath in res.xpaths_required}

    @property
    def named_extensions(self):
        configs: dict[str, dict[str, Any]] = {}
        for extension, config in self._named_extensions.items():
            configs[extension] = {}
            for key, value in config.items():
                if isinstance(value, ExtendableValue) or isinstance(value, LateValue):
                    try:
                        # This might invoke callbacks, hence the error checking
                        configs[extension][key] = value.value
                    except Exception as e:
                        self.progress.error(f'{extension}:{key}', exception = e)
                else:
                    configs[extension][key] = value
        return configs
