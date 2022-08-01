from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Generic,
    Optional,
    Iterable,
    Sequence,
    TypeVar,
    Union,
)


ItemType = TypeVar("ItemType")
_MISSING = object()


class Structured(Generic[ItemType]):
    """
    Layers structure onto an arbitrary type.

    Structure can be added in two ways: by keys and by tuples, and can be
    arbitrarily nested. If present, the object assigned to the "root" key is
    treated specially, in that enumeration over the structured instance is
    equivalent to enumeration over the root node if there is no other structure.
    Otherwise, enumeration and key look up is done over the top-level values in
    the container in the order in which they were assigned (except that the root
    node is always first).

    The structure is mutable (new keys can be added, or existing attributes
    overridden) by direct assignment in the usual way; or via the `_update`
    method. To avoid collision with potential keys, all methods and attributes
    are preceded with an underscore. Contrary to Python convention, these are
    still considered public methods.

    Attributes:
        _structure: A dictionary of the keys stored in the `Structured`
            instance.
        _mapped_attrs: A set attribute names which will, when looked up, be
            mapped onto all objects in the `Structured` instance, and return
            a new `Structured` instance with the same structure but all values
            replaced with the result of the attribute on the stored instances.
        _metadata: A dictionary of metadata which can be used to store arbitrary
            information about the `Structured` instance.

    Examples:
        ```
        >>>  s = Structured((1, 2), b=3, c=(4,5)); s
        root:
            [0]:
                1
            [1]:
                2
        .b:
            3
        .c:
            [0]:
                4
            [1]:
                5
        >>> list(s)
        [(1, 2), 3, (4, 5)]
        >>> s.root
        (1, 2)
        >>> s.b
        3
        >>> s._map(lambda x: x+1)
        root:
            [0]:
                2
            [1]:
                3
        .b:
            4
        .c:
            [0]:
                5
            [1]:
                6
        ```
    """

    __slots__ = ("_structure", "_mapped_attrs", "_metadata")

    def __init__(
        self,
        root: Any = _MISSING,
        *,
        _mapped_attrs: Iterable[str] = None,
        _metadata: Dict[str, Any] = None,
        **structure,
    ):
        if any(key.startswith("_") for key in structure):
            raise ValueError(
                "Substructure keys cannot start with an underscore. "
                f"The invalid keys are: {set(key for key in structure if key.startswith('_'))}."
            )
        if root is not _MISSING:
            structure["root"] = self._prepare_item("root", root)
        self._mapped_attrs = set(_mapped_attrs or ())
        self._metadata = _metadata

        self._structure = {
            key: self._prepare_item(key, item) for key, item in structure.items()
        }

    def _prepare_item(self, key: str, item: Any) -> Any:
        return item

    @property
    def _has_root(self) -> bool:
        "Whether this instance of `Structured` has a root node."
        return "root" in self._structure

    @property
    def _has_structure(self) -> bool:
        return set(self._structure) != {"root"}

    def _map(
        self, func: Callable[[ItemType], Any], recurse: bool = True
    ) -> Structured[Any]:
        """
        Map a callable object onto all the structured objects, returning a
        `Structured` instance with identical structure, where the original
        objects are replaced with the output of `func`.

        Args:
            func: The callable to apply to all objects contained in the
                `Structured` instance.
            recurse: Whether to recursively map, or only map one level deep (the
                objects directly referenced by this `StructuredInstance`).
                When `True`, if objects within this structure are `Structured`
                instances also, then the map will be applied only on the leaf
                nodes (otherwise `func` will received `Structured` instances).
                (default: True).

        Returns:
            A `Structured` instance with the same structure as this instance,
            but with all objects transformed under `func`.
        """

        def apply_func(obj):
            if recurse and isinstance(obj, Structured):
                return obj._map(func, recurse=True)
            if isinstance(obj, tuple):
                return tuple(func(o) for o in obj)
            return func(obj)

        return Structured[ItemType](
            **{key: apply_func(obj) for key, obj in self._structure.items()}
        )

    def _to_dict(self, recurse: bool = True) -> Dict[Optional[str], Any]:
        """
        Generate a dictionary representation of this structure.

        Args:
            recurse: Whether to recursively convert any nested `Structured`
                instances into dictionaries also. If `False`, any nested
                `Structured` instances will be surfaced in the generated
                dictionary.

        Returns:
            The dictionary representation of this `Structured` instance.
        """

        def do_recursion(obj):
            if recurse and isinstance(obj, Structured):
                return obj._to_dict()
            return obj

        return {key: do_recursion(value) for key, value in self._structure.items()}

    def _simplify(
        self, *, recurse: bool = True, unwrap: bool = True, inplace: bool = False
    ) -> Union[Any, Structured[ItemType]]:
        """
        Simplify this `Structured` instance by:
            - returning the object stored at the root node if there is no other
                structure (removing as many `Structured` wrappers as satisfy
                this requirement).
            - if `recurse` is `True`, recursively applying the logic above to
                any nested `Structured` instances.

        Args:
            unwrap: Whether to unwrap the root node (returning the raw
                unstructured root value) if there is no other structure.
            recurse: Whether to recurse the simplification into the objects
                associated with the keys of this (and nested) `Structured`
                instances.
            inplace: Whether to simplify the current structure (`True`), or
                return a new object with the simplifications (`False`). Note
                that if `True`, `unwrap` *must* be `False`.
        """
        if inplace and unwrap:
            raise RuntimeError(
                f"Cannot simplify `{self.__class__.__name__}` instances "
                "in-place if `unwrap` is `True`."
            )
        structured = self
        while (
            isinstance(structured, Structured)
            and structured._has_root
            and not structured._has_structure
            and (unwrap or isinstance(structured.root, Structured))
        ):
            structured = structured.root

        if not isinstance(structured, Structured):
            return structured

        structure = structured._structure

        if recurse:
            structure = {
                key: value._simplify(recurse=True)
                if isinstance(value, Structured)
                else value
                for key, value in structured._structure.items()
            }

        if inplace:
            self._structure = structure
            return self
        return self.__class__(
            _mapped_attrs=self._mapped_attrs,
            _metadata=self._metadata,
            **structure,
        )

    def _update(self, root=_MISSING, **structure) -> Structured[ItemType]:
        """
        Return a new `Structured` instance that is identical to this one but
        the root and/or keys replaced with the nominated values.

        Args:
            root: The (optional) replacement of the root node.
            structure: Any additional key/values to update in the structure.
        """
        if root is not _MISSING:
            structure["root"] = root
        return self.__class__(
            **{
                "_mapped_attrs": self._mapped_attrs,
                "_metadata": self._metadata,
                **self._structure,
                **{
                    key: self._prepare_item(key, item)
                    for key, item in structure.items()
                },
            }
        )

    def __dir__(self):
        return super().__dir__() + list(self._structure)

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if attr in self._structure:
            return self._structure[attr]
        if attr in self._mapped_attrs:
            return self._map(lambda x: getattr(x, attr))
        raise AttributeError(
            f"This `{self.__class__.__name__}` instance does not have structure @ `{repr(attr)}`."
        )

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        self._structure[attr] = self._prepare_item(attr, value)

    def __getitem__(self, key):
        if self._has_root and not self._has_structure:
            return self.root[key]
        if key in (None, "root") and self._has_root:
            return self.root
        if isinstance(key, str) and not key.startswith("_") and key in self._structure:
            return self._structure[key]
        raise KeyError(
            f"This `{self.__class__.__name__}` instance does not have structure @ `{repr(key)}`."
        )

    def __setitem__(self, key, value):
        if not isinstance(key, str) or not key.isidentifier():
            raise KeyError(key)
        if key.startswith("_"):
            raise KeyError(
                "Substructure keys cannot start with an underscore. "
                f"The invalid keys are: {set(key for key in self._structure if key.startswith('_'))}."
            )
        self._structure[key] = self._prepare_item(key, value)

    def __iter__(self) -> Generator[Union[ItemType, Structured[ItemType]]]:
        if (
            self._has_root
            and not self._has_structure
            and isinstance(self.root, Sequence)
        ):
            yield from self.root
        elif self._has_root:
            yield self.root
        for key, value in self._structure.items():
            if key != "root":
                yield value

    def __eq__(self, other):
        if isinstance(other, Structured):
            return self._structure == other._structure
        return False

    def __len__(self) -> int:
        return len(self._structure)

    def __str__(self):
        return self.__repr__(to_str=str)

    def __repr__(self, to_str=repr):
        import textwrap

        d = self._to_dict(recurse=False)
        keys = [key for key in d if key != "root"]
        if self._has_root:
            keys.insert(0, "root")

        out = []
        for key in keys:
            if key == "root":
                out.append("root:")
            else:
                out.append(f".{key}:")
            value = d[key]
            if isinstance(value, tuple):
                for i, obj in enumerate(value):
                    out.append(f"    [{i}]:")
                    out.append(textwrap.indent(to_str(obj), "        "))
            else:
                out.append(textwrap.indent(to_str(value), "    "))
        return "\n".join(out)
