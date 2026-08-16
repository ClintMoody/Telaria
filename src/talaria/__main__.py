# Talaria launcher. This stub must PARSE on any Python (2.7 included) so the floor
# message reaches users on museum interpreters instead of a SyntaxError (R-XPLAT-09).
# No f-strings, no walrus, no annotations in this file.
import sys

if sys.version_info < (3, 9):
    sys.stderr.write(
        "talaria needs Python 3.9 or newer; this is Python %d.%d.\n"
        "On this machine try: python3 talaria.pyz  (or install a newer Python)\n"
        % (sys.version_info[0], sys.version_info[1]))
    sys.exit(2)

from talaria.cli import main  # noqa: E402

sys.exit(main())
