from clang.cindex import Cursor, CursorKind

from wraptor.decl.declaration import Declaration


class StructFieldDeclaration(Declaration):
    def __init__(self, cursor: Cursor):
        super().__init__(cursor)
        assert cursor.kind == CursorKind.FIELD_DECL
