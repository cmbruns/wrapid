from clang.cindex import Index, TranslationUnit, TokenKind

from wraptor.decl import RootDeclGroup, TranslationUnitIterable, WrappedDeclIndex
from wraptor.lib import clang_lib_loader  # noqa


class ModuleBuilder(object):
    def __init__(self, path, compiler_args=None, unsaved_files=None):
        self.comment_index = dict()
        self.translation_unit = Index.create().parse(
            path=path,
            args=compiler_args,
            unsaved_files=unsaved_files,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            | TranslationUnit.PARSE_INCLUDE_BRIEF_COMMENTS_IN_CODE_COMPLETION,
        )
        self.wrapper_index = WrappedDeclIndex()
        # Store root cursor generator for later method delegation
        self.cursor_generator = RootDeclGroup(
            cursors=TranslationUnitIterable(self.translation_unit, self.wrapper_index),
            wrapper_index=self.wrapper_index,
        )
        # Store the comments for later alignment to the cursors
        ctu = self.comment_index.setdefault(self.translation_unit, dict())
        # first pass - count all the tokens at each line, for later use by comment processing
        token_start_counts = dict()
        for token in self.translation_unit.cursor.get_tokens():
            file_name = token.location.file.name
            start_line = token.extent.start.line
            token_start_counts.setdefault(file_name, dict()).setdefault(start_line, 0)
            token_start_counts[file_name][start_line] += 1
        # second pass - just look at the comments
        for token in self.translation_unit.cursor.get_tokens():
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

    def __getattr__(self, method_name):
        """Delegate unknown methods to contained CursorGeneratorWrapper"""
        return getattr(self.cursor_generator, method_name)


__all__ = [
    "ModuleBuilder",
]

if __name__ == "__main__":
    mb = ModuleBuilder(
        path="C:/Users/cmbruns/Documents/git/libjpeg-turbo/jpeglib.h",
    )
    jpeg_compress_struct = mb.struct("jpeg_compress_struct")
    jpeg_compress_struct.include()
