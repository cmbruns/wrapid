from collections import deque
from collections.abc import Iterable, Callable
from typing import Iterator

from clang.cindex import CursorKind, Cursor, TranslationUnit


class WrappedDeclIndex(object):
    def __init__(self):
        self._index: dict[int, DeclWrapper] = dict()

    def __contains__(self, cursor: Cursor) -> bool:
        return self._cursor_key(cursor) in self._index

    @staticmethod
    def _cursor_key(cursor: Cursor):
        # TODO: cursor.hash is not a perfect key because collisions
        return cursor.hash

    def get(self, cursor: Cursor) -> "DeclWrapper":
        if cursor.kind == CursorKind.STRUCT_DECL:
            return self._index.setdefault(self._cursor_key(cursor), StructWrapper(cursor, self))
        else:
            return self._index.setdefault(self._cursor_key(cursor), DeclWrapper(cursor, self))


class DeclWrapper(object):
    """
    Base class for wrapped declarations.

    This class contains configuration that could be applied to all declarations.
    """
    def __init__(self, cursor: Cursor, index: WrappedDeclIndex) -> None:
        self._cursor = cursor
        self._index = index
        self._included = False

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained cursor"""
        return getattr(self._cursor, method_name)

    def __hash__(self) -> int:
        return self._cursor.hash

    def include(self) -> None:
        """Expose this declaration"""
        self._included = True

    def is_included(self):
        """:return: Whether this declaration is exposed."""
        return self._included

    def __str__(self) -> str:
        return f"{self._cursor.spelling}"


Predicate = [Callable[[DeclWrapper], bool]]


def everything_predicate(_cursor: DeclWrapper) -> bool:
    return True


class TranslationUnitIterable(object):
    """
    Iterable object over the declarations related to a clang.cindex.TranslationUnit
    including declarations found outside the translation unit.
    """
    def __init__(self, translation_unit: TranslationUnit, wrapper_index: WrappedDeclIndex) -> None:
        self.parent_cursor: Cursor = translation_unit.cursor
        self.wrapper_index = wrapper_index

    def __iter__(self) -> Iterator[DeclWrapper]:
        # all the macro definitions arrive at once, before everything else.
        # so reserve the ones for the current file until the other stuff has arrived.
        # TODO: also distribute comments here or in __init__
        # TODO: also do something clever with MACRO_INSTANTIATIONs
        macro_deque = deque()
        for cursor in self.parent_cursor.get_children():
            # For now, just realign the declarations in the main source file
            if str(cursor.location.file) == self.parent_cursor.spelling:
                if cursor.kind == CursorKind.MACRO_INSTANTIATION:
                    pass  # Let these also-early declarations go through for now, because laziness
                elif cursor.kind == CursorKind.MACRO_DEFINITION:
                    macro_deque.append(cursor)  # postpone traversal of these macros
                    continue
                else:
                    # Drain macros that occur before this cursor in the file
                    while len(macro_deque) > 0 and macro_deque[0].location.line < cursor.location.line:
                        yield self.wrapper_index.get(macro_deque.popleft())
            yield self.wrapper_index.get(cursor)
        # Drain remaining macros
        while len(macro_deque) > 0:
            yield self.wrapper_index.get(macro_deque.popleft())


class StructWrapper(DeclWrapper):
    def field(self, field_name) -> DeclWrapper:
        assert self.kind == CursorKind.STRUCT_DECL
        for child in self.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                if child.spelling == field_name:
                    return self._index.get(child)
                    # TODO: error on multiple hits
        raise ValueError("no such field")  # TODO: better message


class BaseDeclGroup(Iterable[DeclWrapper]):
    """
    Base class for declaration generators.

    This class contains configuration that could be applied to all declaration generators.
    """

    def __init__(
            self,
            cursors: Iterable[DeclWrapper],
            wrapper_index: WrappedDeclIndex,
            predicate: Predicate = everything_predicate,
    ) -> None:
        iter(cursors)  # No exception? it's OK we want an iterABLE
        try:
            next(cursors)
            assert False  # but we don't want an iteratOR
        except TypeError:
            pass  # OK, not an iteratOR
        self._cursors: Iterable[DeclWrapper] = cursors
        self._wrapper_index: WrappedDeclIndex = wrapper_index
        self._predicate: Predicate = predicate

    def __iter__(self) -> Iterator[DeclWrapper]:
        for cursor in self._cursors:
            if not self._predicate(cursor):
                continue
            yield cursor

    def in_header(self, path: str) -> "BaseDeclGroup":
        """
        Select only those declarations found in a particular source file.
        :param path: The path to a source code file
        :return: An iterable over the declarations in this group found in a particular source file
        """
        return type(self)(
            cursors=self,
            wrapper_index=self._wrapper_index,
            predicate=lambda c: str(c.location.file) == str(path),
        )

    def included(self, predicate: Predicate = everything_predicate) -> Iterable[DeclWrapper]:
        """Select declarations that have been marked to be exposed."""
        return type(self)(
            self,
            self._wrapper_index,
            lambda c:
                c in self._wrapper_index
                and self._wrapper_index.get(c).is_included(),
        )

    def include(self) -> None:
        """
        Expose all the cursors in this group
        :return: None
        """
        for cursor in self:
            self._wrapper_index.get(cursor).include()

    def _select_single_declaration(self, predicate: Predicate) -> DeclWrapper:
        """Query expected to return exactly one cursor"""
        result = None
        for index, decl in enumerate(filter(predicate, self)):
            if index == 0:
                result = decl
            else:
                raise RuntimeError("multiple matches")  # TODO: better error
        if result is None:
            raise RuntimeError("no matches")  # TODO: better error
        return decl


class RootDeclGroup(BaseDeclGroup):
    """Declaration generator for top level declarations"""

    def enums(self, predicate: Predicate = everything_predicate) -> "BaseDeclGroup":
        return BaseDeclGroup(
            self,
            self._wrapper_index,
            lambda c: c.kind == CursorKind.ENUM_DECL and predicate(c),
        )

    def macros(self, predicate: Predicate = everything_predicate) -> "BaseDeclGroup":
        return BaseDeclGroup(
            self,
            self._wrapper_index,
            lambda c: c.kind == CursorKind.MACRO_DEFINITION and predicate(c),
        )

    def struct(self, name: str) -> DeclWrapper:
        """
        Query one particular struct declaration by name.
        :param name: The name of the struct declaration
        :return: A struct declaration.
        """
        return self.structs()._select_single_declaration(
            lambda c:
                c.spelling == name
                and c.is_definition()
        )

    def structs(self, predicate: Predicate = everything_predicate):
        """
        Select only Struct declarations
        :param predicate: optional filter to further restrict which declarations to select
        :return: An iterable over the selected Struct declarations in this group
        """
        return BaseDeclGroup(
            self,
            self._wrapper_index,
            lambda c: c.kind == CursorKind.STRUCT_DECL and predicate(c),
        )

    def typedef(self, name: str) -> DeclWrapper:
        """
        Query one particular TypeDef declaration by name.
        :param name: The name of the TypeDef declaration
        :return: A TypeDef declaration.
        """
        return self.typedefs()._select_single_declaration(lambda c: c.spelling == name)

    def typedefs(self, predicate: Predicate = everything_predicate) -> BaseDeclGroup:
        """
        Select only TypeDef declarations
        :param predicate: optional filter to further restrict which declarations to select
        :return: An iterable over the selected TypeDef declarations in this group
        """
        return BaseDeclGroup(
            self,
            self._wrapper_index,
            lambda c: c.kind == CursorKind.TYPEDEF_DECL and predicate(c),
        )


def name_for_cursor(cursor: Cursor):
    if cursor.kind == CursorKind.STRUCT_DECL:
        # Workaround for anonymous structs
        if len(cursor.spelling) < 1:
            return cursor.type.spelling
    return cursor.spelling


