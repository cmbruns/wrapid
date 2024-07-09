from wraptor.decl.translation_unit import TranslationUnitDeclaration


class ModuleBuilder(object):
    def __init__(self, file_paths, compiler_args=None):
        self.translation_units = []
        self.structs = []
        for path in file_paths:
            self.translation_units.append(TranslationUnitDeclaration(
                file_path=path,
                compiler_args=compiler_args,
            ))

    def class_(self, name: str):
        """Returns a declaration by name"""
        for tu in self.translation_units:
            for struct in tu.structs:
                if struct.name == name:
                    return struct
        raise ValueError(f"class '{name}' not found")

    def declarations(self):
        for tu in self.translation_units:
            yield from tu.declarations()


__all__ = [
    "ModuleBuilder",
]

if __name__ == "__main__":
    mb = ModuleBuilder(
        file_paths=["C:/Users/cmbruns/Documents/git/libjpeg-turbo/jpeglib.h"],
    )
    jpeg_compress_struct = mb.class_("jpeg_compress_struct")
    jpeg_compress_struct.include()
