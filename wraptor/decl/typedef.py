from clang.cindex import Cursor, CursorKind, TypeKind

from wraptor.decl.declaration import Declaration
from wraptor.decl.types import type_for_clang_type


class TypeDefDeclaration(Declaration):
    def __init__(self, cursor: Cursor):
        super().__init__(cursor)
        assert cursor.kind == CursorKind.TYPEDEF_DECL
        self.base_type = type_for_clang_type(cursor.underlying_typedef_type)
