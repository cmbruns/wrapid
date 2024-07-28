import inspect
from typing import Union, Callable, Iterator

from clang.cindex import Type as ClangType
from clang.cindex import (
    Cursor,
    CursorKind,
    Token,
    TokenKind, TypeKind,
)

from wrapid import ModuleBuilder
from wrapid.ctgen.types import w_type_for_clang_type, WCTypesType, VoidType
from wrapid.decl import (
    DeclWrapper,
    OpaqueKind,
    OpaqueWrapper,
    StructUnionWrapper,
    StructDeclType,
)

ICursor = Union[Cursor, DeclWrapper]


class Indent(object):
    """Manages indentation during code generation"""
    def __init__(self, spacer: "Spacer"):
        self.spacer = spacer

    def __enter__(self):
        self.spacer.indent_count += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.spacer.indent_count -= 1


class Spacer(object):
    """Manages blank lines and indentation during code generation"""
    def __init__(self):
        self.previous_blank_lines = 2  # inhibit initial blank lines by pretending there are already two
        self.indent_count = 0
        self._indent_str = "    "

    def indent(self) -> str:
        return self._indent_str * self.indent_count

    def next_indent(self):
        return Indent(self)

    def end_pad(self, num_lines: int) -> Iterator[str]:
        self.previous_blank_lines = num_lines
        for _ in range(num_lines):
            yield ""

    def pad_to(self, num_lines: int) -> Iterator[str]:
        if num_lines <= self.previous_blank_lines:
            return
        for _ in range(num_lines - self.previous_blank_lines):
            yield ""


class CTypesCodeGenerator(object):
    def __init__(self, module_builder: ModuleBuilder, library=None):
        self.module_builder = module_builder
        self.library = library
        self.imports = dict()
        self.all_section_cursors = set()
        self.unexposed_dependencies = dict()

    def above_comment(self, cursor, spacer: Spacer) -> str:
        """
        Find comments directly above a declaration in the source file.
        :param cursor: ctypes Cursor object representing the declaration.
        :param spacer: number of spaces cursor is indented in the output
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
        i = spacer.indent()
        for line in comment.splitlines():
            yield i + line

    def add_all_cursor(self, cursor):
        self.all_section_cursors.add(cursor)

    def all_section_code(self, spacer: Spacer):
        if not self.all_section_cursors:
            return
        yield from spacer.pad_to(1)
        yield "__all__ = ["
        all_items = sorted([c.alias for c in self.all_section_cursors])
        for item in all_items:
            yield f'    "{item}",'
        yield "]"
        yield from spacer.end_pad(0)

    def coder_for_cursor_kind(self, cursor_kind: CursorKind) -> Callable[[ICursor, Spacer], Iterator[str]]:
        return {
            CursorKind.ENUM_DECL: self.enum_code,
            CursorKind.FUNCTION_DECL: self.function_code,
            CursorKind.MACRO_DEFINITION: self.macro_code,
            OpaqueKind: self.opaque_code,
            CursorKind.STRUCT_DECL: self.struct_code,
            CursorKind.TYPEDEF_DECL: self.typedef_code,
            CursorKind.UNION_DECL: self.union_code,
        }[cursor_kind]

    def enum_code(self, decl: DeclWrapper, spacer: Spacer):
        assert decl.kind == CursorKind.ENUM_DECL
        self.set_import("enum", "IntFlag")
        if decl._exported:
            self.add_all_cursor(decl)
        values = []
        for v in decl.get_children():
            assert v.kind == CursorKind.ENUM_CONSTANT_DECL
            values.append(v)
        enum_name = decl.alias
        yield from spacer.pad_to(2)
        yield spacer.indent() + f"class {enum_name}(IntFlag):"
        with spacer.next_indent():
            if len(values) == 0:
                yield spacer.indent() + "pass"
            else:
                for v in values:
                    yield from self.enum_constant_code(v, spacer)
                # yield i + f"globals().update({enum_name}.__members__)"
                # Two blank lines for PEP8
                yield ""
                yield ""
        for v in values:
            constant_name = v.spelling
            yield spacer.indent() + f"{constant_name} = {enum_name}.{constant_name}"
        yield from spacer.end_pad(1)

    @staticmethod
    def enum_constant_code(cursor: Cursor, spacer: Spacer):
        i = spacer.indent()
        assert cursor.kind == CursorKind.ENUM_CONSTANT_DECL
        yield i + f"{cursor.spelling} = {cursor.enum_value}"

    def field_code(self, decl: DeclWrapper, spacer: Spacer):
        i = spacer.indent()
        assert decl.kind == CursorKind.FIELD_DECL
        field_name = decl.alias
        w_type = w_type_for_clang_type(decl.type, decl)
        type_name = w_type.alias
        # If the field type is unnamed and is a declared type, use the alias, if any, as the name
        if "(unnamed at " in type_name:
            type_cursor = w_type.clang_type.get_declaration()
            if type_cursor.kind != CursorKind.NO_DECL_FOUND:
                type_decl = self.module_builder.wrapper_index.get(type_cursor)
                type_name = type_decl.alias
        self.load_imports(w_type)
        self.check_dependency(w_type, decl)
        yield from self.above_comment(decl, spacer)
        yield from self.right_comment(decl, i + f'("{field_name}", {type_name}),')

    def function_code(self, decl: DeclWrapper, spacer: Spacer):
        i = spacer.indent()
        assert decl.kind == CursorKind.FUNCTION_DECL
        assert self.library is not None
        lib_name = self.library[0]
        yield from spacer.pad_to(1)
        yield from self.above_comment(decl, spacer)
        yield from self.right_comment(
            decl,
            i + f"{decl.alias} = {lib_name}.{decl.name}"
        )
        result_type = VoidType(ClangType(TypeKind.VOID.value))
        parameters = []
        for c in decl.get_children():
            if c.kind == CursorKind.TYPE_REF:
                result_type = w_type_for_clang_type(c.type)
            elif c.kind == CursorKind.PARM_DECL:
                parameters.append(c)
            else:
                assert False
        yield i + f"{decl.alias}.restype = {result_type.alias}"
        if len(parameters) == 0:
            yield i + f"{decl.alias}.argtypes = []"
        else:
            yield i + f"{decl.alias}.argtypes = ["
            with spacer.next_indent():
                for parameter in parameters:
                    t = w_type_for_clang_type(parameter.type)
                    self.load_imports(t)
                    yield spacer.indent() + f"{t.alias},"
            yield i + f"]"
        yield from spacer.end_pad(1)

    def import_code(self, spacer: Spacer) -> Iterator[str]:
        if not self.imports:
            return
        yield from spacer.pad_to(1)
        for module in self.imports:
            if len(self.imports[module]) < 5:
                yield f"from {module} import {', '.join(sorted(self.imports[module]))}"
            else:
                yield f"from {module} import ("
                for item in sorted(self.imports[module]):
                    yield f"    {item},"
                yield ")"
        yield from spacer.end_pad(1)

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
        # Indent subsequent lines of comment to line up with the first one.
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

    def load_imports(self, w_type: WCTypesType):
        for module, item in w_type.imports():
            self.set_import(module, item)

    def macro_code(self, cursor: Cursor, spacer: Spacer):
        assert cursor.kind == CursorKind.MACRO_DEFINITION
        macro_name = cursor.spelling
        tokens = list(cursor.get_tokens())[1:]  # skip the first token, which is the macro name
        if len(tokens) < 1:
            return  # empty definition
        if len(tokens) > 2:
            return  # too many tokens to deal with TODO:
        rhs = tokens[0].spelling
        if len(tokens) == 2:
            if tokens[1].spelling == "-":
                # two tokens for negative numbers is OK
                rhs += tokens[1].spelling
            else:
                return  # TODO: unexplored case
        # TODO: but only if exported...
        self.add_all_cursor(cursor)
        yield from spacer.pad_to(0)
        yield from self.above_comment(cursor, spacer)
        i = spacer.indent()
        yield from self.right_comment(cursor, i + f'{macro_name} = {rhs}')
        yield from spacer.end_pad(0)

    def opaque_code(self, decl: OpaqueWrapper, spacer: Spacer):
        yield from spacer.pad_to(2)
        i = spacer.indent()
        yield i + "# Opaque type"
        self.set_import("ctypes", "Structure")
        yield i + f"class {decl.alias}(Structure):"
        yield i + "    pass"
        yield from spacer.end_pad(2)

    def set_import(self, import_module: str, import_name: str):
        """
        Track import statements needed for the python module we are creating
        """
        self.imports.setdefault(import_module, set()).add(import_name)

    def struct_code(self, decl: StructUnionWrapper, spacer: Spacer):
        assert decl.kind == CursorKind.STRUCT_DECL
        yield from self._struct_union_code(decl, spacer, "Structure")

    def _struct_union_code(self, decl: StructUnionWrapper, spacer: Spacer, ctypes_type_name: str = "Structure"):
        i = spacer.indent()
        fields = list(decl.fields())
        yield from spacer.pad_to(2)
        if decl.decl_type == StructDeclType.FORWARD_ONLY:
            if len(fields) > 0:
                yield i + "# Forward declaration. Definition of _fields_ will appear later."
            else:
                yield i + "# Forward declaration"
            self.set_import("ctypes", ctypes_type_name)
            yield i + f"class {decl.alias}({ctypes_type_name}):"
            with spacer.next_indent():
                yield spacer.indent() + "pass"
        else:
            if decl.decl_type == StructDeclType.DEFINITION_ONLY:
                if len(fields) > 0:
                    yield i + f"{decl.alias}._fields_ = ("
            elif decl.decl_type == StructDeclType.FULL:
                self.set_import("ctypes", ctypes_type_name)
                yield i + f"class {decl.alias}({ctypes_type_name}):"
                with spacer.next_indent():
                    if len(fields) > 0:
                        yield spacer.indent() + "_fields_ = ("
                    else:
                        yield spacer.indent() + "pass"
            else:
                raise NotImplementedError
            with spacer.next_indent():
                with spacer.next_indent():
                    for index, field in enumerate(fields):
                        if index > 0:
                            yield ""  # blank line between fields
                        yield from self.field_code(field, spacer)
                if len(fields) > 0:
                    yield spacer.indent() + ")"
        if decl._exported:
            self.add_all_cursor(decl)
        yield from spacer.end_pad(2)

    def check_dependency(self, wc_type: WCTypesType, depender: Cursor):
        for dependee in wc_type.dependencies():
            if dependee.kind == CursorKind.NO_DECL_FOUND:
                continue  # not a real declaration
            w_decl = self.module_builder.wrapper_index.get(dependee)
            if w_decl.is_included():
                continue  # declaration already exposed
            _dependee, dependers = self.unexposed_dependencies.setdefault(dependee.hash, (dependee, dict()))
            dependers[depender.hash] = depender

    def typedef_code(self, decl: DeclWrapper, spacer: Spacer):
        i = spacer.indent()
        name = decl.alias
        # TODO: warn if base_type is not exposed
        base_type = w_type_for_clang_type(decl.underlying_typedef_type, decl)
        if str(name) == str(base_type):
            return  # Avoid no-op typedefs
        self.load_imports(base_type)
        self.check_dependency(base_type, decl)
        if decl._exported:
            self.add_all_cursor(decl)
        yield from self.above_comment(decl, spacer)
        yield from self.right_comment(decl, i + f"{name}: type = {base_type}")
        # r_comment = self.right_comment(cursor)
        # pre_comment = i + f"{name}: type = {base_type}"
        # yield f"{pre_comment}{r_comment}"

    def union_code(self, decl: StructUnionWrapper, spacer: Spacer):
        assert decl.kind == CursorKind.UNION_DECL
        yield from self._struct_union_code(decl, spacer, "Union")

    # Factor out generating one cursor's lines, to help with
    # automated dependency/before generation
    def _write_declaration(self, decl: DeclWrapper, spacer: Spacer) -> Iterator[str]:
        for dep in decl.predecessors:
            if dep is decl:
                continue
            # TODO: check if its already exported first
            yield from self._write_declaration(dep, spacer)
        coder = self.coder_for_cursor_kind(decl.kind)
        yield from coder(decl, spacer)

    def write_module(self, file):
        self.imports.clear()
        self.all_section_cursors.clear()
        self.unexposed_dependencies.clear()
        body_spacer = Spacer()
        body_spacer.previous_blank_lines = 0  # Begin assuming something comes before the body
        # First, accumulate the main body of the generated code in memory,
        # so we can track needed import statements just-in-time
        body_lines = []
        if self.library is not None:
            self.set_import("ctypes", "cdll")
            body_spacer.pad_to(0)
            body_lines.append(f'{self.library[0]} = cdll.LoadLibrary("{self.library[1]}")')
            body_spacer.end_pad(0)
        for decl in self.module_builder.included():
            for line in self._write_declaration(decl, body_spacer):
                body_lines.append(line)
        # Now start printing lines for real
        # import statements
        spacer = Spacer()
        prev_line = None
        for line in self.import_code(spacer):
            print(line, file=file)
            prev_line = line
        # main body of code
        # special case for boundary between imports and body
        if prev_line == "" and body_lines[0] == "":
            del body_lines[0]
        for line in body_lines:
            print(line, file=file)
        # __all__ stanza
        for index, line in enumerate(self.all_section_code(body_spacer)):
            print(line, file=file)
        file.flush()
        # Warn about unexposed dependencies
        for dependee, dependers in self.unexposed_dependencies.values():
            unexposed_kind = short_name_for_cursor_kind.get(dependee.kind, str(dependee.kind))
            print(inspect.cleandoc(f"""
                WARNING: {dependee.spelling} [{unexposed_kind}]
                > execution error W1040: This declaration is unexposed, but there are other 
                > declarations that refer to it. This could cause
                > "NameError: name is not defined" run time error.
                > Declarations: [{', '.join(sorted([c.spelling for c in dependers.values()]))}]
            """))


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
        line = line.rstrip()
        lines.append(line)
    # Remove whitespace in a multiline-aware way
    comment = inspect.cleandoc("\n".join(lines))
    # Insert python comment character
    comment = "\n".join([f"# {c}" for c in comment.splitlines()])
    return comment


# TODO: this should be in module_builder
short_name_for_cursor_kind = {
    CursorKind.STRUCT_DECL: "struct",
}


__all__ = [
    "CTypesCodeGenerator",
]
