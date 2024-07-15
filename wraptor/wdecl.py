from clang.cindex import Cursor, CursorKind


class WDeclaration(object):
    """Base class for wrapped declarations"""
    def __init__(self, cursor: Cursor, index):
        self.cursor = cursor
        self._index = index
        self._included = False

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained cursor"""
        return getattr(self.cursor, method_name)

    def include(self):
        self._included = True

    def is_included(self):
        return self._included


class WStructDecl(WDeclaration):
    def field(self, field_name) -> WDeclaration:
        assert self.kind == CursorKind.STRUCT_DECL
        for child in self.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                if child.spelling == field_name:
                    return w_decl_for_cursor(child, self._index)
                    # TODO: error on multiple hits
        raise ValueError("no such field")  # TODO: better message


def w_decl_for_cursor(cursor: Cursor, decl_index: dict):
    if cursor.hash in decl_index:
        return decl_index[cursor.hash]
    elif cursor.kind == CursorKind.STRUCT_DECL:
        decl_index[cursor.hash] = WStructDecl(cursor, decl_index)
    else:
        decl_index[cursor.hash] = WDeclaration(cursor, decl_index)
    return decl_index[cursor.hash]
