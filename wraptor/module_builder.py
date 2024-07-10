from clang.cindex import Index, Cursor, CursorKind, TranslationUnit
from .lib import clang_lib_loader  # noqa


def name_for_cursor(cursor: Cursor):
    if cursor.kind == CursorKind.STRUCT_DECL:
        # Workaround for anonymous structs
        if len(cursor.spelling) < 1:
            return cursor.type.spelling
    return cursor.spelling


class CursorWrapper(object):
    """Thin wrapper around a clang cursor with methods to help set wrapping state"""
    def __init__(self, cursor, included_cursors: set):
        self.cursor = cursor
        self.included_cursors = included_cursors

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained cursor"""
        return getattr(self.cursor, method_name)

    def include(self):
        self.included_cursors.add(self.cursor.hash)

    def is_included(self):
        return self.cursor.hash in self.included_cursors


def all_filter(cursor):
    return True


class ModuleBuilder(object):
    def __init__(self, file_paths, compiler_args=None):
        self.included_cursors = set()
        self.translation_units = []
        for file_path in file_paths:
            tu = Index.create().parse(
                path=file_path,
                args=compiler_args,
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
            )
            self.translation_units.append(tu)

    def cursors(self, criteria=all_filter):
        """Top level cursors"""
        for tu in self.translation_units:
            for cursor in filter(criteria, tu.cursor.get_children()):
                yield CursorWrapper(cursor, self.included_cursors)

    def _singleton_cursor(self, criteria) -> CursorWrapper:
        """Query expected to return exactly one cursor"""
        result = None
        for index, cursor in enumerate(self.cursors(criteria)):
            if index == 0:
                result = cursor
            elif index == 1:
                raise RuntimeError("multiple matches")
        if result is None:
            raise RuntimeError("no matches")
        return result

    def struct(self, name: str) -> CursorWrapper:
        return self._singleton_cursor(
            lambda c:
                c.kind == CursorKind.STRUCT_DECL
                and name_for_cursor(c) == name
        )

    def typedef(self, name: str):
        return self._singleton_cursor(
            lambda c:
                c.kind == CursorKind.TYPEDEF_DECL
                and name_for_cursor(c) == name
        )


__all__ = [
    "ModuleBuilder",
]

if __name__ == "__main__":
    mb = ModuleBuilder(
        file_paths=["C:/Users/cmbruns/Documents/git/libjpeg-turbo/jpeglib.h"],
    )
    jpeg_compress_struct = mb.class_("jpeg_compress_struct")
    jpeg_compress_struct.include()
