from typing import Optional

import clang.cindex
from clang.cindex import Cursor, CursorKind, TypeKind

from wraptor import ModuleBuilder


class CTypesCodeGenerator(object):
    def __init__(self, module_builder: ModuleBuilder):
        self.module_builder = module_builder

    def write_module(self, file):
        module_index = ModuleIndex()
        body_lines = []
        for decl in self.module_builder.declarations():
            if not decl.included():
                continue
            coder = coder_for_cursor_kind[decl.cursor.kind]
            for line in coder(decl.cursor, 0, module_index):
                body_lines.append(line)
        for line in module_index.import_code():
            print(line, file=file)
        for line in body_lines:
            print(line, file=file)


class ModuleIndex(object):
    """
    Tracks needed import statements and declaration dependencies (eventually...)
    """
    def __init__(self):
        self.imports = dict()

    def set_import(self, import_module: str, import_name: str):
        """
        Track import statements needed for the python module we are creating
        """
        if import_module not in self.imports:
            self.imports[import_module] = set()
        self.imports[import_module].add(import_name)

    def import_code(self):
        for module in self.imports:
            yield f"from {module} import {', '.join(self.imports[module])}"


def ctypes_name_for_cursor(cursor: Cursor):
    if cursor.kind == CursorKind.STRUCT_DECL:
        # Workaround for anonymous structs
        if len(cursor.spelling) < 1:
            return cursor.type.spelling
    return cursor.spelling


def ctypes_name_for_clang_type(clang_type: clang.cindex.Type, module_index=None):
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


def field_code(field_cursor: Cursor, indent=8, module_index=None):
    i = indent * " "
    assert field_cursor.kind == CursorKind.FIELD_DECL
    field_name = ctypes_name_for_cursor(field_cursor)
    type_name = ctypes_name_for_clang_type(field_cursor.type, module_index)
    yield i+f'("{field_name}", {type_name}),'  # TODO: more work on types


def index_import(module_index: Optional[ModuleIndex], import_module: str, import_name: str):
    if module_index is None:
        return
    module_index.set_import(import_module, import_name)


def struct_code(cursor: Cursor, indent=0, module_index=None):
    assert cursor.kind == CursorKind.STRUCT_DECL
    i = indent * " "
    name = ctypes_name_for_cursor(cursor)
    yield i+f"class {name}(Structure):"
    index_import(module_index, "ctypes", "Structure")
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


def typedef_code(cursor: Cursor, indent=0, module_index=None):
    i = indent * " "
    name = ctypes_name_for_cursor(cursor)
    base_type = ctypes_name_for_clang_type(cursor.underlying_typedef_type, module_index)
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
