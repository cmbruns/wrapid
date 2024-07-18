import ctypes
import io
import unittest

import wraptor
from tests.util import import_module_from_string


class MacroTester(unittest.TestCase):
    def test_simple_macro_ctypes(self):
        file_path = "data/simple_macro_definition_input.h"
        mb = wraptor.ModuleBuilder(
            path=file_path,
        )
        mb.in_header(file_path).macros().include()
        cg = wraptor.CTypesCodeGenerator(mb)
        py_code_stream = io.StringIO()
        cg.write_module(py_code_stream)
        py_code = py_code_stream.getvalue()
        with open("data/simple_macro_definition_ctypes_expected.py") as f:
            py_code_expected = f.read()
        # Verify that the code is generated as expected
        self.assertEqual(py_code_expected, py_code)
        # Verify that the generated module loads and works correctly
        simple_macro = import_module_from_string("simple_macro", py_code)
        self.assertEqual(8, simple_macro.DCTSIZE)  # noqa


if __name__ == "__main__":
    unittest.main()
