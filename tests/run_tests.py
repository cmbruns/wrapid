# Programmatically run as if "pytest" on command line
# NOTE: run this from the top level wrapid folder, *NOT* from this "tests" folder.

import pytest

_result_code = pytest.main()
