"""Command line entry points that run without Maya.

``rig-kit validate`` checks a rig description exported from Maya and writes a
JSON or Markdown report. ``rig-kit segment`` runs the proxy segmentation on a
mesh dump (faces plus weights) and prints the piece sizes, which is handy for
tuning ``--smooth`` and ``--min-faces`` on a farm machine.

"""

import argparse
import json
import os
import sys

import yaml

from rig_kit import report
from rig_kit import segment
from rig_kit import validate

FORMATS = ("md", "json")


def main(argv=None):
    """Parse arguments and run a sub-command.

    Args:
        argv (list): Arguments without the program name. Defaults to sys.argv.

    Returns:
        int: Exit code. 0 on success, 1 when validation finds errors, 2 on
        bad input.

    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as error:
        print(f"rig-kit: {error}", file=sys.stderr)
        return 2


def _build_parser():
    """Create the argument parser with its sub-commands."""
    parser = argparse.ArgumentParser(prog="rig-kit", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("validate", help="Validate a rig description JSON.")
    check.add_argument("rig", help="Rig description JSON exported from Maya.")
    check.add_argument("--settings", help="YAML file with validation setting overrides.")
    check.add_argument("--rules", nargs="+", help="Only run these rules.")
    check.add_argument("--format", choices=FORMATS, default="md")
    check.add_argument("--output", help="Write the report here instead of stdout.")
    check.set_defaults(func=_run_validate)

    split = commands.add_parser("segment", help="Segment a mesh dump into pieces.")
    split.add_argument("mesh", help="JSON with 'faces', 'weights' and 'influences'.")
    split.add_argument("--smooth", type=int, default=2, help="Smoothing iterations.")
    split.add_argument("--min-faces", type=int, default=0, help="Merge smaller islands.")
    split.set_defaults(func=_run_segment)
    return parser


def _read_json(path):
    """Load a JSON file, raising FileNotFoundError when it is missing."""
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing file: {0}".format(path))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_settings(path):
    """Load validation setting overrides from YAML, or None."""
    if not path:
        return None
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing settings file: {0}".format(path))
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _run_validate(args):
    """Run the ``validate`` sub-command."""
    rig = _read_json(args.rig)
    issues = validate.run(rig, settings=_read_settings(args.settings), rules=args.rules)
    name = rig.get("name", os.path.splitext(os.path.basename(args.rig))[0])
    render = report.to_json if args.format == "json" else report.to_markdown
    text = render(name, issues)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        info = report.summary(name, issues)
        print(f"Wrote {args.output}: {info['errors']} error(s), {info['warnings']} warning(s)")
    else:
        sys.stdout.write(text)
    return 0 if report.summary(name, issues)["passed"] else 1


def _run_segment(args):
    """Run the ``segment`` sub-command."""
    data = _read_json(args.mesh)
    for key in ("faces", "weights"):
        if key not in data:
            raise ValueError("Mesh dump is missing '{0}'.".format(key))
    result = segment.segment(
        data["faces"], data["weights"],
        smooth_iterations=args.smooth, min_faces=args.min_faces,
    )
    names = data.get("influences", [])

    print("=" * 40)
    print(f" Segmentation: {len(data['faces'])} faces, {len(result.islands)} islands")
    print("=" * 40)
    for influence, count in result.piece_sizes().items():
        label = names[influence] if influence < len(names) else str(influence)
        print(f"  {label:<28} {count:>8}")
    return 0
