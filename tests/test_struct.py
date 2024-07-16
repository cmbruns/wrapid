import io
import unittest

import wraptor
from tests.util import import_module_from_string


class StructTester(unittest.TestCase):
    def test_simple_struct_ctypes(self):
        mb = wraptor.ModuleBuilder(
            path="data/simple_struct_input.h",
        )
        mb.structs().include()
        cg = wraptor.CTypesCodeGenerator(mb)
        py_code_stream = io.StringIO()
        cg.write_module(py_code_stream)
        py_code = py_code_stream.getvalue()
        with open("data/simple_struct_ctypes_expected.py") as f:
            py_code_expected = f.read()
        # Verify that the code is generated as expected
        self.assertEqual(py_code_expected, py_code)
        # Verify that the generated module loads and works correctly
        simple_struct = import_module_from_string("simple_struct", py_code)
        my_struct = simple_struct.MyStructure(6, "q".encode())
        self.assertEqual(6, my_struct.number)  # noqa


if __name__ == "__main__":
    unittest.main()
