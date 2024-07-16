from ctypes import Structure, c_char, c_int


class MyStructure(Structure):
    _fields_ = (
        ("number", c_int),

        ("letter", c_char),
    )


__all__ = [
    "MyStructure",
]
