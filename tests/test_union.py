import io
import unittest

import wrapid
from tests.util import import_module_from_string


class StructTester(unittest.TestCase):
    def test_simple_struct_ctypes(self):
        mb = wrapid.ModuleBuilder(
            path="data/union_input.h",
        )
        mb.unions().include()
        cg = wrapid.CTypesCodeGenerator(mb)
        py_code_stream = io.StringIO()
        cg.write_module(py_code_stream)
        py_code = py_code_stream.getvalue()
        with open("data/union_ctypes_expected.py") as f:
            py_code_expected = f.read()
        # Verify that the code is generated as expected
        self.assertEqual(py_code_expected, py_code)
        # Verify that the generated module loads and works correctly
        simple_union = import_module_from_string("simple_union", py_code)
        data = simple_union.Data(f=6.3)
        self.assertGreater(6.4, data.f)
        self.assertLess(6.3, data.f)


if __name__ == "__main__":
    unittest.main()
