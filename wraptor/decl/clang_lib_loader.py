"""
Now that pkg_resources is deprecated, all the crap that's needed to
use the supposed replacement importlib deserves its own file here.
"""

import atexit
import contextlib
import importlib.resources
import os
import platform

import clang.cindex

file_manager = contextlib.ExitStack()
atexit.register(file_manager.close)

if platform.system() == "Windows":
    ref = importlib.resources.files("wraptor.decl")/"libclang.dll"
elif platform.system() == "Linux":
    # TODO: don't hardcode this file name
    ref = importlib.resources.files("wraptor.decl")/"libclang-14.so"
else:
    raise NotImplementedError
lib_clang = file_manager.enter_context(importlib.resources.as_file(ref))
if os.path.isfile(lib_clang):
    clang.cindex.Config.set_library_file(lib_clang)
