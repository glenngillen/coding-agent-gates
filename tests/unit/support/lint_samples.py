"""Verbatim lint-imports 2.17 outputs captured on 2026-11-19 (``--no-cache --no-logo``,
``COLUMNS=1000``, macOS, Python 3.12.15) against copies of this example. Used as
parser fixtures; they are recorded tool output, not hand-written approximations.
Every case below exited with status 0 (KEPT) or 1 (everything else)."""

RULE = "Controllers must not import infrastructure repositories directly"

KEPT = """
---------
Contracts
---------

Analyzed 9 files, 8 dependencies.
---------------------------------

Controllers must not import infrastructure repositories directly KEPT

Contracts: 1 kept, 0 broken.
"""

BROKEN_ONE_EDGE = """
---------
Contracts
---------

Analyzed 9 files, 9 dependencies.
---------------------------------

Controllers must not import infrastructure repositories directly BROKEN

Contracts: 0 kept, 1 broken.


----------------
Broken contracts
----------------

Controllers must not import infrastructure repositories directly
----------------------------------------------------------------

orders.controllers is not allowed to import orders.infrastructure:

-   orders.controllers.orders -> orders.infrastructure.repository (l.14)


"""

BROKEN_TWO_EDGES = """
---------
Contracts
---------

Analyzed 9 files, 10 dependencies.
----------------------------------

Controllers must not import infrastructure repositories directly BROKEN

Contracts: 0 kept, 1 broken.


----------------
Broken contracts
----------------

Controllers must not import infrastructure repositories directly
----------------------------------------------------------------

orders.controllers is not allowed to import orders.infrastructure:

-   orders.controllers -> orders.infrastructure.repository (l.6)

-   orders.controllers.orders -> orders.infrastructure.repository (l.14)


"""

SYNTAX_ERROR = (
    "Syntax error in /work/src/orders/application/broken.py, line 1: def broken(:\n"
)
MISSING_FIELD = """
Contract "X" is not configured correctly:
    forbidden_modules: This is a required field.
"""
MISSING_MODULE = "\nModule 'orders.nosuch' does not exist.\n"
NO_CONTRACTS = """No contracts found in none.ini.

Each contract goes in an 'importlinter:contract:<name>' section (INI files)
or a 'tool.importlinter.contracts' array of tables (TOML files).
"""
NOT_ON_PATH = "Could not find package 'orders' in your Python path.\n"
UNPARSEABLE_CONFIG = """File contains no section headers.
file: '<string>', line: 1
'garbage [[[\\n'
"""

# Captured in §8 of evidence/walkthrough-2026-11-19.txt (exit 0): an
# ``ignore_imports`` entry for the offending edge was appended to .importlinter.
KEPT_ONE_IGNORED = """
---------
Contracts
---------

Analyzed 9 files, 9 dependencies.
---------------------------------

Controllers must not import infrastructure repositories directly KEPT (1 ignored import)

Contracts: 1 kept, 0 broken.
"""
