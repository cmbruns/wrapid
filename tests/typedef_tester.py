import ctypes
import importlib.util
import io
import sys
import unittest

import wraptor


def import_module_from_string(name: str, code: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(code, module.__dict__)
    sys.modules[name] = module
    globals()[name] = module
    return module


class TypedefTester(unittest.TestCase):
    def test_simple_typedef(self):
        mb = wraptor.ModuleBuilder(
            path="data/simple_typedef_input.h",
        )
        mb.typedefs().include()
        cg = wraptor.CTypesCodeGenerator(mb)
        py_code_stream = io.StringIO()
        cg.write_module(py_code_stream)
        py_code = py_code_stream.getvalue()
        with open("data/simple_typedef_ctypes_expected.py") as f:
            py_code_expected = f.read()
        self.assertEqual(py_code_expected, py_code)
        # Verify the code is generated as expected
        import_module_from_string("my_module", py_code)
        self.assertEqual(ctypes.c_int, my_module.IntAlias)  # noqa


if __name__ == "__main__":
    unittest.main()
