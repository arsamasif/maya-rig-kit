"""Validation rules for a rig description.

A rig description is a plain dict, exported from Maya by
``rig_kit.maya_export`` or written by hand in tests::

    {
        "name": "hero",
        "controls": [{"name": "arm_L0_fk0_ctl",
                      "values": {"tx": 0.0, ..., "sx": 1.0, "v": 1.0},
                      "locked": ["v"], "keyable": ["tx", "ty", ...]}],
        "joints": [{"name": "arm_L0_0_jnt", "deform": True}],
        "skin_clusters": [{"name": "body_skinCluster", "geometry": "body_geo",
                           "influences": ["arm_L0_0_jnt"],
                           "max_influences_found": 4}],
    }

Each rule is a function ``rule(rig, settings) -> list[Issue]``. Rules are
registered in ``RULES`` and run by :func:`run`.

"""

import re
from dataclasses import asdict, dataclass

ERROR = "error"
WARNING = "warning"

DEFAULT_SETTINGS = {
    "rest_values": {
        "tx": 0.0, "ty": 0.0, "tz": 0.0,
        "rx": 0.0, "ry": 0.0, "rz": 0.0,
        "sx": 1.0, "sy": 1.0, "sz": 1.0,
    },
    "tolerance": 1e-4,
    "require_locked": ["v"],
    "max_influences": 4,
    "control_pattern": r"^[A-Za-z][A-Za-z0-9]*_[LRC]\d+_[A-Za-z0-9_]*ctl$",
    "joint_pattern": r"^[A-Za-z][A-Za-z0-9]*_[LRC]\d+_[A-Za-z0-9_]*jnt$",
    "ignore_joints": [r"_end_jnt$"],
}


@dataclass(frozen=True)
class Issue:
    """A single validation finding.

    Attributes:
        rule (str): Name of the rule that raised it.
        severity (str): ``"error"`` or ``"warning"``.
        node (str): Node the issue is about.
        message (str): Human-readable description.

    """

    rule: str
    severity: str
    node: str
    message: str

    def to_dict(self):
        """Return the issue as a JSON-friendly dict."""
        return asdict(self)


def merged_settings(overrides=None):
    """Return default settings updated with ``overrides``.

    Args:
        overrides (dict): Settings to replace, e.g. ``{"max_influences": 8}``.

    Returns:
        dict: Complete settings.

    Raises:
        ValueError: If ``overrides`` contains unknown keys.

    """
    settings = dict(DEFAULT_SETTINGS)
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(DEFAULT_SETTINGS))
    if unknown:
        raise ValueError("Unknown validation settings: {0}".format(", ".join(unknown)))
    settings.update(overrides)
    return settings


def check_control_values(rig, settings):
    """Flag controls that are not at their rest values.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings.

    Returns:
        list: :class:`Issue` per control with offset channels.

    """
    issues = []
    rest = settings["rest_values"]
    tolerance = settings["tolerance"]
    for control in rig.get("controls", []):
        values = control.get("values", {})
        dirty = [
            "{0}={1:g}".format(channel, values[channel])
            for channel, expected in rest.items()
            if channel in values and abs(values[channel] - expected) > tolerance
        ]
        if dirty:
            issues.append(Issue(
                "control_values", ERROR, control["name"],
                "Not at rest: {0}".format(", ".join(dirty)),
            ))
    return issues


def check_locked_channels(rig, settings):
    """Flag controls whose required channels are still animatable.

    A channel counts as safe if it is locked or not keyable.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings.

    Returns:
        list: :class:`Issue` per control with open channels.

    """
    issues = []
    for control in rig.get("controls", []):
        locked = set(control.get("locked", []))
        keyable = set(control.get("keyable", []))
        open_channels = [
            channel for channel in settings["require_locked"]
            if channel not in locked and channel in keyable
        ]
        if open_channels:
            issues.append(Issue(
                "locked_channels", WARNING, control["name"],
                "Channels should be locked: {0}".format(", ".join(open_channels)),
            ))
    return issues


def check_unused_joints(rig, settings):
    """Flag deform joints that no skin cluster uses as an influence.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings.

    Returns:
        list: :class:`Issue` per unused deform joint.

    """
    used = set()
    for cluster in rig.get("skin_clusters", []):
        used.update(cluster.get("influences", []))
    ignore = [re.compile(p) for p in settings["ignore_joints"]]

    issues = []
    for joint in rig.get("joints", []):
        name = joint["name"]
        if not joint.get("deform", True) or name in used:
            continue
        if any(p.search(name) for p in ignore):
            continue
        issues.append(Issue(
            "unused_joints", WARNING, name, "Deform joint is not a skin influence.",
        ))
    return issues


def check_max_influences(rig, settings):
    """Flag skin clusters with too many influences on a single vertex.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings.

    Returns:
        list: :class:`Issue` per offending skin cluster.

    """
    limit = settings["max_influences"]
    issues = []
    for cluster in rig.get("skin_clusters", []):
        found = cluster.get("max_influences_found", 0)
        if found > limit:
            issues.append(Issue(
                "max_influences", ERROR, cluster["name"],
                "{0} has vertices with {1} influences (limit {2}).".format(
                    cluster.get("geometry", "?"), found, limit
                ),
            ))
    return issues


def check_naming(rig, settings):
    """Flag controls and joints that break the naming convention.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings.

    Returns:
        list: :class:`Issue` per badly named node.

    """
    issues = []
    groups = (
        ("controls", settings["control_pattern"]),
        ("joints", settings["joint_pattern"]),
    )
    for key, pattern in groups:
        regex = re.compile(pattern)
        for item in rig.get(key, []):
            if not regex.match(item["name"]):
                issues.append(Issue(
                    "naming", WARNING, item["name"],
                    "Name does not match {0} pattern {1}".format(key, pattern),
                ))
    return issues


def check_unique_names(rig, settings):
    """Flag short names used by more than one control or joint.

    Args:
        rig (dict): Rig description.
        settings (dict): Validation settings (unused).

    Returns:
        list: :class:`Issue` per clashing name.

    """
    seen = {}
    for key in ("controls", "joints"):
        for item in rig.get(key, []):
            short = item["name"].split("|")[-1]
            seen[short] = seen.get(short, 0) + 1
    return [
        Issue("unique_names", ERROR, name, "Name is used {0} times.".format(count))
        for name, count in sorted(seen.items())
        if count > 1
    ]


RULES = {
    "control_values": check_control_values,
    "locked_channels": check_locked_channels,
    "unused_joints": check_unused_joints,
    "max_influences": check_max_influences,
    "naming": check_naming,
    "unique_names": check_unique_names,
}


def run(rig, settings=None, rules=None):
    """Run validation rules over a rig description.

    Args:
        rig (dict): Rig description.
        settings (dict): Overrides for :data:`DEFAULT_SETTINGS`.
        rules (list): Rule names to run; all rules when None.

    Returns:
        list: All :class:`Issue` objects, errors first, then by rule and node.

    Raises:
        ValueError: If a rule name is unknown or the rig is not a dict.

    """
    if not isinstance(rig, dict):
        raise ValueError("Rig description must be a dict.")
    names = list(RULES) if rules is None else list(rules)
    unknown = [name for name in names if name not in RULES]
    if unknown:
        raise ValueError("Unknown rules: {0}".format(", ".join(unknown)))
    resolved = merged_settings(settings)

    issues = []
    for name in names:
        issues.extend(RULES[name](rig, resolved))
    return sorted(issues, key=lambda i: (i.severity != ERROR, i.rule, i.node))
