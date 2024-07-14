from typing import Iterator

from clang.cindex import Index, Cursor, CursorKind, TranslationUnit, TokenKind
from wraptor.lib import clang_lib_loader  # noqa


def all_filter(_cursor):
    return True


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


class CursorGeneratorWrapper(object):
    """Thin wrapper around a clang cursor generator with methods to help set wrapping state"""
    def __init__(self, generator):
        self.generator = generator

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained cursor"""
        return getattr(self.generator, method_name)

    def include(self):
        for cursor_wrapper in self.generator:
            cursor_wrapper.include()


class ModuleBuilder(object):
    def __init__(self, path, compiler_args=None, unsaved_files=None):
        self.included_cursors = set()
        self.comment_index = dict()
        self.translation_units = []
        for file_path in [path, ]:
            tu = Index.create().parse(
                path=file_path,
                args=compiler_args,
                unsaved_files=unsaved_files,
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
                | TranslationUnit.PARSE_INCLUDE_BRIEF_COMMENTS_IN_CODE_COMPLETION,
            )
            self.translation_units.append(tu)
            # Store the comments for later alignment to the cursors
            ctu = self.comment_index.setdefault(tu, dict())
            # first pass - count all the tokens at each line, for later use by comment processing
            token_start_counts = dict()
            for token in tu.cursor.get_tokens():
                file_name = token.location.file.name
                start_line = token.extent.start.line
                token_start_counts.setdefault(file_name, dict()).setdefault(start_line, 0)
                token_start_counts[file_name][start_line] += 1
            # second pass - just look at the comments
            for token in tu.cursor.get_tokens():
                if token.kind == TokenKind.COMMENT:
                    file_name = token.location.file.name
                    end_line = token.extent.end.line
                    starts = ctu.setdefault(file_name, dict()).setdefault("start_line", dict())
                    ends = ctu[file_name].setdefault("end_line", dict())
                    start_line = token.extent.start.line
                    starts.setdefault(start_line, list()).append(token)
                    # Only store ends for comments that are the only token on their start line
                    # (otherwise the comment probably does not belong to the declaration below it)
                    if token_start_counts[file_name][start_line] == 1:
                        ends.setdefault(end_line, list()).append(token)

    def cursors(self, criteria=all_filter) -> Iterator[CursorWrapper]:
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
                and c.is_definition()
        )

    def structs(self, criteria=all_filter):
        generator = filter(
            lambda c:
                c.kind == CursorKind.STRUCT_DECL
                and criteria(c)
                and c.is_definition(),
            self.cursors()
        )
        return CursorGeneratorWrapper(generator)

    def typedef(self, name: str):
        return self._singleton_cursor(
            lambda c:
                c.kind == CursorKind.TYPEDEF_DECL
                and name_for_cursor(c) == name
        )

    def typedefs(self, criteria=all_filter):
        generator = filter(lambda c: c.kind == CursorKind.TYPEDEF_DECL and criteria(c), self.cursors())
        return CursorGeneratorWrapper(generator)


__all__ = [
    "CursorWrapper",
    "ModuleBuilder",
    "name_for_cursor",
]

if __name__ == "__main__":
    mb = ModuleBuilder(
        file_paths=["C:/Users/cmbruns/Documents/git/libjpeg-turbo/jpeglib.h"],
    )
    jpeg_compress_struct = mb.struct("jpeg_compress_struct")
    jpeg_compress_struct.include()
