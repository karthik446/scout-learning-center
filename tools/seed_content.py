#!/usr/bin/env python3
"""Refused: the one-off that seeded content/ for site 2026.10.1 (system design module, families, redirects, changelog).

Families and role pathways no longer exist; content/ is edited by hand and grows through
``python3 tools/import_course.py --module ID --export DIR`` (see README.md, "Adding a module"). Running this file again would
overwrite modules/system-design.json, so it only says so.
"""

import sys

if __name__ == "__main__":
    sys.exit("seed_content.py is retired: the content is edited by hand and imported per module with tools/import_course.py --module")
