from clang.cindex import Cursor, CursorKind

from wraptor.decl.declaration import Declaration
from wraptor.decl.struct_field import StructFieldDeclaration


class StructDeclaration(Declaration):
    def __init__(self, cursor: Cursor):
        super().__init__(cursor)
        assert cursor.kind == CursorKind.STRUCT_DECL
        if len(self.name) < 1:
            self.name = cursor.type.spelling
        self.fields = []
        for child in cursor.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                self.fields.append(StructFieldDeclaration(child))
            elif child.kind == CursorKind.STRUCT_DECL:
                pass  # structure contains a field that is a structure or structure pointer
            elif child.kind == CursorKind.UNION_DECL:
                pass  # structure contains a field that is a union
            else:
                assert False
