"""Makes `python -m sentinel.tools` print the isolation report.

A package needs a `__main__` to be runnable with `-m`; the report itself lives
in `__init__.py` alongside the registry it describes.
"""

from sentinel.tools import main

main()
