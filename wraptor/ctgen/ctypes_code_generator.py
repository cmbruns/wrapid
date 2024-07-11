from typing import Optional

from clang.cindex import Type as ClangType
from clang.cindex import (
    Cursor,
    CursorKind,
    SourceLocation,
    SourceRange,
    TokenKind,
    TypeKind,
)

from wraptor import ModuleBuilder
from wraptor.module_builder import name_for_cursor


class CTypesCodeGenerator(object):
    def __init__(self, module_builder: ModuleBuilder):
        self.module_builder = module_builder

    def write_module(self, file):
        module_index = ModuleIndex()
        body_lines = []
        for cursor in self.module_builder.cursors():
            if not cursor.is_included():
                continue
            coder = coder_for_cursor_kind[cursor.kind]
            for line in coder(cursor, 0, module_index):
                body_lines.append(line)
        # import statements
        for line in module_index.import_code():
            print(line, file=file)
        # main body of code
        for line in body_lines:
            print(line, file=file)
        # __all__ stanza
        for line in module_index.all_section_code():
            print(line, file=file)


class ModuleIndex(object):
    """
    Tracks needed import statements and declaration dependencies (eventually...)
    """
    def __init__(self):
        self.imports = dict()
        self.all_section_cursors = set()

    def add_all_cursor(self, cursor):
        self.all_section_cursors.add(cursor)

    def set_import(self, import_module: str, import_name: str):
        """
        Track import statements needed for the python module we are creating
        """
        if import_module not in self.imports:
            self.imports[import_module] = set()
        self.imports[import_module].add(import_name)

    def import_code(self):
        if not self.imports:
            return
        for module in self.imports:
            yield f"from {module} import {', '.join(self.imports[module])}"

    def all_section_code(self):
        if not self.all_section_cursors:
            return
        yield ""
        yield "__all__ = ["
        for cursor in self.all_section_cursors:
            yield f'    "{name_for_cursor(cursor)}",'
        yield "]"
        yield ""


def ctypes_name_for_clang_type(clang_type: ClangType, module_index=None):
    """
    Recursive function to build up complex type names piece by piece
    """
    # TODO: maybe replace wraptor type_for_clang_type
    if clang_type.kind in primitive_ctype_for_clang_type:
        t = primitive_ctype_for_clang_type[clang_type.kind]
        index_import(module_index, "ctypes", t)
        return t
    if clang_type.kind == TypeKind.CONSTANTARRAY:
        element_type = ctypes_name_for_clang_type(clang_type.element_type, module_index)
        # TODO: element_count may or may not be a constant macro
        return f"{element_type} * {clang_type.element_count}"
    elif clang_type.kind == TypeKind.ELABORATED:
        return ctypes_name_for_clang_type(clang_type.get_declaration().type, module_index)
    elif clang_type.kind == TypeKind.FUNCTIONPROTO:
        result_type = ctypes_name_for_clang_type(clang_type.get_result(), module_index)
        arg_types = [ctypes_name_for_clang_type(a, module_index) for a in clang_type.argument_types()]
        index_import(module_index, "ctypes", "CFUNCTYPE")
        return f"CFUNCTYPE({result_type}, {', '.join(arg_types)})"
    elif clang_type.kind == TypeKind.POINTER:
        pointee = clang_type.get_pointee()
        if pointee.kind in [TypeKind.CHAR_S, TypeKind.SCHAR]:
            t = "c_char_p"
            index_import(module_index, "ctypes", t)
            return t
        elif pointee.kind == TypeKind.WCHAR:
            t = "c_wchar_p"
            index_import(module_index, "ctypes", t)
            return t
        elif pointee.kind == TypeKind.VOID:
            t = "c_void_p"
            index_import(module_index, "ctypes", t)
            return t
        else:
            index_import(module_index, "ctypes", "POINTER")
            return f"POINTER({ctypes_name_for_clang_type(pointee, module_index)})"
    else:
        return clang_type.spelling


def _py_comment_from_c_comment(c_comment: str):
    c = c_comment
    c = c.strip()  # whitespace
    c = c.strip("/")  # "//" or half of "/* */" comment delimiter
    c = c.strip("*")  # other half of "/* */" comment delimiter
    c = c.strip()  # whitespace again
    return f"# {c}"  # TODO: assumes one-line comment


def right_comment(cursor) -> str:
    """
    Find end-of-line comment on the same line as the declaration.
    :param cursor: ctypes Cursor object representing the declaration.
    :return: either the empty string, or a two-space padded python comment
    """
    tu = cursor.translation_unit
    loc_end = cursor.extent.end
    line = loc_end.line
    file = loc_end.file
    column = loc_end.column
    start = SourceLocation.from_position(tu, file, line, column)
    end = SourceLocation.from_position(tu, file, line + 1, 1)
    extent = SourceRange.from_locations(start, end)
    comment = ""
    for token in tu.get_tokens(extent=extent):
        if token.kind == TokenKind.COMMENT and token.location.line == line:
            comment = f"  {_py_comment_from_c_comment(token.spelling)}"
            break
    return comment


def field_code(cursor: Cursor, indent=8, module_index=None):
    i = indent * " "
    assert cursor.kind == CursorKind.FIELD_DECL
    field_name = name_for_cursor(cursor)
    type_name = ctypes_name_for_clang_type(cursor.type, module_index)
    r_comment = right_comment(cursor)
    yield i+f'("{field_name}", {type_name}),{r_comment}'


def add_to_all(module_index: Optional[ModuleIndex], cursor: Cursor):
    if module_index is None:
        return
    module_index.add_all_cursor(cursor)


def index_import(module_index: Optional[ModuleIndex], import_module: str, import_name: str):
    if module_index is None:
        return
    module_index.set_import(import_module, import_name)


def struct_code(cursor: Cursor, indent=0, module_index=None):
    assert cursor.kind == CursorKind.STRUCT_DECL
    i = indent * " "
    name = name_for_cursor(cursor)
    yield ""
    yield i+f"class {name}(Structure):"
    index_import(module_index, "ctypes", "Structure")
    add_to_all(module_index, cursor)
    fields = []
    for child in cursor.get_children():
        if child.kind == CursorKind.FIELD_DECL:
            fields.append(child)
    if len(fields) > 0:
        yield i+f"    _fields_ = ("
        for field in fields:
            yield from field_code(field, indent + 8, module_index)
        yield i + f"    )"
    else:
        yield i+"    pass"
    yield ""


def typedef_code(cursor: Cursor, indent=0, module_index=None):
    i = indent * " "
    name = name_for_cursor(cursor)
    base_type = ctypes_name_for_clang_type(cursor.underlying_typedef_type, module_index)
    add_to_all(module_index, cursor)
    yield ""
    yield i+f"{name} = {base_type}"


coder_for_cursor_kind = {
    CursorKind.STRUCT_DECL: struct_code,
    CursorKind.TYPEDEF_DECL: typedef_code,
}

primitive_ctype_for_clang_type = {
    TypeKind.BOOL: "c_bool",
    TypeKind.CHAR_S: "c_char",
    TypeKind.CHAR_U: "c_ubyte",
    TypeKind.DOUBLE: "c_double",
    TypeKind.FLOAT: "c_float",
    TypeKind.INT: "c_int",
    TypeKind.LONG: "c_long",
    TypeKind.LONGDOUBLE: "c_longdouble",
    TypeKind.LONGLONG: "c_longlong",
    TypeKind.SCHAR: "c_char",
    TypeKind.SHORT: "c_short",
    TypeKind.UCHAR: "c_ubyte",
    TypeKind.UINT: "c_uint",
    TypeKind.ULONG: "c_ulong",
    TypeKind.ULONGLONG: "c_ulonglong",
    TypeKind.USHORT: "c_ushort",
    TypeKind.WCHAR: "c_wchar",
}

__all__ = [
    "CTypesCodeGenerator",
]
