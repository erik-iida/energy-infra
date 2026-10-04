"""Moved to common/store.py (spec 3 step 4). This shim keeps `from collector.store import Store` working for one release."""
from common.store import *  # noqa: F401,F403
from common.store import Store, asset_name, load  # noqa: F401
