from wraptor import ModuleBuilder
from wraptor.decl.struct import StructDeclaration


class CTypesCodeGenerator(object):
    def __init__(self, module_builder: ModuleBuilder):
        self.module_builder = module_builder

    def write_module(self, file):
        for decl in self.module_builder.declarations():
            if not decl.included():
                continue
            coder = coder_map[type(decl)]
            for line in coder(decl, 0):
                print(line, file=file)


def field_code(field, indent=0):
    i = indent * " "
    yield i+f'("{field.name}", {field.cursor.type.spelling}),'  # TODO: more work on types


def struct_code(struct: StructDeclaration, indent=0):
    i = indent * " "
    yield i+f"class {struct.name}(ctypes.Structure):"
    if len(struct.fields) > 0:
        yield i+f"    _fields_ = ("
        for field in struct.fields:
            yield from field_code(field, indent + 8)
        yield i + f"    )"
    else:
        yield i+"    pass"


coder_map = {
    StructDeclaration: struct_code,
}

__all__ = [
    "CTypesCodeGenerator",
]
