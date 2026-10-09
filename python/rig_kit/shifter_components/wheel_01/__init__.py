"""mGear Shifter component ``wheel_01``: a wheel that rolls as it travels.

Hierarchy built under the component root::

    root
    └── ik_cns
        └── ctl              (move / steer the wheel)
            └── roll_npo     (auto roll from travel distance)
                └── spin_ctl (manual roll on top, drives the joint)

The auto roll is a scrubbable node network: the wheel's displacement from its
build position is projected onto its forward axis and divided by the radius
(see :mod:`rig_kit.wheel_math`, which holds the same math in pure Python).

"""

from maya import cmds
from mgear.core import attribute
from mgear.core import primitive
from mgear.core import transform
from mgear.core import vector
from mgear.shifter import component

from rig_kit import wheel_math

try:
    from mgear.pymaya import datatypes
except ImportError:  # mGear 4.x ships with pymel
    from pymel.core import datatypes

QUARTER_TURN = 1.5707963267948966
FORWARD_AXIS = (0.0, 0.0, 1.0)


class Component(component.Main):
    """Build, attributes and node network for the wheel."""

    def addObjects(self):
        """Create the controls and the joint placement."""
        self.radius = vector.getDistance(self.guide.apos[0], self.guide.apos[1])
        size = self.radius * 2.0 * self.settings["iconScale"]
        t = transform.setMatrixScale(self.guide.tra["root"])

        self.ik_cns = primitive.addTransform(self.root, self.getName("ik_cns"), t)
        self.ctl = self.addCtl(
            self.ik_cns, "ctl", t, self.color_ik, "square",
            w=size, d=size, tp=self.parentCtlTag,
        )
        attribute.setKeyableAttributes(
            self.ctl, ["tx", "ty", "tz", "rx", "ry", "rz", "ro"]
        )

        self.roll_npo = primitive.addTransform(self.ctl, self.getName("roll_npo"), t)
        self.spin_ctl = self.addCtl(
            self.roll_npo, "spin_ctl", t, self.color_fk, "circle",
            w=size, ro=datatypes.Vector(0, 0, QUARTER_TURN), tp=self.ctl,
        )
        attribute.setKeyableAttributes(self.spin_ctl, ["rx"])

        self.jnt_pos.append([self.spin_ctl, "0"])

    def addAttributes(self):
        """Add animator-facing attributes on the UI host."""
        auto_default = 1.0 if self.settings["autoRoll"] else 0.0
        self.auto_att = self.addAnimParam(
            "autoRoll", "Auto Roll", "double", auto_default, 0.0, 1.0
        )
        self.radius_att = self.addAnimParam(
            "radius", "Radius", "double", self.radius, 0.001
        )

    def addOperators(self):
        """Drive ``roll_npo.rotateX`` from distance travelled along forward."""
        world_matrix = "{0}.worldMatrix[0]".format(self.ctl)

        position = cmds.createNode("decomposeMatrix", name=self.getName("pos_dm"))
        cmds.connectAttr(world_matrix, position + ".inputMatrix")

        offset = cmds.createNode("plusMinusAverage", name=self.getName("offset_pma"))
        cmds.setAttr(offset + ".operation", 2)  # subtract
        cmds.connectAttr(position + ".outputTranslate", offset + ".input3D[0]")
        rest = [float(v) for v in self.guide.apos[0]]
        cmds.setAttr(offset + ".input3D[1]", *rest, type="double3")

        forward = cmds.createNode("vectorProduct", name=self.getName("forward_vp"))
        cmds.setAttr(forward + ".operation", 3)  # vector matrix product
        cmds.setAttr(forward + ".input1", *FORWARD_AXIS, type="double3")
        cmds.setAttr(forward + ".normalizeOutput", True)
        cmds.connectAttr(world_matrix, forward + ".matrix")

        travel = cmds.createNode("vectorProduct", name=self.getName("travel_vp"))
        cmds.setAttr(travel + ".operation", 1)  # dot product
        cmds.connectAttr(offset + ".output3D", travel + ".input1")
        cmds.connectAttr(forward + ".output", travel + ".input2")

        per_radius = cmds.createNode("multiplyDivide", name=self.getName("radius_md"))
        cmds.setAttr(per_radius + ".operation", 2)  # divide
        cmds.connectAttr(travel + ".outputX", per_radius + ".input1X")
        cmds.connectAttr(str(self.radius_att), per_radius + ".input2X")

        degrees = cmds.createNode("multDoubleLinear", name=self.getName("degrees_mdl"))
        factor = wheel_math.degrees_per_unit(1.0) * self.settings["rollDirection"]
        cmds.connectAttr(per_radius + ".outputX", degrees + ".input1")
        cmds.setAttr(degrees + ".input2", factor)

        blend = cmds.createNode("multDoubleLinear", name=self.getName("auto_mdl"))
        cmds.connectAttr(degrees + ".output", blend + ".input1")
        cmds.connectAttr(str(self.auto_att), blend + ".input2")
        cmds.connectAttr(blend + ".output", "{0}.rotateX".format(self.roll_npo))

    def setRelation(self):
        """Map guide locators to the objects other components attach to."""
        self.relatives["root"] = self.ctl
        self.relatives["rim"] = self.spin_ctl
        self.controlRelatives["root"] = self.ctl
        self.controlRelatives["rim"] = self.spin_ctl
        self.jointRelatives["root"] = 0
        self.jointRelatives["rim"] = 0
        self.aliasRelatives["root"] = "ctl"
        self.aliasRelatives["rim"] = "spin"

    def addConnection(self):
        """Register the connection types this component supports."""
        self.connections["standard"] = self.connect_standard

    def connect_standard(self):
        """Parent the component root under its parent component."""
        self.parent.addChild(self.root)
