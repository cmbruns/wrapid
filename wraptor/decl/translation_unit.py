from clang.cindex import CursorKind, Index, TranslationUnit, TypeKind

import wraptor.decl.clang_lib_loader  # noqa
from wraptor.decl.declaration import Declaration
from wraptor.decl.struct import StructDeclaration


class TranslationUnitDeclaration(Declaration):
    def __init__(self, file_path, compiler_args):
        tu = Index.create().parse(
            path=file_path,
            args=compiler_args,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )
        cursor = tu.cursor
        super().__init__(cursor)
        self.structs = []
        # Only store declarations from this file
        file_name = str(cursor.spelling)
        for child in cursor.get_children():
            if not str(child.location.file) == file_name:
                continue  # Don't leave this file
            if child.kind == CursorKind.STRUCT_DECL:
                self.structs.append(StructDeclaration(child))
            elif child.kind == CursorKind.TYPEDEF_DECL:
                utt = child.underlying_typedef_type
                if utt.kind == TypeKind.ELABORATED:
                    x = 3
            # TODO: other declaration

    def declarations(self):
        for decl in self.structs:
            yield decl
