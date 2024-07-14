import inspect
from typing import Union, Callable, Iterator

from clang.cindex import (
    Cursor,
    CursorKind,
    Token,
    TokenKind,
    TypeKind,
)

from wraptor import ModuleBuilder
from wraptor.ctgen.types import w_type_for_clang_type, WCTypesType
from wraptor.module_builder import name_for_cursor, CursorWrapper


ICursor = Union[Cursor, CursorWrapper]


class CTypesCodeGenerator(object):
    def __init__(self, module_builder: ModuleBuilder):
        self.module_builder = module_builder
        self.imports = dict()
        self.all_section_cursors = set()
        self.unexposed_dependencies = dict()

    def above_comment(self, cursor, indent: int) -> str:
        """
        Find comments directly above a declaration in the source file.
        :param cursor: ctypes Cursor object representing the declaration.
        :param indent: number of spaces cursor is indented in the output
        :return: either the empty string, or a python comment string
        """
        tu_ix = self.module_builder.comment_index.get(cursor.translation_unit, None)
        if tu_ix is None:
            return
        loc_start = cursor.extent.start
        if loc_start.file is None:
            return
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

    def add_all_cursor(self, cursor):
        self.all_section_cursors.add(cursor)

    def all_section_code(self):
        if not self.all_section_cursors:
            return
        yield ""
        yield "__all__ = ["
        all_items = sorted([name_for_cursor(c) for c in self.all_section_cursors])
        for item in all_items:
            yield f'    "{item}",'
        yield "]"

    def coder_for_cursor_kind(self, cursor_kind: CursorKind) -> Callable[[ICursor, int], Iterator[str]]:
        return {
            CursorKind.STRUCT_DECL: self.struct_code,
            CursorKind.TYPEDEF_DECL: self.typedef_code,
        }[cursor_kind]

    def field_code(self, cursor: Cursor, indent=8):
        i = indent * " "
        assert cursor.kind == CursorKind.FIELD_DECL
        field_name = name_for_cursor(cursor)
        type_name = w_type_for_clang_type(cursor.type, cursor)
        self.load_imports(type_name)
        self.check_dependency(type_name, cursor)
        yield from self.above_comment(cursor, indent)
        yield from self.right_comment(cursor, i + f'("{field_name}", {type_name}),')

    def import_code(self):
        if not self.imports:
            return
        for module in self.imports:
            if len(self.imports[module]) < 5:
                yield f"from {module} import {', '.join(sorted(self.imports[module]))}"
            else:
                yield f"from {module} import ("
                for item in sorted(self.imports[module]):
                    yield f"    {item},"
                yield ")"

    def right_comment(self, cursor: ICursor, non_comment_code: str) -> Iterator[str]:
        """
        Find end-of-line comment on the same line as the declaration.
        :param cursor: ctypes Cursor object representing the declaration.
        :param non_comment_code: Non-comment portion of the generated code line
        :return: code lines with comment attached
        """
        tu_ix = self.module_builder.comment_index.get(cursor.translation_unit, None)
        if tu_ix is None:
            yield non_comment_code
            return  # No comments are indexed for this translation unit
        loc_end = cursor.extent.end
        if loc_end.file is None:
            return
        file_ix = tu_ix.get(loc_end.file.name, None)
        if file_ix is None:
            yield non_comment_code
            return  # No comments are indexed for this source file
        # Right comment must start on the same line as the cursor ends.
        line_ix = file_ix["start_line"].get(loc_end.line, None)
        if line_ix is None:
            yield non_comment_code
            return  # No comments begin on the same source line as this declaration
        assert len(line_ix) == 1  # TODO: what if there are two comments on the line?
        token = line_ix[0]
        comment = _py_comment_from_token(token)
        if comment in ["# ", ""]:
            yield non_comment_code
            return  # comment is empty
        assert comment.startswith("# ")
        # TODO: Indent subsequent lines of comment to line up with the first one.
        lines = comment.splitlines()
        yield f"{non_comment_code}  {lines[0]}"
        # 1) Indentation of the output code fragment
        indent1 = " " * (len(non_comment_code) - len(non_comment_code.lstrip(" ")))
        # 2) Further indentation of the comment section
        indent2 = " " * (len(non_comment_code) - len(indent1) + 3)
        for line in lines[1:]:
            assert line.startswith("# ")
            line = line.removeprefix("# ")
            yield f"{indent1}#{indent2}{line}"

    def load_imports(self, wtype: WCTypesType):
        for module, item in wtype.imports():
            self.set_import(module, item)

    def set_import(self, import_module: str, import_name: str):
        """
        Track import statements needed for the python module we are creating
        """
        self.imports.setdefault(import_module, set()).add(import_name)

    def struct_code(self, cursor: ICursor, indent=0):
        assert cursor.kind == CursorKind.STRUCT_DECL
        i = indent * " "
        name = name_for_cursor(cursor)
        yield i + f"class {name}(Structure):"
        self.set_import("ctypes", "Structure")
        self.add_all_cursor(cursor)
        fields = []
        for child in cursor.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                fields.append(child)
        if len(fields) > 0:
            yield i + f"    _fields_ = ("
            for index, field in enumerate(fields):
                if index > 0:
                    yield ""  # blank line between fields
                yield from self.field_code(field, indent + 8)
            yield i + f"    )"
        else:
            yield i + "    pass"

    def check_dependency(self, wc_type: WCTypesType, depender: Cursor):
        for dependee in wc_type.dependencies():
            if dependee.kind == CursorKind.NO_DECL_FOUND:
                continue  # not a real declaration
            if dependee.hash in self.module_builder.included_cursors:
                continue  # declaration already exposed
            _dependee, dependers = self.unexposed_dependencies.setdefault(dependee.hash, (dependee, dict()))
            dependers[depender.hash] = depender

    def typedef_code(self, cursor: ICursor, indent=0):
        i = indent * " "
        name = name_for_cursor(cursor)
        # TODO: warn if base_type is not exposed
        base_type = w_type_for_clang_type(cursor.underlying_typedef_type, cursor)
        if str(name) == str(base_type):
            return  # Avoid no-op typedefs
        self.load_imports(base_type)
        self.check_dependency(base_type, cursor)
        self.add_all_cursor(cursor)
        yield from self.above_comment(cursor, indent)
        yield from self.right_comment(cursor, i + f"{name}: type = {base_type}")
        # r_comment = self.right_comment(cursor)
        # pre_comment = i + f"{name}: type = {base_type}"
        # yield f"{pre_comment}{r_comment}"

    def write_module(self, file):
        self.imports.clear()
        self.all_section_cursors.clear()
        self.unexposed_dependencies.clear()
        # First, accumulate the main body of the generated code in memory,
        # so we can track needed import statements just-in-time
        body_lines = []
        previous_blank_lines = 0
        for cursor in self.module_builder.cursors():
            if not cursor.is_included():
                continue
            coder = self.coder_for_cursor_kind(cursor.kind)
            for index, line in enumerate(coder(cursor, 0)):
                if index == 0:
                    # Insert blank lines according to PEP8 and CursorType
                    blank_lines_count = max(previous_blank_lines, _blank_lines(cursor))
                    for _ in range(blank_lines_count):
                        body_lines.append("")
                    previous_blank_lines = _blank_lines(cursor)
                body_lines.append(line)
        # Now start printing lines for real
        # import statements
        import_blank_lines = 0
        for line in self.import_code():
            # Emit at least one blank line after imports
            import_blank_lines = 1  # TODO: what if a class definition follows the imports?
            print(line, file=file)
        for _ in range(import_blank_lines):
            print("", file=file)
        # main body of code
        for line in body_lines:
            print(line, file=file)
        # __all__ stanza
        for index, line in enumerate(self.all_section_code()):
            if index == 0:
                # Emit at least one blank line before the __all__ stanza
                for _ in range(max(1, previous_blank_lines)):
                    print("", file=file)
            print(line, file=file)
        file.flush()
        # Warn about unexposed dependencies
        for dependee, dependers in self.unexposed_dependencies.values():
            unexposed_kind = short_name_for_cursor_kind.get(dependee.kind, str(dependee.kind))
            print(inspect.cleandoc(f"""
                WARNING: {name_for_cursor(dependee)} [{unexposed_kind}]
                > execution error W1040: This declaration is unexposed, but there are other 
                > declarations that refer to it. This could cause "no to_python
                > converter found" run time error.
                > Declarations: [{', '.join(sorted([c.spelling for c in dependers.values()]))}]
            """))


def _blank_lines(cursor: ICursor) -> int:
    """PEP8 blank lines by declaration type"""
    if cursor.kind in [
        CursorKind.CLASS_DECL,
        CursorKind.ENUM_DECL,
        CursorKind.FUNCTION_DECL,
        CursorKind.STRUCT_DECL,
        CursorKind.UNION_DECL,
    ]:
        return 2
    if cursor.kind in [
        CursorKind.CONSTRUCTOR,
        CursorKind.CXX_METHOD,
    ]:
        return 1
    return 0


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
short_name_for_cursor_kind = {
    CursorKind.STRUCT_DECL: "struct",
}


__all__ = [
    "CTypesCodeGenerator",
]
