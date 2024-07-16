import importlib.util
import sys


def import_module_from_string(name: str, code: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(code, module.__dict__)
    sys.modules[name] = module
    globals()[name] = module
    return module
