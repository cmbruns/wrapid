import io
import unittest

import wraptor
from tests.util import import_module_from_string


class EnumTester(unittest.TestCase):
    def test_simple_enum_ctypes(self):
        file_path = "data/enum_input.h"
        mb = wraptor.ModuleBuilder(
            path=file_path,
        )
        mb.in_header(file_path).enums().include()
        cg = wraptor.CTypesCodeGenerator(mb)
        py_code_stream = io.StringIO()
        cg.write_module(py_code_stream)
        py_code = py_code_stream.getvalue()
        with open("data/enum_ctypes_expected.py") as f:
            py_code_expected = f.read()
        # Verify that the code is generated as expected
        self.assertEqual(py_code_expected, py_code)
        # Verify that the generated module loads and works correctly
        simple_enum = import_module_from_string("simple_enum", py_code)
        self.assertEqual(1, simple_enum.Level.MEDIUM)  # noqa


if __name__ == "__main__":
    unittest.main()
