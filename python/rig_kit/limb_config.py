"""Load and validate the YAML file that describes limbs for IK/FK matching.

The config maps each limb to the control and node names of a particular rig,
so the same matching code works on mGear rigs or any hand-built rig. See
``config/limbs_mgear_biped.yaml`` for a full example.

"""

import dataclasses
import os

from rig_kit import vecmath

REQUIRED_KEYS = ("blend_attr", "chain", "fk", "ik", "pole")
OPTIONAL_KEYS = (
    "ik_value", "fk_value", "aim_axis", "up_axis", "pole_distance",
    "match_ik_rotation",
)


@dataclasses.dataclass(frozen=True)
class LimbSpec:
    """Names and settings for one two-bone limb.

    Attributes:
        name (str): Limb name, e.g. ``"arm_L"``.
        blend_attr (str): ``node.attr`` that switches between IK and FK.
        chain (tuple): Three nodes that follow the limb in both modes
            (usually the deform or blend joints): root, mid, end.
        fk (tuple): Three FK controls: upper, lower, end.
        ik (str): IK handle control.
        pole (str): Pole vector control.
        ik_value (float): ``blend_attr`` value meaning IK.
        fk_value (float): ``blend_attr`` value meaning FK.
        aim_axis (str): FK control axis that runs down the bone.
        up_axis (str): FK control axis that points at the pole side.
        pole_distance (float): Pole offset from the mid joint, or None for
            half the chain length.
        match_ik_rotation (bool): Rotate the IK control to the end joint.

    """

    name: str
    blend_attr: str
    chain: tuple
    fk: tuple
    ik: str
    pole: str
    ik_value: float = 1.0
    fk_value: float = 0.0
    aim_axis: str = "x"
    up_axis: str = "y"
    pole_distance: float = None
    match_ik_rotation: bool = True


def load(path):
    """Read a limb config file.

    Args:
        path (str): Path to a YAML file with a top-level ``limbs`` mapping.

    Returns:
        dict: Limb name to :class:`LimbSpec`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the content is invalid.

    """
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing limb config: {0}".format(path))
    # Imported here so parse() and find_limb() work in a Maya without PyYAML.
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return parse(data)


def parse(data):
    """Validate a config mapping and build limb specs.

    Args:
        data (dict): Parsed YAML with a ``limbs`` mapping.

    Returns:
        dict: Limb name to :class:`LimbSpec`.

    Raises:
        ValueError: If a limb is missing keys or has malformed values.

    """
    limbs = data.get("limbs") if isinstance(data, dict) else None
    if not isinstance(limbs, dict) or not limbs:
        raise ValueError("Limb config needs a non-empty 'limbs' mapping.")
    return {name: _parse_limb(name, entry) for name, entry in limbs.items()}


def _parse_limb(name, entry):
    """Build one :class:`LimbSpec`, raising on bad entries."""
    if not isinstance(entry, dict):
        raise ValueError("Limb '{0}' must be a mapping.".format(name))
    missing = [key for key in REQUIRED_KEYS if key not in entry]
    if missing:
        raise ValueError("Limb '{0}' is missing: {1}".format(name, ", ".join(missing)))
    unknown = sorted(set(entry) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise ValueError("Limb '{0}' has unknown keys: {1}".format(name, ", ".join(unknown)))

    for key in ("chain", "fk"):
        if not isinstance(entry[key], (list, tuple)) or len(entry[key]) != 3:
            raise ValueError("Limb '{0}': '{1}' needs exactly 3 names.".format(name, key))
    if "." not in entry["blend_attr"]:
        raise ValueError(
            "Limb '{0}': blend_attr must be 'node.attr', got '{1}'".format(
                name, entry["blend_attr"]
            )
        )

    spec = LimbSpec(
        name=name,
        blend_attr=entry["blend_attr"],
        chain=tuple(entry["chain"]),
        fk=tuple(entry["fk"]),
        ik=entry["ik"],
        pole=entry["pole"],
        ik_value=float(entry.get("ik_value", 1.0)),
        fk_value=float(entry.get("fk_value", 0.0)),
        aim_axis=entry.get("aim_axis", "x"),
        up_axis=entry.get("up_axis", "y"),
        pole_distance=entry.get("pole_distance"),
        match_ik_rotation=bool(entry.get("match_ik_rotation", True)),
    )
    _check_axes(spec)
    return spec


def _check_axes(spec):
    """Raise if the aim and up axes are unknown or the same."""
    try:
        _, aim = vecmath.parse_axis(spec.aim_axis)
        _, up = vecmath.parse_axis(spec.up_axis)
    except ValueError as error:
        raise ValueError("Limb '{0}': {1}".format(spec.name, error)) from error
    if aim == up:
        raise ValueError("Limb '{0}': aim_axis and up_axis must differ.".format(spec.name))


def find_limb(limbs, node):
    """Return the limb that a selected node belongs to.

    Matches FK, IK, pole and chain nodes and the node that holds the blend
    attribute. A namespace on the selected node (a referenced rig) is added
    to every name of the returned spec.

    Args:
        limbs (dict): Limb name to :class:`LimbSpec`, from ``load``.
        node (str): Selected node, short name or DAG path.

    Returns:
        LimbSpec: The matching limb, or None when nothing matches.

    """
    short = node.rsplit("|", 1)[-1]
    namespace, _, bare = short.rpartition(":")
    for spec in limbs.values():
        names = set(spec.chain) | set(spec.fk) | {spec.ik, spec.pole}
        names.add(spec.blend_attr.split(".", 1)[0])
        if bare in names:
            return with_namespace(spec, namespace) if namespace else spec
    return None


def with_namespace(spec, namespace):
    """Return a copy of a limb with every node name in a namespace.

    Args:
        spec (LimbSpec): Limb with plain names.
        namespace (str): Namespace without the trailing colon, e.g. ``"hero"``.

    Returns:
        LimbSpec: The namespaced copy.

    """

    def _name(name):
        return "{0}:{1}".format(namespace, name)

    return dataclasses.replace(
        spec,
        blend_attr=_name(spec.blend_attr),
        chain=tuple(_name(name) for name in spec.chain),
        fk=tuple(_name(name) for name in spec.fk),
        ik=_name(spec.ik),
        pole=_name(spec.pole),
    )
