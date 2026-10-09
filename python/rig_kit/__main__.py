"""Run the rig_kit command line: ``python -m rig_kit``.

Delegates to :func:`rig_kit.cli.main` and exits with its return code.

"""

import sys

from rig_kit import cli

sys.exit(cli.main())
