"""Root conftest.

Its presence puts the repository root on ``sys.path`` (pytest's default
``prepend`` import mode inserts a conftest's directory), which is what lets the
tests import the top-level helper scripts ``bump_version`` and ``get_version``.
"""
