from clang.cindex import CursorKind, Index, TranslationUnit, TypeKind

import wraptor.decl.clang_lib_loader  # noqa
from wraptor.decl.declaration import Declaration
from wraptor.decl.struct import StructDeclaration
from wraptor.decl.typedef import TypeDefDeclaration


class TranslationUnitDeclaration(Declaration):
    def __init__(self, file_path, compiler_args):
        tu = Index.create().parse(
            path=file_path,
            args=compiler_args,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )
        cursor = tu.cursor
        super().__init__(cursor)
        self._declarations = []
        # Only store declarations from this file
        file_name = str(cursor.spelling)
        for child in cursor.get_children():
            if not str(child.location.file) == file_name:
                continue  # Don't leave this file
            if child.kind == CursorKind.STRUCT_DECL:
                self._declarations.append(StructDeclaration(child))
            elif child.kind == CursorKind.TYPEDEF_DECL:
                self._declarations.append(TypeDefDeclaration(child))
            # TODO: other declarations

    @property
    def declarations(self):
        for decl in self._declarations:
            yield decl

    @property
    def structs(self):
        for decl in self._declarations:
            if decl.cursor.kind == CursorKind.STRUCT_DECL:
                yield decl

    @property
    def typedefs(self):
        for decl in self._declarations:
            if decl.cursor.kind == CursorKind.TYPEDEF_DECL:
                yield decl
