from clang.cindex import Cursor


class Declaration(object):
    def __init__(self, cursor: Cursor):
        self.cursor = cursor
        self.name = cursor.spelling
        self._include = False

    def include(self):
        self._include = True
        # TODO: include children and parents recursively (but not siblings)

    def included(self) -> bool:
        return self._include
