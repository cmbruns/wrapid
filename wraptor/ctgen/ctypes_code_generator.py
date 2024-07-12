import inspect
from typing import Optional

from clang.cindex import Type as ClangType
from clang.cindex import (
    Cursor,
    CursorKind,
    Token,
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
        module_index.comment_index = self.module_builder.comment_index
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
        all_items = sorted([name_for_cursor(c) for c in self.all_section_cursors])
        for item in all_items:
            yield f'    "{item}",'
        yield "]"
        yield ""


def above_comment(cursor, indent: int, module_index) -> str:
    """
    Find comments directly above a declaration in the source file.
    :param cursor: ctypes Cursor object representing the declaration.
    :param indent: number of spaces cursor is indented in the output
    :param module_index: ModuleIndex object containing ancillary parsing information.
    :return: either the empty string, or a python comment string
    """
    if module_index is None:
        return
    tu_ix = module_index.comment_index.get(cursor.translation_unit, None)
    if tu_ix is None:
        return
    loc_start = cursor.extent.start
    file_ix = tu_ix.get(loc_start.file.name, None)
    if file_ix is None:
        return
    # Above comment must end on the line before the cursor begins.
    line_ix = file_ix["end_line"].get(loc_start.line - 1, None)
    if line_ix is None:
        return
    assert len(line_ix) == 1
    token = line_ix[0]
    comment = _py_comment_from_token(token)
    i = " " * indent
    for line in comment.splitlines():
        yield i + line


def add_to_all(module_index: Optional[ModuleIndex], cursor: Cursor):
    if module_index is None:
        return
    module_index.add_all_cursor(cursor)


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
        elif pointee.kind == TypeKind.FUNCTIONPROTO:
            result_type = ctypes_name_for_clang_type(pointee.get_result(), module_index)
            arg_types = [ctypes_name_for_clang_type(a, module_index) for a in pointee.argument_types()]
            index_import(module_index, "ctypes", "CFUNCTYPE")
            return f"CFUNCTYPE({result_type}, {', '.join(arg_types)})"
        elif pointee.kind == TypeKind.VOID:
            t = "c_void_p"
            index_import(module_index, "ctypes", t)
            return t
        elif pointee.kind == TypeKind.WCHAR:
            t = "c_wchar_p"
            index_import(module_index, "ctypes", t)
            return t
        else:
            index_import(module_index, "ctypes", "POINTER")
            return f"POINTER({ctypes_name_for_clang_type(pointee, module_index)})"
    else:
        return clang_type.spelling


def field_code(cursor: Cursor, indent=8, module_index=None):
    i = indent * " "
    assert cursor.kind == CursorKind.FIELD_DECL
    field_name = name_for_cursor(cursor)
    type_name = ctypes_name_for_clang_type(cursor.type, module_index)
    yield from above_comment(cursor, indent, module_index)
    r_comment = right_comment(cursor, module_index)
    yield i+f'("{field_name}", {type_name}),{r_comment}'


def index_import(module_index: Optional[ModuleIndex], import_module: str, import_name: str):
    if module_index is None:
        return
    module_index.set_import(import_module, import_name)


def _py_comment_from_token(token: Token):
    assert token.kind == TokenKind.COMMENT
    column = token.location.column
    c = token.spelling
    is_star_comment = False
    if c.startswith("/*"):
        is_star_comment = True
        c = c.removeprefix("/*")
        c = c.removesuffix("*/")
    elif c.startswith("//"):
        c = c.removeprefix("//")
    # Pad first line so multiple lines align
    pad = " " * (column - 1)
    c = pad + c
    lines = []
    for index, line in enumerate(c.splitlines()):
        if is_star_comment and index > 0:
            if line.startswith(pad + " *"):
                line = pad + "  " + line.removeprefix(pad + " *")
        lines.append(line)
    # Remove whitespace in a multiline-aware way
    comment = inspect.cleandoc("\n".join(lines))
    # Insert python comment character
    comment = "\n".join([f"# {c}" for c in comment.splitlines()])
    return comment


def right_comment(cursor, module_index) -> str:
    """
    Find end-of-line comment on the same line as the declaration.
    :param cursor: ctypes Cursor object representing the declaration.
    :return: either the empty string, or a two-space padded python comment
    """
    if module_index is None:
        return ""
    tu_ix = module_index.comment_index.get(cursor.translation_unit, None)
    if tu_ix is None:
        return ""
    loc_end = cursor.extent.end
    file_ix = tu_ix.get(loc_end.file.name, None)
    if file_ix is None:
        return ""
    # Right comment must end on the same line as the cursor ends.
    line_ix = file_ix["start_line"].get(loc_end.line, None)
    if line_ix is None:
        return ""
    assert len(line_ix) == 1
    token = line_ix[0]
    comment = f"  {_py_comment_from_token(token)}"
    return comment


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
    if name == base_type:
        return  # Tautology typedefs need not apply
    add_to_all(module_index, cursor)
    yield ""
    yield from above_comment(cursor, indent, module_index)
    r_comment = right_comment(cursor, module_index)
    yield i+f"{name} = {base_type}{r_comment}"


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
