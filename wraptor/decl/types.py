from clang.cindex import TypeKind


def type_for_clang_type(clang_type):
    if clang_type.kind == TypeKind.CONSTANTARRAY:
        return ConstantArrayType(clang_type)
    elif clang_type.kind == TypeKind.ELABORATED:
        return type_for_clang_type(clang_type.get_declaration().type)
    elif clang_type.kind == TypeKind.ENUM:
        return EnumType(clang_type)
    elif clang_type.kind == TypeKind.FUNCTIONPROTO:
        return FunctionProtoType(clang_type)
    elif clang_type.kind == TypeKind.POINTER:
        return PointerType(clang_type)
    elif clang_type.kind == TypeKind.RECORD:
        return RecordType(clang_type)
    elif clang_type.kind == TypeKind.TYPEDEF:
        return TypeDefType(clang_type)
    elif clang_type.kind in [
        TypeKind.INT,
        TypeKind.SHORT,
        TypeKind.UCHAR,
        TypeKind.USHORT,
    ]:
        return PrimitiveType(clang_type)
    else:
        decl = clang_type.get_declaration()
        assert False


class ConstantArrayType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type
        self.count = clang_type.element_count  # TODO - might be a constant symbol
        self.element_type = type_for_clang_type(clang_type.element_type)


class EnumType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type


class FunctionProtoType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type
        self.result_type = type_for_clang_type(clang_type.get_result())
        self.argument_types = [type_for_clang_type(a) for a in clang_type.argument_types()]


class PointerType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type
        self.pointee = type_for_clang_type(clang_type.get_pointee())


class PrimitiveType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type


class RecordType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type
        self.decl = self.clang_type.get_declaration()


class TypeDefType(object):
    def __init__(self, clang_type):
        self.clang_type = clang_type
        self.name = clang_type.spelling
        decl = clang_type.get_declaration()
        self.underlying_type = type_for_clang_type(decl.underlying_typedef_type)
