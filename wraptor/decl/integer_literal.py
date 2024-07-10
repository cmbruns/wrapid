from clang.cindex import Cursor, CursorKind, TokenKind

from wraptor.decl.declaration import Declaration
from wraptor.decl.struct_field import StructFieldDeclaration


class IntegerLiteralDeclaration(Declaration):
    def __init__(self, cursor: Cursor):
        super().__init__(cursor)
        assert cursor.kind == CursorKind.INTEGER_LITERAL
        tokens = list(cursor.get_tokens())
        assert tokens[0].kind == TokenKind.LITERAL
        self.value = tokens[0].spelling
        for child in cursor.get_children():
                assert False
