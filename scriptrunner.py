"""
ScriptRunner - A QGIS plugin that runs scripts to automate QGIS tasks.

Date: 2012-01-27
Copyright: (C) 2012 by GeoApt LLC
Email: gsherman@geoapt.com


This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

"""

import sys
import traceback
import os
import platform
import subprocess
import re
import inspect
import datetime
if platform.system() == 'Windows':
    import win32api

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
#from qgis import console
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from scriptrunner_mainwindow import ScriptRunnerMainWindow
# Import the preferenes dialog
from preferences_dialog import PreferencesDialog
# Import the traceback dialog
from traceback_dialog import TracebackDialog
# Import the stdout dialog
from stdout_textwidget import StdoutTextEdit
# Import the help module
from scriptrunner_help import *
#from highlighter import *
from syntax import *
# ars dialog
from argsdialog import ArgsDialog

# for remote pydev debug (remove prior to production)
#import debug_settings


class ScriptRunner:

    """
    ScriptRunner is the main plugin class that initializes the QGIS
    plugin, initializes the GUI, and performs the work.
    """

    def __init__(self, iface):
        """
        Save reference to the QGIS interface
        """
        self.iface = iface

        self.settings = QSettings()
        self.fetch_settings()
        if self.log_output:
            # open the logfile using mode based on user preference

            if self.log_overwrite:
                mode = 'w'
            else:
                mode = 'a'

            self.log_file = open(os.path.join(str(self.log_dir),
                                              "scriptrunner.log"), mode)
        self.last_args = ''

        self.plugin_dir = QFileInfo(
            QgsApplication.qgisUserDbFilePath()).path() + \
            "/python/plugins/scriptrunner"



    def initGui(self):
        """
        Initialize the GUI elements and menu/tool
        on the QGIS Plugins toolbar.
        """
        # create the mainwindow
        self.mw = ScriptRunnerMainWindow()
        self.mw.setWindowTitle("Script Runner Version 0.7")
        self.restore_window_position()
        # fetch the list of stored scripts from user setting
        stored_scripts = self.settings.value("ScriptRunner/scripts")
        self.list_of_scripts = stored_scripts.toList()

        # Create action that will start plugin configuration
        self.action = QAction(QIcon(":/plugins/scriptrunner/icon.png"),
                              "ScriptRunner", self.iface.mainWindow())
        # connect the action to the run method
        self.action.triggered.connect(self.run)

#        # Add toolbar button and menu item
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&ScriptRunner", self.action)

        self.main_window = self.mw.ui

        self.toolbar = self.main_window.toolBar
        self.toolbar.setIconSize(QSize(30,30))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        #self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        ## Action setup
        # action for adding a script
        self.add_action = QAction(QIcon(":plugins/scriptrunner/add_icon"),
                                  "Add Script", self.mw)
        self.toolbar.addAction(self.add_action)
        self.add_action.triggered.connect(self.add_script)

        # action for running a script
        self.run_action = QAction(QIcon(":plugins/scriptrunner/run_icon"),
                                  "Run Script", self.mw)
        self.toolbar.addAction(self.run_action)
        self.run_action.triggered.connect(self.dispatch_script)

        # action for running a script with arguments
        #self.run_with_args_action = QAction(QIcon(":plugins/scriptrunner/run_args_icon"),
        #                                    "Run script with arguments", self.mw)
        #self.toolbar.addAction(self.run_with_args_action)
        #self.run_with_args_action.triggered.connect(self.run_with_args)

        # action for getting info about a script
        self.info_action = QAction(QIcon(":plugins/scriptrunner/info_icon"),
                                   "Script Info", self.mw)
        self.toolbar.addAction(self.info_action)
        self.info_action.triggered.connect(self.info)

        # action for reloading a script
        self.reload_action = QAction(QIcon(
            ":plugins/scriptrunner/reload_icon"),
            "Reload Script", self.mw)
        self.toolbar.addAction(self.reload_action)
        self.reload_action.triggered.connect(self.reload_script)

        # action for removing a script
        self.remove_action = QAction(QIcon(
            ":plugins/scriptrunner/cancel_icon"),
            "Remove Script", self.mw)
        self.toolbar.addAction(self.remove_action)
        self.remove_action.triggered.connect(self.remove_script)

        # action for clear console
        self.clear_action = QAction(QIcon(":plugins/scriptrunner/clear_icon"),
                                    "Clear Console", self.mw)
        self.toolbar.addAction(self.clear_action)
        self.clear_action.triggered.connect(self.sweep_console)

        # action for setting prevferences
        self.prefs_action = QAction(QIcon(":plugins/scriptrunner/prefs_icon"),
                                    "Preferences", self.mw)
        self.toolbar.addAction(self.prefs_action)
        self.prefs_action.triggered.connect(self.set_preferences)

        # action for opening help
        self.help_action = QAction(QIcon(":plugins/scriptrunner/help_icon"),
                                    "Help", self.mw)
        self.toolbar.addAction(self.help_action)
        self.help_action.triggered.connect(self.open_help)

        # action for closing ScriptRunner
        self.exit_action = QAction(QIcon(":plugins/scriptrunner/exit_icon"),
                                   "Close", self.mw)
        self.toolbar.addAction(self.exit_action)
        self.exit_action.triggered.connect(self.close_window)

        self.toggle_console_action = QAction(
            QIcon(":/plugins/scriptrunner/toggle_icon"),
            "Toggle Console", self.mw)
        self.toggle_console_action.triggered.connect(self.toggle_console)

        self.edit_action = QAction(
            QIcon(":/plugins/scriptrunner/edit_icon"),
            "Edit script in external editor", self.mw)
        self.edit_action.triggered.connect(self.edit_script)

        # setup the splitter and list/text browser and mainwindow layout
        self.layout = QHBoxLayout(self.main_window.frame)
        self.splitter = QSplitter(self.main_window.frame)
        self.layout.addWidget(self.splitter)

        self.scriptList = QListWidget()
        # connect double click to info slot
        #self.scriptList.itemDoubleClicked.connect(self.item_info)
        self.scriptList.currentItemChanged.connect(self.current_script_changed)
        self.scriptList.customContextMenuRequested.connect(
            self.show_context_menu)
        self.scriptList.setContextMenuPolicy(Qt.CustomContextMenu)
        ## Context menu for the scriptList
        self.context_menu = QMenu(self.scriptList)
        self.context_menu.addAction(self.run_action)
        #self.context_menu.addAction(self.run_with_args_action)
        self.context_menu.addAction(self.remove_action)
        self.context_menu.addAction(self.reload_action)
        self.context_menu.addAction(self.edit_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.clear_action)
        self.context_menu.addAction(self.toggle_console_action)

        self.splitter.addWidget(self.scriptList)

        self.tabWidget = QTabWidget()

        self.textBrowser = QTextBrowser()
        self.tabWidget.addTab(self.textBrowser, "Info")

        self.textBrowserSource = QTextBrowser()
        self.tabWidget.addTab(self.textBrowserSource, "Source")
        highlighter = PythonHighlighter(self.textBrowserSource.document())

        #self.textBrowserHelp = QTextBrowser()
        #self.textBrowserHelp.setSearchPaths(["%s/doc" % self.plugin_dir])
        #help_url = QUrl("file:///%s/doc/index.html" % self.plugin_dir)
        #self.textBrowserHelp.setSource(help_url)
        ##self.textBrowserHelp.setHtml(htmlhelp())
        #self.tabWidget.addTab(self.textBrowserHelp, "Help")

        self.textBrowserAbout = QTextBrowser()
        self.textBrowserAbout.setHtml(htmlabout())
        self.textBrowserAbout.setOpenExternalLinks(True)
        self.tabWidget.addTab(self.textBrowserAbout, "About")

        self.tabWidget.setMinimumHeight(320)

        self.splitter.addWidget(self.tabWidget)
        # set the sizes for the splitter
        split_size = [150, 350]
        self.splitter.setSizes(split_size)

        # set up the stdout dock
        self.stdout_dock = QDockWidget(self.mw)
        self.stdout_dock.setWindowTitle("Script Runner - Output Console")
        self.stdout_textedit = StdoutTextEdit()
        self.stdout_dock.setWidget(self.stdout_textedit)
        self.mw.addDockWidget(Qt.BottomDockWidgetArea, self.stdout_dock)

        # cursor for the StdoutTextEdit
        self.cursor = QTextCursor(self.stdout_textedit.textCursor())
        self.stdout_textedit.setTextCursor(self.cursor)

        self.configure_console()

        if len(self.list_of_scripts) == 0:
            # make the help tab visible if no scripts are loaded
            self.tabWidget.setCurrentIndex(2)
        else:
            # add the list of scripts fetched from settings
            for script in self.list_of_scripts:
                full_path = str(script.toString())
                (script_dir, script_name) = os.path.split(full_path)
                (has_run_method, uses_args) = self.have_run_method(full_path)
                if has_run_method:
                    if uses_args:
                        script_name += '**'
                    item = QListWidgetItem(script_name, self.scriptList)
                    item.setToolTip(script.toString())
                else:
                    self.stdout_textedit.write(
                        "!!Script %s is missing the run_script method---not loaded!!\n" % full_path)
            self.stdout_textedit.ensureCursorVisible()

        self.scriptList.setCurrentRow(0)

    def unload(self):
        """
        Cleanup the QGIS GUI by removing the plugin menu item and icon.
        """
        self.iface.removePluginMenu("&ScriptRunner", self.action)
        self.iface.removeToolBarIcon(self.action)

    def add_script(self):
        """
        Add a script to the list of scripts that can be executed.
        """
        script = QFileDialog.getOpenFileName(None, "Add a Python Script",
                                             "", "Python scripts (*.py)")
        if script:
            # check to see if we have a run method without importing the script
            run_method_check = self.have_run_method(script)
            if run_method_check[0]:  #self.have_run_method(script):
                (script_dir, script_name) = os.path.split(str(script))
                if run_method_check[1]:
                    script_name += '**'
                item = QListWidgetItem(script_name, self.scriptList)
                item.setToolTip(script)
                self.main_window.statusbar.showMessage(
                    "Added script: %s" % script)
                self.list_of_scripts.append(script)
                self.update_settings()

            else:
                QMessageBox.information(
                    None, "Error",
                    """Your script must have a run_script() function defined.\n
                    Adding the script failed.""")
                self.main_window.statusbar.showMessage(
                    "Failed to add: %s - no run_script function" % script)

    def remove_script(self):
        """
        Remove a script from the list of scripts that can be executed.
        """
        item = self.scriptList.currentItem()
        if item is not None:
            result = QMessageBox.question(
                None, "Remove Script",
                "Are you sure you want to remove %s?" % item.text(),
                QMessageBox.Yes, QMessageBox.No)
            if result == QMessageBox.Yes:
                self.list_of_scripts.pop(
                    self.list_of_scripts.index(item.toolTip()))
                self.update_settings()
                self.scriptList.takeItem(self.scriptList.currentRow())

    def reload_script(self):
        """
        Reload the currently selected script.
        """
        item = self.scriptList.currentItem()
        if item is not None:
            script = item.toolTip()
            (script_dir, script_name) = os.path.split(str(script))
            (user_module, ext) = os.path.splitext(script_name)
            if user_module in sys.modules:
                reload(sys.modules[user_module])
                self.main_window.statusbar.showMessage(
                    "Reloaded script: %s" % script)
                (has_run_method, uses_args) = self.have_run_method(script)
                if has_run_method:
                    # set state of the run with args button
                    #self.run_with_args_action.setEnabled(uses_args)
                    if uses_args:
                        # has keyword args: add ** to the name
                        item.setText("%s**" % script_name)
                    else:
                        item.setText(script_name)
                    self.info()
                else:
                    QMessageBox.warning(
                        None, "Missing run_script",
                        "Your script is now missing the required run_script method")

            else:
                QMessageBox.information(
                    None, "Reload",
                    """The %s script was not reloaded since it hasn't\n
                    been imported yet""" % user_module)

    #def item_info(self, item):
    #    self.info(item)

    def info(self):
        """
        Display information about the script, including the docstring,
        classes, methods, and functions.
        """
        item = self.scriptList.currentItem()
        if item is not None:  # in case no currentitem and none was passed
            script = item.toolTip()
            (script_dir, script_name) = os.path.split(str(script))
            (user_module, ext) = os.path.splitext(script_name)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            if not user_module in sys.modules:
                __import__(user_module)

            # add the doc string to the info page
            doc_string = inspect.getdoc(sys.modules[user_module])
            if doc_string is None:
                doc_string = \
                    "You Have no Docstring. You really should add one..."
            else:
                doc_string = doc_string.replace('\n', '<br>')
            html = "<h4>%s</h4><h4>Doc String:</h4>%s" % (script, doc_string)

            # populate the source tab
            highlighter = PythonHighlighter(self.textBrowserSource.document())
            self.textBrowserSource.setPlainText(self.get_source(script))
            #self.textBrowserSource.setHtml(self.get_source(script))

            classes = inspect.getmembers(
                sys.modules[user_module], inspect.isclass)

            # populate classes and methdods

            html += "<h4>Classes and Methods for %s</h4><ul>" % script_name

            for cls in classes:
                modinfo = inspect.getmodule(cls[1])
                if modinfo:
                    if modinfo.__name__ == user_module:
                        html += "<li>%s</li>" % cls[0]
                        html += "<ul>"
                        for meth in inspect.getmembers(cls[1],
                                                       inspect.ismethod):
                            html += "<li>%s</li>" % meth[0]
                        html += "</ul></ul>"
            functions = inspect.getmembers(
                sys.modules[user_module], inspect.isfunction)
            html += "<h4>Functions in %s</h4><ul>" % script_name
            for func in functions:
                modinfo = inspect.getmodule(func[1])
                if modinfo.__name__ == user_module:
                    html += "<li>%s</li>" % func[0]
            html += "</ul>"

            self.textBrowser.setHtml(html)
            #self.tabWidget.setCurrentIndex(0)

    def get_source(self, script):
        src = open(script, 'r')
        source = src.read()
        src.close()
        return source

    def dispatch_script(self):
        item = self.scriptList.currentItem()
        if item is not None:
            script = str(item.text())
            if script[-2:] == '**':
                self.run_with_args()
            else:
                self.run_script(None)




    def run_with_args(self):
        # get the args
        script_args = self.get_script_args()
        print "script args:"
        print script_args

        if script_args is not None:
            args_dlg = ArgsDialog(self.get_script_args(), self.script_name())
            args = args_dlg.show_dialog()
            if args is not None:
                self.run_script(args)
        else:
            args = None
            QMessageBox.information(
                    None,
                    "No Arguments",
                    """Your script accepts no arguments. Use the Run Script button to run it.""")

        #user_args = QInputDialog.getText(
        #    self.mw, "Script Arguments", 
        #    """Arguments must be specified as key=value pairs with all string values quoted:""",
        #    QLineEdit.Normal, self.last_args)
        #if len(user_args[0]) > 0 and user_args[1]:
        #    self.last_args = user_args[0]
        #    # convert input to a dict
        #    args_list = "dict(%s)" % user_args[0]
        #try:
            #args = eval(args_list)
        #    self.run_script(args)
        #except:
        #    QMessageBox.warning(
        #        None,
        #        "Error in arguments",
        #        """There is an error in your argument list. Arguments must be specified as key=value pairs with all string values quoted.""")


    def run_script(self, user_args):
        """
        Run the currently selected script.
        """
        # get the selected item from the list
        item = self.scriptList.currentItem()
        #settrace()
        if item is not None:
            script = item.toolTip()
            self.main_window.statusbar.showMessage(
                "Running script: %s" % script)

            # get the path and add it to sys.path
            (script_dir, script_name) = os.path.split(str(script))

            if script_dir not in sys.path:
                sys.path.append(script_dir)
            (user_module, ext) = os.path.splitext(script_name)

            user_script = __import__(user_module)

            abnormal_exit = False
            self.last_traceback = ''
            try:
                # grab stdout
                self.old_stdout = sys.stdout
                sys.stdout = self.stdout
                if self.clear_console:
                    self.stdout.setPlainText('')
                print "----------%s----------" % datetime.datetime.now()
                print "Running %s in: %s" % (script_name, script_dir)
                print user_args  # for debug
                print type(user_args)
                if type(user_args) is not dict:
                    user_args = {}
                    user_script.run_script(self.iface)  #, **user_args)
                else:
                    func = "user_script.run_script(self.iface, "
                    #func += ",' ".join(user_args['args'])
                    for ar in user_args['args']:
                        func += "%s, " % ar
                    func = func[:-2]
                    if user_args['keywords'] != None:
                        kwlist = "dict(%s)" % user_args['keywords']
                        kwargs = eval(kwlist)
                        func += ", **kwargs)"
                    else:
                        func += ")"
                    print "func is %s" % func
                    exec(func)

            #except NameError as ne:
            #    tb = TracebackDialog()
            #    tb.ui.teTraceback.setText("""There was an argument error. Did you
            #            forget to quote a string argument?\n%s""" % ne.message)
            except:
                # show traceback
                tb = TracebackDialog()
                tb.ui.teTraceback.setTextColor(QColor(Qt.red))
                self.last_traceback = traceback.format_exc()
                tb.ui.teTraceback.setText(traceback.format_exc())
                tb.show()
                tb.exec_()
                abnormal_exit = True
                print "\n%s\nAbnormal termination" % self.last_traceback
                #QMessageBox.information(None, "Error", traceback.format_exc())
            finally:
                print "Completed script: %s" % script_name
                sys.stdout = self.old_stdout
                if self.log_output:
                    self.log_file.flush()

            self.main_window.statusbar.showMessage(
                "Completed script: %s" % script_name)

    def run(self):
        """
        Bring up the main window.
        """
        self.mw.show()

    def have_run_method(self, script_path):
        """
        Parse the script to make sure it has a run_script function
        before allowing it to be added to the list of scripts.
        """
        script = open(script_path, 'r')
        pattern = re.compile('\s*def run_script\(*')
        run_method = False
        uses_args = False
        for line in script:
            if pattern.search(line):
                run_method = True
                # check to see if this script uses keyword args
                parts = line.split(',')
                if len(parts) > 1:
                    #uses_args =  line.find('**') != -1
                    uses_args = True
                    break
        script.close()
        return run_method, uses_args

    def current_script_changed(self):
        # check to see if it uses args
        item = self.scriptList.currentItem()
        label = str(item.text())
        #self.run_with_args_action.setEnabled(label[-2:] == "**")

        if self.auto_display:
            self.info()

    def update_settings(self):
        """
        Update the setting for the plugin---at present just
        the list of scripts.
        """
        self.settings.setValue("ScriptRunner/scripts",
                               QVariant(self.list_of_scripts))

    def sweep_console(self):
        self.stdout_textedit.setPlainText('')

    def set_preferences(self):
        prefs_dlg = PreferencesDialog()
        prefs_dlg.show()
        if prefs_dlg.exec_() == QDialog.Accepted:
            self.fetch_settings()
            self.configure_console()

    def fetch_settings(self):
        self.auto_display = self.settings.value(
            "ScriptRunner/auto_display", True).toBool()
        self.clear_console = self.settings.value(
            "ScriptRunner/clear_console", True).toBool()
        self.show_console = self.settings.value(
            "ScriptRunner/show_console", True).toBool()
        self.log_output = self.settings.value(
            "ScriptRunner/log_output_to_disk", False).toBool()
        self.log_dir = self.settings.value(
            "ScriptRunner/log_directory", "/tmp").toString()
        self.log_overwrite = self.settings.value(
            "ScriptRunner/log_overwrite", False).toBool()
        self.use_custom_editor = self.settings.value(
            "ScriptRunner/use_custom_editor", False).toBool()
        self.custom_editor = str(
            self.settings.value("ScriptRunner/custom_editor", "").toString())

    def configure_console(self):
        self.stdout = self.stdout_textedit
        self.stdout.new_output.connect(self.output_posted)
        self.stdout.show()

        # set the visibility of the console based on user preference
        self.stdout_dock.setVisible(self.show_console)

    def log_results(self, script_dir, script_name, output):
        # open the logfile using mode based on user preference
        if self.log_overwrite:
            mode = 'w'
        else:
            mode = 'a'

        log_file = open(os.path.join(str(self.log_dir),
                                     "%s.log" % script_name), mode)
        log_file.close()

    def show_context_menu(self, pos):
        #self.context_menu.popup(point)
        #QMessageBox.information(None, "Popup Menu", "Pop it up")
        self.context_menu.exec_(self.scriptList.mapToGlobal(pos))

    def toggle_console__(self):
        if self.stdout_textedit.isVisible():
            self.stdout_textedit.hide()
        else:
            self.stdout_textedit.show()

    def toggle_console(self):
        self.stdout_dock.setVisible(not self.stdout_dock.isVisible())

    def edit_script(self):
        item = self.scriptList.currentItem()
        if item is not None:
            script = item.toolTip()
            if self.use_custom_editor:
                try:
                    (path, app) = os.path.split(self.custom_editor)
                    (base_name, ext) = os.path.splitext(app)
                    if ext == '.app' and platform.system() == 'Darwin':
                        # open it using open -a syntax
                        subprocess.Popen(['open', '-a', app, script])
                    else:
                        if platform.system() == 'Windows':
                            # use the short name 
                            editor = win32api.GetShortPathName(str(self.custom_editor))
                        else:
                            editor = str(self.custom_editor)
                        # use subprocess to call custom editor
                        subprocess.Popen([str(self.custom_editor),
                                          str(script)])
                except:
                    QMessageBox.critical(
                        None, "Error Opening Editor",
                        """Atempting to open %s using %s failed.\n
                        Check the path to your custom editor."""
                        % (script, self.custom_editor))
                    tb = TracebackDialog()
                    tb.ui.teTraceback.setTextColor(QColor(Qt.red))
                    self.last_traceback = traceback.format_exc()
                    tb.ui.teTraceback.setText(traceback.format_exc())
                    tb.show()
                    tb.exec_()
            else:
                # Open the script with the system default
                QDesktopServices.openUrl(QUrl("file://%s" % script))

    def close_window(self):
        self.mw.hide()

    def get_script_args(self):
        """
        Get the args for the scripts run_script function
        """
        item = self.scriptList.currentItem()
        if item is not None:  # in case no currentitem and none was passed
            script = item.toolTip()
            (script_dir, script_name) = os.path.split(str(script))
            (user_module, ext) = os.path.splitext(script_name)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            if not user_module in sys.modules:
                __import__(user_module)
            script_args = inspect.getargspec(sys.modules[user_module].run_script)
            #print "script_args is ", script_args

            # check to see if we have args in addition to 'iface'
            if len(script_args.args) > 1 or script_args.keywords != None:
                return script_args
            else:
                return None

    def script_name(self):
        """Return the script name."""
        item = self.scriptList.currentItem()
        if item is not None:
            script = item.toolTip()
            (script_dir, script_name) = os.path.split(str(script))
            return script_name
        else:
            return None

    #@pyqtSlot(str)
    def output_posted(self, text):
        #QMessageBox.information(None, "New Stdout", text)
        if self.log_output:
            try:
                self.log_file.write(text)
            except:
                print traceback.format_exc()
            finally:
                sys.__stdout__.flush()

    def restore_window_position(self):
        self.mw.restoreGeometry(
            self.settings.value("ScriptRunner/geometry").toByteArray())

    def open_help(self):
        help_url = QUrl("file:///%s/help/index.html" % self.plugin_dir)
        QDesktopServices.openUrl(help_url)
