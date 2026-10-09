"""Render validation issues as JSON or Markdown.

Both formats carry the same summary (rig name, error and warning counts) so
the JSON can feed a publish gate or dashboard and the Markdown can be pasted
into a review ticket.

"""

import json

from rig_kit import validate


def summary(rig_name, issues):
    """Count issues by severity.

    Args:
        rig_name (str): Name of the validated rig.
        issues (list): :class:`rig_kit.validate.Issue` objects.

    Returns:
        dict: ``rig``, ``errors``, ``warnings`` and ``passed``.

    """
    errors = sum(1 for issue in issues if issue.severity == validate.ERROR)
    warnings = sum(1 for issue in issues if issue.severity == validate.WARNING)
    return {
        "rig": rig_name,
        "errors": errors,
        "warnings": warnings,
        "passed": errors == 0,
    }


def to_json(rig_name, issues):
    """Render a report as a JSON string.

    Args:
        rig_name (str): Name of the validated rig.
        issues (list): :class:`rig_kit.validate.Issue` objects.

    Returns:
        str: Indented JSON with ``summary`` and ``issues``.

    """
    payload = {
        "summary": summary(rig_name, issues),
        "issues": [issue.to_dict() for issue in issues],
    }
    return json.dumps(payload, indent=2)


def to_markdown(rig_name, issues):
    """Render a report as Markdown.

    Args:
        rig_name (str): Name of the validated rig.
        issues (list): :class:`rig_kit.validate.Issue` objects.

    Returns:
        str: Markdown with a status line and one table of issues.

    """
    info = summary(rig_name, issues)
    status = "PASSED" if info["passed"] else "FAILED"
    lines = [
        f"# Rig validation: {rig_name}",
        "",
        f"**{status}** - {info['errors']} error(s), {info['warnings']} warning(s)",
        "",
    ]
    if not issues:
        lines.append("No issues found.")
        return "\n".join(lines) + "\n"

    lines.extend([
        "| Severity | Rule | Node | Message |",
        "| --- | --- | --- | --- |",
    ])
    for issue in issues:
        lines.append("| {0} | {1} | `{2}` | {3} |".format(
            issue.severity, issue.rule, issue.node, _escape(issue.message)
        ))
    return "\n".join(lines) + "\n"


def _escape(text):
    """Escape pipe characters so they do not break the Markdown table."""
    return text.replace("|", "\\|")
