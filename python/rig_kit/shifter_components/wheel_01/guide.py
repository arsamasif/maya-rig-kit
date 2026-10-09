"""Guide for the ``wheel_01`` mGear Shifter component.

Two locators: ``root`` at the wheel centre and ``rim`` on the tyre surface.
The distance between them is the rolling radius. The root's X axis is the
axle and its Z axis is the driving direction, so orient the root guide the
way the vehicle drives.

"""

from functools import partial

from maya.app.general.mayaMixin import MayaQDockWidget
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from mgear.core import pyqt
from mgear.core import transform
from mgear.shifter.component import guide
from mgear.vendor.Qt import QtCore
from mgear.vendor.Qt import QtWidgets

AUTHOR = "Arsam Ali"
URL = ""
EMAIL = ""
VERSION = [1, 0, 0]
TYPE = "wheel_01"
NAME = "wheel"
DESCRIPTION = (
    "Wheel with automatic roll from travel distance. A main control moves "
    "and steers the wheel, a spin control adds manual roll on top."
)


class Guide(guide.ComponentGuide):
    """Guide placement and settings for the wheel component."""

    compType = TYPE
    compName = NAME
    description = DESCRIPTION

    author = AUTHOR
    url = URL
    email = EMAIL
    version = VERSION

    def postInit(self):
        """Declare the guide locators that get saved with the template."""
        self.save_transform = ["root", "rim"]

    def addObjects(self):
        """Create the root and rim locators and a display curve."""
        self.root = self.addRoot()
        rim_position = transform.getOffsetPosition(self.root, [0, 1, 0])
        self.rim = self.addLoc("rim", self.root, rim_position)
        self.dispcrv = self.addDispCurve("crv", [self.root, self.rim])

    def addParameters(self):
        """Add the settings stored on the guide root."""
        self.pAutoRoll = self.addParam("autoRoll", "bool", True)
        self.pRollDirection = self.addParam("rollDirection", "double", 1.0, -1.0, 1.0)
        self.pIconScale = self.addParam("iconScale", "double", 1.2, 0.01, None)


class settingsTab(QtWidgets.QDialog):
    """Component-specific settings page shown in the guide settings window."""

    def __init__(self, parent=None):
        super(settingsTab, self).__init__(parent)
        self.autoRoll_checkBox = QtWidgets.QCheckBox("Auto roll from travel")
        self.reverse_checkBox = QtWidgets.QCheckBox("Reverse roll direction")
        self.iconScale_spinBox = QtWidgets.QDoubleSpinBox()
        self.iconScale_spinBox.setRange(0.01, 100.0)
        self.iconScale_spinBox.setSingleStep(0.1)

        layout = QtWidgets.QFormLayout(self)
        layout.addRow(self.autoRoll_checkBox)
        layout.addRow(self.reverse_checkBox)
        layout.addRow("Icon scale", self.iconScale_spinBox)


class componentSettings(MayaQWidgetDockableMixin, guide.componentMainSettings):
    """Guide settings window for ``wheel_01``."""

    def __init__(self, parent=None):
        self.toolName = TYPE
        pyqt.deleteInstances(self, MayaQDockWidget)
        super(componentSettings, self).__init__(parent=parent)
        self.settingsTab = settingsTab()

        self.setup_componentSettingWindow()
        self.create_componentControls()
        self.populate_componentControls()
        self.create_componentLayout()
        self.create_componentConnections()

    def setup_componentSettingWindow(self):
        """Configure the window frame."""
        self.mayaMainWindow = pyqt.maya_main_window()
        self.setObjectName(self.toolName)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(TYPE)
        self.resize(280, 350)

    def create_componentControls(self):
        """No extra widgets beyond the settings tab."""
        return

    def populate_componentControls(self):
        """Fill the widgets from the guide root attributes."""
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")
        self.populateCheck(self.settingsTab.autoRoll_checkBox, "autoRoll")
        reverse = self.root.attr("rollDirection").get() < 0
        self.settingsTab.reverse_checkBox.setChecked(reverse)
        self.settingsTab.iconScale_spinBox.setValue(self.root.attr("iconScale").get())

    def create_componentLayout(self):
        """Stack the tabs and the close button."""
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)
        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        """Write widget changes back to the guide root."""
        self.settingsTab.autoRoll_checkBox.stateChanged.connect(
            partial(self.updateCheck, self.settingsTab.autoRoll_checkBox, "autoRoll")
        )
        self.settingsTab.reverse_checkBox.stateChanged.connect(self._update_direction)
        self.settingsTab.iconScale_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.iconScale_spinBox, "iconScale")
        )

    def _update_direction(self, *args):
        """Store the roll direction as +1 or -1."""
        reverse = self.settingsTab.reverse_checkBox.isChecked()
        self.root.attr("rollDirection").set(-1.0 if reverse else 1.0)

    def dockCloseEventTriggered(self):
        """Clean up the dock widget when the window closes."""
        pyqt.deleteInstances(self, MayaQDockWidget)
