#!/usr/bin/env python3
"""Regenerate the generated regions of the reference pages, or check that they are up to date.

    uv run tools/docs/reference.py              rewrite every page
    uv run tools/docs/reference.py --check      exit 1 if a page is out of date
    uv run tools/docs/reference.py cli          only the named pages

`just docs-gen` and `just docs-check` run it. The pages are hand-written Markdown in docs/reference/
with regions between `<!-- generated: NAME -->` and `<!-- end generated -->` that this script owns;
see refdocs/page.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refdocs import PAGES  # noqa: E402
from refdocs.page import PageError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pages", nargs="*", choices=[[], *PAGES], metavar="PAGE", help=", ".join(PAGES))
    parser.add_argument("--check", action="store_true", help="write nothing; fail if a page is out of date")
    args = parser.parse_args()

    failed = False
    for name in args.pages or PAGES:
        page = PAGES[name]
        try:
            if args.check:
                diff = page.check()
                if diff:
                    print("\n".join(diff[:60]), file=sys.stderr)
                    print(f"{page.path} is out of date; run `just docs-gen`", file=sys.stderr)
                    failed = True
                else:
                    print(f"{page.path} is up to date")
            elif page.write():
                print(f"wrote {page.path}")
        except PageError as e:
            print(e, file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
