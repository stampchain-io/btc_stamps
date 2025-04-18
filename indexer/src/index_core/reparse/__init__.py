"""
Package initialization for reparse namespace.
Ensure stale stub modules are cleared so real modules load correctly.
"""

import sys

# Clean up any stub module entries for our submodules if they lack __file__
for sub in ("index_core.reparse.snapshot", "index_core.reparse.db_manager", "index_core.reparse.validator"):
    mod = sys.modules.get(sub)
    # If module exists but has no __file__, it's likely a test stub; remove it
    if mod is not None and not getattr(mod, "__file__", None):
        del sys.modules[sub]
