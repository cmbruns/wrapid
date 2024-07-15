from clang.cindex import Cursor, CursorKind


class WDeclaration(object):
    """Base class for wrapped declarations"""
    def __init__(self, cursor: Cursor):
        self.cursor = cursor
        self._included = False

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained cursor"""
        return getattr(self.cursor, method_name)

    def include(self):
        self._included = True

    def is_included(self):
        return self._included


class WStructDecl(WDeclaration):
    pass


def w_decl_for_cursor(cursor: Cursor, decl_index: dict):
    if cursor.hash in decl_index:
        return decl_index[cursor.hash]
    elif cursor.kind == CursorKind.STRUCT_DECL:
        decl_index[cursor.hash] = WStructDecl(cursor)
    else:
        decl_index[cursor.hash] = WDeclaration(cursor)
    return decl_index[cursor.hash]
