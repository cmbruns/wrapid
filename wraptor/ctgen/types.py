from typing import Iterator
from clang.cindex import Type as ClangType
from clang.cindex import Cursor, CursorKind, TokenKind, TypeKind


class WCTypesType(object):
    """
    Base class for ctypes mapping from declared types
    """
    def __init__(self, clang_type: ClangType):
        self.clang_type = clang_type

    def dependencies(self) -> Iterator[Cursor]:
        """Declarations in the name of this type, which might need to be exposed."""
        decl = self.clang_type.get_declaration()
        if decl.kind != CursorKind.NO_DECL_FOUND:
            yield decl

    def imports(self) -> Iterator[tuple[str, str]]:  # noqa
        """module/item pairs required for this type's name to be parsed"""
        yield from []

    def __str__(self):
        name = self.clang_type.spelling
        if name.startswith("struct "):
            name = name.removeprefix("struct ")
        return name


class ConstantArrayType(WCTypesType):
    def __init__(self, clang_type: ClangType, parent_declaration: Cursor):
        super().__init__(clang_type)
        self.parent_declaration = parent_declaration

    def dependencies(self) -> Iterator[Cursor]:
        yield from self.element_type.dependencies()
        # TODO: how to get dependency on element_count macro definition?

    @property
    def element_count(self):
        declaration = self.clang_type.get_declaration()
        if declaration.kind == CursorKind.NO_DECL_FOUND:
            declaration = self.parent_declaration
        # Look for macro definition name for element count
        if declaration is not None:
            in_brackets = False
            for token in declaration.get_tokens():
                # Try to parse out element count spelling
                if token.kind == TokenKind.PUNCTUATION and token.spelling == "[":
                    in_brackets = True
                elif token.kind == TokenKind.PUNCTUATION and token.spelling == "]":
                    in_brackets = False
                elif in_brackets and token.kind == TokenKind.IDENTIFIER:
                    # TODO: is there only one set of brackets?
                    # TODO: is there a corresponding macro definition?
                    return token.spelling
        return self.clang_type.element_count

    @property
    def element_type(self) -> WCTypesType:
        return w_type_for_clang_type(self.clang_type.element_type)

    def imports(self) -> Iterator[tuple[str, str]]:  # noqa
        """module/item pairs required for this type"""
        yield from self.element_type.imports()

    def __str__(self) -> str:
        return f"{self.element_type} * {self.element_count}"


class FunctionPointerType(WCTypesType):
    def dependencies(self):
        yield from []

    def imports(self):
        yield "ctypes", "CFUNCTYPE"
        yield from self.result_type.imports()
        for arg in self.arg_types:
            yield from arg.imports()

    @property
    def arg_types(self):
        return [w_type_for_clang_type(a) for a in self.clang_type.argument_types()]

    @property
    def result_type(self):
        return w_type_for_clang_type(self.clang_type.get_result())

    def __str__(self):
        return f"CFUNCTYPE({self.result_type}, {', '.join([str(a) for a in self.arg_types])})"


class PointerType(WCTypesType):
    def imports(self):
        yield "ctypes", "POINTER"
        yield from self.pointee.imports()

    def dependencies(self) -> Iterator[Cursor]:
        """Declarations in the name of this type, which might need to be exposed."""
        yield from super().dependencies()
        # TODO: maybe pointee dependencies could be satisfied with forward declarations
        yield from self.pointee.dependencies()

    @property
    def pointee(self) -> WCTypesType:
        return w_type_for_clang_type(self.clang_type.get_pointee())

    def __str__(self) -> str:
        return f"POINTER({self.pointee})"


class PrimitiveCTypesType(WCTypesType):
    def __init__(self, clang_type, symbol: str):
        super().__init__(clang_type)
        self.symbol = symbol

    def imports(self):
        yield "ctypes", self.symbol

    def __str__(self) -> str:
        return self.symbol


class VoidType(WCTypesType):
    def __str__(self):
        return "None"


def w_type_for_clang_type(clang_type: ClangType, parent_declaration: Cursor = None) -> WCTypesType:
    if clang_type.kind in primitive_ctype_for_clang_type:
        return PrimitiveCTypesType(clang_type, primitive_ctype_for_clang_type[clang_type.kind])
    elif clang_type.kind == TypeKind.CONSTANTARRAY:
        return ConstantArrayType(clang_type, parent_declaration)
    elif clang_type.kind == TypeKind.ELABORATED:
        return w_type_for_clang_type(clang_type.get_declaration().type)
    elif clang_type.kind == TypeKind.FUNCTIONPROTO:
        return FunctionPointerType(clang_type)
    elif clang_type.kind == TypeKind.POINTER:
        pointee = clang_type.get_pointee()
        if pointee.kind in [TypeKind.CHAR_S, TypeKind.SCHAR]:
            return PrimitiveCTypesType(clang_type, "c_char_p")
        elif pointee.kind == TypeKind.FUNCTIONPROTO:
            return FunctionPointerType(pointee)
        elif pointee.kind == TypeKind.VOID:
            return PrimitiveCTypesType(clang_type, "c_void_p")
        elif pointee.kind == TypeKind.WCHAR:
            return PrimitiveCTypesType(clang_type, "c_wchar_p")
        else:
            return PointerType(clang_type)
    elif clang_type.kind == TypeKind.VOID:
        return VoidType(clang_type)
    else:
        return WCTypesType(clang_type)


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

if __name__ == "__main__":
    # TODO:
    pass
