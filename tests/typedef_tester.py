import inspect
import io
import unittest

import wraptor


class TypedefTester(unittest.TestCase):
    def test_simple_typedef(self):
        src = inspect.cleandoc("""
            typedef int INT_TYPEDEF;
        """)
        expected = inspect.cleandoc("""
            from ctypes import c_int
            
            INT_TYPEDEF: type = c_int
            
            __all__ = [
                "INT_TYPEDEF",
            ]
        """) + "\n"
        mb = wraptor.ModuleBuilder(
            path="foo.h",
            unsaved_files=[("foo.h", src),]
        )
        mb.typedefs().include()
        cg = wraptor.CTypesCodeGenerator(mb)
        result = io.StringIO()
        cg.write_module(result)
        self.assertEqual(expected, result.getvalue())


if __name__ == "__main__":
    unittest.main()
