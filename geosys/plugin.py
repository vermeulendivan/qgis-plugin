# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeosysPlugin
                                 A QGIS plugin
 Discover, request and use aggregate imagery products based on landsat-8,
 Sentinel 2 and other sensors from within QGIS, using the GEOSYS API.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-03-11
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Kartoza (Pty) Ltd
        email                : andre@kartoza.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os.path

from PyQt5.QtCore import (
    QSettings, QTranslator, qVersion, QCoreApplication, Qt)
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction

from qgis.core import QgsApplication

from geosys.processing.geosys_processing_provider import (
    GeosysProcessingProvider)
from geosys.utilities.resources import resources_path


class GeosysPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GeosysPlugin_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&GEOSYS Plugin')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'GeosysPlugin')
        self.toolbar.setObjectName(u'GeosysPlugin')

        # print "** INITIALIZING GeosysPlugin"

        self.plugin_active = False
        self.dock_widget = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GeosysPlugin', message)

    def add_action(self, action, add_to_toolbar=True):
        """Add a toolbar icon to the GEOSYS toolbar.

        :param action: The action that should be added to the toolbar.
        :type action: QAction

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the GEOSYS toolbar. Defaults to True.
        :type add_to_toolbar: bool
        """
        # store in the class list of actions for easy plugin unloading
        self.actions.append(action)
        self.iface.addPluginToMenu(self.menu, action)
        if add_to_toolbar:
            self.toolbar.addAction(action)

    def _create_dock_toggle_action(self):
        """Create action for plugin dockable window (show/hide)."""
        # pylint: disable=W0201
        icon = resources_path('img', 'icons', 'icon.png')
        self.action_dock = QAction(
            QIcon(icon),
            self.tr('Toggle GEOSYS Dock'),
            self.iface.mainWindow())
        self.action_dock.setStatusTip(self.tr(
            'Show/hide GEOSYS dock widget'))
        self.action_dock.setWhatsThis(self.tr(
            'Show/hide GEOSYS dock widget'))
        self.action_dock.setCheckable(True)
        self.action_dock.setChecked(True)
        self.action_dock.triggered.connect(self.toggle_dock_visibility)
        self.add_action(self.action_dock)

    def _create_options_dialog_action(self):
        """Create action for options dialog."""
        icon = resources_path('img', 'icons', 'icon.png')
        self.action_options = QAction(
            QIcon(icon),
            self.tr('Options'), self.iface.mainWindow())
        self.action_options.setStatusTip(self.tr(
            'Open GEOSYS options dialog'))
        self.action_options.setWhatsThis(self.tr(
            'Open GEOSYS options dialog'))
        self.action_options.triggered.connect(self.show_options)
        self.add_action(self.action_options, add_to_toolbar=False)

    def _create_dock(self):
        """Create GEOSYS dock widget."""
        if self.dock_widget is None:
            # Create the dockwidget (after translation) and keep reference
            from geosys.ui.widgets.geosys_dockwidget import (
                GeosysPluginDockWidget)
            self.dock_widget = GeosysPluginDockWidget(self.iface)

        # connect to provide cleanup on closing of dock widget
        self.dock_widget.closingPlugin.connect(self.onClosePlugin)

        # show the dock widget
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.show()

    def initProcessing(self):
        """Processing initialisation procedure (for QGIS plugin api).

        This method is called by initGui and should be used to set up
        any processing tools that should appear in QGIS by
        default (i.e. before the user performs any explicit action with the
        plugin).
        """
        self.provider = GeosysProcessingProvider()
        QgsApplication.processingRegistry().addProvider(
            self.provider)

    def initGui(self):
        """Gui initialisation procedure (for QGIS plugin api).

        .. note:: Don't change the name of this method from initGui!

        This method is called by QGIS and should be used to set up
        any graphical user interface elements that should appear in QGIS by
        default (i.e. before the user performs any explicit action with the
        plugin).
        """

        self._create_dock()
        self._create_dock_toggle_action()
        self._create_options_dialog_action()

        # Hook up a slot for when the dock is hidden using its close button
        # or  view-panels
        #
        self.dock_widget.visibilityChanged.connect(self.toggle_geosys_action)
        # Also deal with the fact that on start of QGIS dock may already be
        # hidden.
        self.action_dock.setChecked(self.dock_widget.isVisible())

        # Add custom processing tools
        self.initProcessing()

    # ---------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dock widget is closed"""

        # print "** CLOSING GeosysPlugin"

        # disconnects
        self.dock_widget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dock widget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashes
        # when closing the docked window:
        # self.dock_widget = None

        self.plugin_active = False

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        # print "** UNLOAD GeosysPlugin"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&GEOSYS Plugin'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    # ---------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.plugin_active:
            self.plugin_active = True

            # print "** STARTING GeosysPlugin"

            # dock widget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dock_widget is None:
                # Create the dock widget (after translation) and keep reference
                from geosys.ui.widgets.geosys_dockwidget import (
                    GeosysPluginDockWidget)
                self.dock_widget = GeosysPluginDockWidget()

            # connect to provide cleanup on closing of dock widget
            self.dock_widget.closingPlugin.connect(self.onClosePlugin)

            # show the dock widget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.show()

    def toggle_geosys_action(self, checked):
        """Check or un-check the toggle GEOSYS toolbar button.

        This slot is called when the user hides the GEOSYS panel using its
        close button or using view->panels.

        :param checked: True if the dock should be shown, otherwise False.
        :type checked: bool
        """
        self.action_dock.setChecked(checked)

    def toggle_dock_visibility(self):
        """Show or hide the dock widget."""
        if self.dock_widget.isVisible():
            self.dock_widget.setVisible(False)
        else:
            self.dock_widget.setVisible(True)
            self.dock_widget.raise_()

    def populate_map_products(self):
        """Obtain a list of map products from Bridge API definition.
        If the US zone has been selected the soil option will be included, otherwise excluded.
        """
        self.dock_widget.populate_map_products()

    def show_options(self):
        """Show the options dialog."""
        # import here only so that it is AFTER i18n set up
        from geosys.ui.widgets.options_dialog import GeosysOptionsDialog

        dialog = GeosysOptionsDialog(
            self.iface, parent=self.iface.mainWindow())
        if dialog.exec_():  # modal
            # Repopulates the maptypes combobox if the user clicked OK
            self.populate_map_products()
            pass
