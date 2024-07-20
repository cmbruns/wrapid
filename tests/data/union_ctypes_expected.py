from ctypes import Union, c_char, c_float, c_int


class Data(Union):
    _fields_ = (
        ("i", c_int),

        ("f", c_float),

        ("str", c_char * 20),
    )


__all__ = [
    "Data",
]
