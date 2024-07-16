import ctypes
import io
import unittest

import wraptor
from tests.util import import_module_from_string


class TypedefTester(unittest.TestCase):
    def test_simple_typedef_ctypes(self):
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
        # Verify that the code is generated as expected
        self.assertEqual(py_code_expected, py_code)
        # Verify that the generated module loads and works correctly
        simple_typedef = import_module_from_string("simple_typedef", py_code)
        self.assertEqual(ctypes.c_int, simple_typedef.IntAlias)  # noqa


if __name__ == "__main__":
    unittest.main()
