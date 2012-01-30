"""
 ScriptRunner
 A QGIS plugin
 Run scripts to automate QGIS tasks
                              -------------------
        begin                : 2012-01-27
        copyright            : (C) 2012 by GeoApt LLC
        email                : gsherman@geoapt.com


    This program is free software; you can redistribute it and/or modify  
    it under the terms of the GNU General Public License as published by  
    the Free Software Foundation; either version 2 of the License, or     
    (at your option) any later version.                                   
                                                                          
"""

import sys
import os
import re
import inspect

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from scriptrunner_mainwindow import ScriptRunnerMainWindow
# Import the help module
from scriptrunner_help import htmlhelp

class ScriptRunner:

    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface


    def initGui(self):
        # create the mainwindow
        self.mw = ScriptRunnerMainWindow()
        # fetch the list of stored scripts from user setting
        settings = QSettings()
        stored_scripts = settings.value("ScriptRunner/scripts")
        self.list_of_scripts = stored_scripts.toList()

        # Create action that will start plugin configuration
        self.action = QAction(QIcon(":/plugins/scriptrunner/icon.png"), \
            "ScriptRunner", self.iface.mainWindow())
        # connect the action to the run method
        QObject.connect(self.action, SIGNAL("triggered()"), self.run)

#        # Add toolbar button and menu item
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&ScriptRunner", self.action)

        self.main_window = self.mw.ui

        self.toolbar = self.main_window.toolBar
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        ## Action setup 
        # action for adding a script
        self.add_action = QAction(QIcon(":plugins/scriptrunner/add_icon"),
                "Add Script", self.mw)
        self.toolbar.addAction(self.add_action)
        QObject.connect(self.add_action, SIGNAL("triggered()"), self.add_script)

        # action for running a script
        self.run_action = QAction(QIcon(":plugins/scriptrunner/run_icon"),
                "Run Script", self.mw)
        self.toolbar.addAction(self.run_action)
        QObject.connect(self.run_action, SIGNAL("triggered()"), self.run_script)

        # action for getting info about a script
        self.info_action = QAction(QIcon(":plugins/scriptrunner/info_icon"),
                "Script Info", self.mw)
        self.toolbar.addAction(self.info_action)
        QObject.connect(self.info_action, SIGNAL("triggered()"), self.info)


        # action for reloading a script
        self.reload_action = QAction(QIcon(":plugins/scriptrunner/reload_icon"),
                "Reload Script", self.mw)
        self.toolbar.addAction(self.reload_action)
        QObject.connect(self.reload_action, SIGNAL("triggered()"), self.reload_script)

        # action for removing a script
        self.remove_action = QAction(QIcon(":plugins/scriptrunner/cancel_icon"),
                "Remove Script", self.mw)
        self.toolbar.addAction(self.remove_action)
        QObject.connect(self.remove_action, SIGNAL("triggered()"), self.remove_script)

        # setup the splitter and list/text browser and mainwindow layout
        self.layout = QHBoxLayout(self.main_window.frame)
        self.splitter = QSplitter(self.main_window.frame)
        self.layout.addWidget(self.splitter)

        self.scriptList = QListWidget()
        self.splitter.addWidget(self.scriptList)

        self.tabWidget = QTabWidget()
        self.textBrowser = QTextBrowser()
        self.textBrowserSource = QTextBrowser()
        self.textBrowserHelp = QTextBrowser()
        self.textBrowserHelp.setHtml(htmlhelp())
        self.tabWidget.addTab(self.textBrowser, "Info")
        self.tabWidget.addTab(self.textBrowserSource, "Source")
        self.tabWidget.addTab(self.textBrowserHelp, "Help")
        self.splitter.addWidget(self.tabWidget)
        # set the sizes for the splitter
        split_size = [150, 350]
        self.splitter.setSizes(split_size)
        
        # add the list of scripts fetched from settings
        for script in self.list_of_scripts:
            (script_dir, script_name) = os.path.split(str(script.toString()))
            item = QListWidgetItem(script_name, self.scriptList)
            item.setToolTip(script.toString())

    def unload(self):
        # Remove the plugin menu item and icon
        self.iface.removePluginMenu("&ScriptRunner",self.action)
        self.iface.removeToolBarIcon(self.action)

    def add_script(self):
        script = QFileDialog.getOpenFileName(None, "Add a Python Script", 
                "", "Python scripts (*.py)")
        # check to see if we have a run method without importing the script
        if self.have_run_method(script):
            (script_dir, script_name) = os.path.split(str(script))
            item = QListWidgetItem(script_name, self.scriptList)
            item.setToolTip(script)
            self.main_window.statusbar.showMessage("Added script: %s" % script)
            self.list_of_scripts.append(script)
            self.update_settings()
            
        else:
            QMessageBox.information(None, "Error", "Your script must have a run_script() function defined. Adding the script failed.")
            self.main_window.statusbar.showMessage("Failed to add: %s - no run_script function" % script)



    def remove_script(self):
        item = self.scriptList.currentItem()
        if item != None:
            result = QMessageBox.question(None, "Remove Script", 
                    "Are you sure you want to remove %s?" % item.text(),
                    QMessageBox.Yes, QMessageBox.No)
            if result == QMessageBox.Yes:
                self.list_of_scripts.pop(self.list_of_scripts.index(item.toolTip()))
                self.update_settings()
                self.scriptList.takeItem(self.scriptList.currentRow())

    def reload_script(self):
        QMessageBox.information(None, "Reload", "Reload script was clicked--not implemented yet")

    def info(self):
        item = self.scriptList.currentItem()
        if item != None:
            script = item.toolTip()
            (script_dir, script_name) = os.path.split(str(script))
            (user_module, ext) = os.path.splitext(script_name)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            if not sys.modules.has_key(user_module):
                __import__(user_module)

            # add the doc string to the info page
            doc_string = inspect.getdoc(sys.modules[user_module])
            doc_string = doc_string.replace('\n', '<br>')
            html = "<h3>%s</h3><h4>Doc String:</h4>%s" % (script, doc_string)

            # populate the source tab
            source_code = "<pre>%s</pre>" % inspect.getsource(sys.modules[user_module])
            self.textBrowserSource.setHtml(source_code)

            classes = inspect.getmembers(sys.modules[user_module], inspect.isclass)

            # populate classes and methdods

            html += "<h4>Classes and Methods for %s</h4><ul>" % script_name

            for cls in classes:
              modinfo = inspect.getmodule(cls[1])
              if modinfo.__name__ == user_module:
                  html += "<li>%s</li>" % cls[0]
                  html += "<ul>"
                  for meth in inspect.getmembers(cls[1], inspect.ismethod):
                    html+= "<li>%s</li>" % meth[0]
                  html += "</ul></ul>"
            functions = inspect.getmembers(sys.modules[user_module], inspect.isfunction)
            html += "<h4>Functions in %s</h4><ul>" % script_name
            for func in functions:
                modinfo = inspect.getmodule(func[1])
                if modinfo.__name__ == user_module:
                    html += "<li>%s</li>" % func[0]
            html += "</ul>"

            self.textBrowser.setHtml(html)
            self.tabWidget.setCurrentIndex(0)



    def run_script(self):
        # get the selected item from the list
        item = self.scriptList.currentItem()
        if item != None:
            script = item.toolTip()
            self.main_window.statusbar.showMessage("Running script: %s" % script)
    
            # get the path and add it to sys.path
            (script_dir, script_name) = os.path.split(str(script))
   
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            (user_module, ext) = os.path.splitext(script_name)
  
            user_script = __import__(user_module)
 
            user_script.run_script(self.iface)
            self.main_window.statusbar.showMessage("Completed script: %s" % script)

    # Bring up the main window
    def run(self):
        self.mw.show()

    def have_run_method(self, script_path):
        script = open(script_path, 'r')
        pattern = re.compile('\s*def run_script\(*')
        run_method = False
        for line in script:
            if pattern.search(line):
                run_method = True
                break
        script.close()
        return run_method

    def update_settings(self):
        settings = QSettings()
        settings.setValue("ScriptRunner/scripts", QVariant(self.list_of_scripts))

      

