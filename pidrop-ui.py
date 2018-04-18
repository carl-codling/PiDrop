#!/usr/bin/python
"""
Text based UI for pibox dropbox cl tools

---------------------------------------------------------------------------
__/\\\\\\\\\\\\\__________/\\\\\\\\\\\\______________________________________________        
 _\/\\\/////////\\\_______\/\\\////////\\\____________________________________________       
  _\/\\\_______\/\\\__/\\\_\/\\\______\//\\\_______________________________/\\\\\\\\\__      
   _\/\\\\\\\\\\\\\/__\///__\/\\\_______\/\\\__/\\/\\\\\\\______/\\\\\_____/\\\/////\\\_     
    _\/\\\/////////_____/\\\_\/\\\_______\/\\\_\/\\\/////\\\___/\\\///\\\__\/\\\\\\\\\\__    
     _\/\\\_____________\/\\\_\/\\\_______\/\\\_\/\\\___\///___/\\\__\//\\\_\/\\\//////___   
      _\/\\\_____________\/\\\_\/\\\_______/\\\__\/\\\_________\//\\\__/\\\__\/\\\_________  
       _\/\\\_____________\/\\\_\/\\\\\\\\\\\\/___\/\\\__________\///\\\\\/___\/\\\_________ 
        _\///______________\///__\////////////_____\///_____________\/////_____\///__________
                      _               _  __         _   _               _    
                     | |__   _  _    | |/ /  __ _  (_) | |  __ _   ___ | |_  
                     | '_ \ | || |   | ' <  / _` | | | | | / _` | (_-< | ' \ 
                     |_.__/  \_, |   |_|\_\ \__,_| |_| |_| \__,_| /__/ |_||_|
                             |__/                                            
===========================================================================   
"""

from __future__ import print_function
import os
import fnmatch
import json
import time
import unicodedata
import six
import urwid
import shutil
import subprocess

import dropbox

dir_path = os.path.dirname(os.path.realpath(__file__))
with open(dir_path+'/cfg.json') as json_file:  
        cfga = json.load(json_file)
dbx = dropbox.Dropbox(cfga['token'])


PIBOX_DIR = cfga['rootdir']

IMPORT_DIR = cfga['import-dir']
EXPORT_DIR = cfga['export-dir']


palette = [
        ('body', 'black', 'light gray'),
        ('header', 'white', 'dark blue'),
        ('notifications', 'light green', 'black'),
        ('importer', 'white', 'light blue'),
        ('exporter', 'light blue', 'black'),
        ('diradder', 'dark blue', 'white'),
        ('input_box', 'dark blue', 'white'),
        ('input_box_active', 'black', 'yellow'),
        ('file', 'dark blue', 'light gray'),
        ('file focus', 'dark magenta', 'white'),
        ('dir', 'black', 'light gray'),
        ('dir focus','light red', 'white'),
        ('file select', 'white', 'light blue'),
        ('file select focus', 'dark blue', 'white'),
        ('dir select', 'white', 'light green'),
        ('dir select focus', 'dark green', 'white'),
        ('details', 'yellow', 'dark blue')
        ]

notif_default_text = '[Q]uit | [S]elect a file/dir | [N]ew directory | [R]ename file/dir | [P]roperties | [H]elp'
help_text = """
        Using this interface you can move/delete/import/export files in your dropbox folder
        ====================================================================================

            To Move, Delete or Export:
            -------------------------
            1) Navigate to some files in the main directory browser and press [s] to 
               select/deselect any files
            2) With some files/folders selected you can then either:
                a) Move the files: Select the location to move to then press [m]. You will 
                   be asked to press [enter] to confirm.
                b) Delete the files: Press [d]. You will be asked to press [enter] to 
                   confirm.
                c) Send files to the export folder: Press [e]. You will be asked to press 
                   [enter] to confirm.

            To Import:
            --------------------------
            1) Select/deselect files in Import folder browser (top right) using the [s] key
            2) Focus (place the cursor on) the target directory in the main directory browser
            3) Press [i] to import. You will be asked to press [enter] to confirm.

---------------------------------------------------------------------------------------------

"""+notif_default_text


selected_files = []
import_files = []
file_mode = None # can be any of [move, delete, export]
new_dir_location = None
search_term = None
#current_pos = None

collapse_cache = {}


class PiBoxSearchInput(urwid.Edit):

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key == 'enter':
            build_pibox_list('pibox')
            self.set_edit_text('')
        elif key == 'esc':
            notifications.set_text(notif_default_text)
            build_pibox_list()

class PiBoxDirInput(urwid.Edit):
    
    def keypress(self, size, key):
        global new_dir_location
        global file_mode
        key = self.__super.keypress(size, key)
        if key == 'enter':
            dirname = self.get_edit_text()

            if file_mode == 'new_dir' and len(dirname) > 0:
                os.mkdir(new_dir_location+os.sep+dirname)
                notifications.set_text('New directory "'+dirname+'" created at: '+new_dir_location+'\n'+notif_default_text)
            
            elif file_mode == 'rename':
                self.rename_path(dirname)

            file_mode = None
            new_dir_location = None
            build_pibox_list('pibox')
        
        elif key == 'esc':
            file_mode = None
            new_dir_location = None
            notifications.set_text(notif_default_text)
            build_pibox_list('pibox')

    def rename_path(self, new_name):
        rootlen = len(PIBOX_DIR)-1
        current_name = new_dir_location.split(os.sep)[-1]
        new_path = new_dir_location[:-len(current_name)] + new_name

        try:
            res = dbx.files_move(
                new_dir_location[rootlen:], new_path[rootlen:])
        except dropbox.exceptions.ApiError as err:
            print('*** API error', err)
            return None
        os.rename(new_dir_location, new_path)
        notifications.set_text(new_dir_location[rootlen:]+ ' > renamed to > '+new_path[rootlen:])

class PiboxTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
        path = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        self._w = urwid.AttrWrap(self._w, None)
        
        self.set_style()

        if os.path.isdir(path) and 'children' in self.get_node().get_value():
            if path in collapse_cache:
                self.expanded = collapse_cache[path]
            elif node.get_depth() > 0:
                self.expanded = False
            self.update_expanded_icon()
 
    def set_style(self):
        v = self.get_node().get_value()
        path = v['path']+os.sep+v['name']
        if path in selected_files:
            if  os.path.isfile(path):
                self._w.attr = 'file select'
                self._w.focus_attr = 'file select focus'
            else:
                self._w.attr = 'dir select'
                self._w.focus_attr = 'dir select focus'
        else:
            if  os.path.isfile(path):
                self._w.attr = 'file'
                self._w.focus_attr = 'file focus'
            else:
                self._w.attr = 'dir'
                self._w.focus_attr = 'dir focus'

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

    def update_expanded_icon(self):
        self.__super.update_expanded_icon()
        collapse_cache[self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']] = self.expanded

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        """
        Override this method to intercept keystrokes in subclasses.
        Default behavior: Toggle flagged on space, ignore other keys.
        """
        global selected_files;
        global file_mode;

        path = self.get_node().get_value()['path']
        fname = self.get_node().get_value()['name']
        if key == 'u':
            print(json.dumps(collapse_cache))
        if key in ["s", "S"]:
            self.add_to_selected(path+os.sep+fname)

        elif key in ['m','M']:
            self.confirm_move_files()

        elif key in ['d','D']:
            self.confirm_del_files()
            
        elif key in ['e','E']:
            self.confirm_export_files()
        
        elif key in ['h','H']:
            notifications.set_text(help_text)

        elif key in ["i", "I"]:
            self.confirm_import_files()

        elif key in ["n", "N"]:
            self.new_dir(path, fname)
        
        elif key in ["r", "R"]:
            self.init_rename_path(path, fname)
        
        elif key in ["p", "P"]:
            self.more_path_details()
             
        elif key == 'enter':
            rootlen = len(PIBOX_DIR)
            path = self.get_node().get_value()['path']
            fname = self.get_node().get_value()['name']
            
            if file_mode == 'move':
                self.move_files(path, fname)
            
            elif file_mode == 'delete':
                self.delete_files(path, fname)  
            
            elif file_mode == 'export':
                self.export_files() 
            
            elif file_mode == 'import':
                self.import_files(path, fname)  
            
        elif key == 'esc':
            selected_files = []
            notifications.set_text(notif_default_text)
            file_mode = None
            build_pibox_list() 

        else:
            return key

    def add_to_selected(self,p):
        global selected_files;

        # Check that we're not adding a file that exists in already added dir
        parts = p[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in selected_files and jparts != p:
                notifications.set_text('A higher level parent directory is already in the list')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(p):
            for s in filter (lambda x: p in x, selected_files):
                if s != p:
                    notifications.set_text('To add this whole directory you first need to deselect any child nodes')
                    return


        if p == PIBOX_DIR:
            notifications.set_text('Cannot add the root directory to the selected list!')
        else:
            if p in selected_files:
                selected_files.remove(p)
            else:
                selected_files.append(p)
                if os.path.isdir(p) and 'children' in self.get_node().get_value():
                    self.expanded = False
                    self.update_expanded_icon()
            if len(selected_files) > 0:
                #file_mode = 'move'
                notifications.set_text('[m]ove selected files | [d]elete selected files | [e]xport selected files')
            else:
                #file_mode = None
                notifications.set_text(notif_default_text)
        self.set_style()

    def confirm_move_files(self):
        global file_mode

        if len(selected_files) > 0:
            file_mode = 'move'
            notifications.set_text('Press [ENTER] to confirm moving the selected files to this location')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)

    def confirm_del_files(self):
        global file_mode
        if len(selected_files) < 1:
            fpath = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
            self.add_to_selected(fpath)
        file_mode = 'delete'
        notifications.set_text('Press [ENTER] to confirm deletion of the selected files')

    def confirm_export_files(self):
        global file_mode
        if len(selected_files) < 1:
            fpath = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
            self.add_to_selected(fpath)
        file_mode = 'export'
        notifications.set_text('Press [ENTER] to confirm copying the selected files to the export folder')

    def confirm_import_files(self):
        global file_mode
        if len(import_files) > 0:
            file_mode = 'import'
            notifications.set_text('Press [ENTER] to confirm copying the selected files from the imports folder to here.')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)
    
    def path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        out = '\nFull path: '+location
        if os.path.isfile(location):
            fsize = os.path.getsize(location)
            out += '\nSize: '+self.readable_bytes(fsize)
        fdetails.set_text(out)
        more_details.set_text('')

    def more_path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        if os.path.isdir(location):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(location):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            more_details.set_text('Size: ' + self.readable_bytes(fsize) + ' (in '+str(nfiles)+' files)\n')
        else:
            mod = time.ctime(os.path.getmtime(location))
            typ = subprocess.check_output(['file', '--mime-type', location])
            more_details.set_text('Last modified: '+str(mod)+ ' \nFile type: '+typ[len(location)+2:])

    def readable_bytes(self, b):
        if b < (1024*1024):
            out = ' %0.1f KB' % (b/1024.0)
        elif b < (1024*1024*1024):
            out = ' %0.1f MB' % (b/(1024*1024.0))
        else:
            out = ' %0.1f GB' % (b/(1024*1024*1024.0))
        return out

    def move_files(self, path, fname):
        global selected_files
        global file_mode
        rootlen = len(PIBOX_DIR)-1
        if os.path.isdir(path+os.sep+fname):
            p = path+os.sep+fname
        else:
            p = path
        i=0
        for f in selected_files:
            newp = p+os.sep+f.split(os.sep)[-1]
            try:
                res = dbx.files_move(
                    f[rootlen:], newp[rootlen:],
                    autorename=True)
            except dropbox.exceptions.ApiError as err:
                print('*** API error', err)
                return None
            os.rename(f, newp)
            i+=1

        # reset the json list of files to prevent conflicts
        # TO DO: find a better way to manage this
        f = open(dir_path+"/flist.json", 'w')
        f.write('{}')
        f.close()

        build_pibox_list()  
        notifications.set_text(str(i) + ' Selected files were moved.\n'+notif_default_text)
        selected_files = []
        file_mode = None
    
    def init_rename_path(self, path, fname):
        global new_dir_location
        global file_mode
        if self.get_node().get_depth() < 1:
            notifications.set_text('Cannot rename this folder from here')
            return
        new_dir_location = path+os.sep+fname
        file_mode = 'rename'
        listbox.original_widget =  urwid.AttrWrap(urwid.ListBox(urwid.SimpleFocusListWalker([urwid.AttrWrap(PiBoxDirInput('Rename '+fname+' to:\n'), 'input_box_active')])), 'body')
        notifications.set_text('[enter] to confirm | [esc] to cancel and go back to previous screen')

    def delete_files(self, path, name):
        global selected_files
        global file_mode
        rootlen = len(PIBOX_DIR)
        nfiles = 0
        nfolders = 0
        for f in selected_files:
            try:
                dbx.files_delete_v2(os.sep+f[rootlen:])
            except dropbox.exceptions.ApiError as err:
                    print('*** API error', err)
                    return None
            if os.path.isdir(f):
                shutil.rmtree(f)
                nfolders +=1
            else:
                os.remove(f)
                nfiles +=1
        notifications.set_text(str(nfiles)+' files and '+str(nfolders)+' folders have been deleted.\n'+notif_default_text)
        selected_files = []
        file_mode = None
        build_pibox_list('pibox')

    def export_files(self):
        global selected_files
        global file_mode
        
        for p in selected_files:
            dest = EXPORT_DIR + os.sep + p.split(os.sep)[-1]
            if os.path.isfile(p):
                shutil.copy2(p, dest)
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    if not os.path.isdir(dest):
                        os.mkdir(dest)
                    for f in files:

                        #compute current (old) & new file locations
                        oldLoc = root + os.sep + f
                        newLoc = dest + os.sep + f
                        if not os.path.isfile(newLoc):
                            try:
                                shutil.copy2(oldLoc, newLoc)
                            except IOError:
                                notifications.set_text('file "' + f + '" already exists')
        selected_files = []
        file_mode = None
        notifications.set_text(str('files have been exported.\n'+notif_default_text))
        build_pibox_list() 

    def import_files(self, path, fname):
        global import_files
        global file_mode
        rootlen = len(IMPORT_DIR)
        if os.path.isdir(path+os.sep+fname):
            p = path+os.sep+fname
        else:
            p = path
        i=0
        for f in import_files:
            newp = p+os.sep+f.split(os.sep)[-1]
            os.rename(f, newp)
            i+=1
        build_pibox_list()  
        notifications.set_text(str(i) + ' Selected files and folders were imported.\n'+notif_default_text)
        import_files = []
        file_mode = None

    def new_dir(self, path, fname):
        global new_dir_location
        global file_mode
        if os.path.isdir(path+os.sep+fname):
            new_dir_location = path+os.sep+fname
        else:
            new_dir_location = path
        file_mode = 'new_dir'
        listbox.original_widget =  urwid.AttrWrap(urwid.ListBox(urwid.SimpleFocusListWalker([urwid.AttrWrap(PiBoxDirInput('New directory name:\n'), 'input_box_active')])), 'body')
        notifications.set_text('[enter] to confirm creation of new dir | [esc] to cancel and go back to previous screen')


class ImporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
        path = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        if os.path.isdir(path) and 'children' in self.get_node().get_value():
            self.update_expanded_icon()
        self._w = urwid.AttrWrap(self._w, None)
        self._w.attr = 'importer'
        self._w.focus_attr = 'dir focus'

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):

        path = self.get_node().get_value()['path']
        fname = self.get_node().get_value()['name']
        
        if key in ["s", "S"]:
            self.add_to_selected(path+os.sep+fname)

    def add_to_selected(self,p):
        global import_files;
        global file_mode

        # Check that we're not adding a file that exists in already added dir
        parts = p[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in import_files and jparts != p:
                notifications.set_text('A higher level parent directory is already in the list')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(p):
            for s in filter (lambda x: p in x, import_files):
                if s != p:
                    notifications.set_text('To add this whole directory you first need to deselect any child nodes')
                    return


        if p == IMPORT_DIR:
            notifications.set_text('Cannot add the root directory to the selected list!')
        else:
            if p in import_files:
                import_files.remove(p)
                self._w.attr = 'body'#
                self._w.focus_attr = 'dir focus'
            else:
                import_files.append(p)
                self._w.attr = 'dir select'
                self._w.focus_attr = 'dir select focus'
                if os.path.isdir(p):
                    self.expanded = False
                    self.update_expanded_icon()
            if len(import_files) > 0:
                file_mode = 'import'
                notifications.set_text('Focus a directory in the main director browser and press [i] to import the files there.')
            else:
                file_mode = None
                notifications.set_text(notif_default_text)


class ExporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
        path = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        if os.path.isdir(path) and 'children' in self.get_node().get_value():
            self.update_expanded_icon()
        self._w = urwid.AttrWrap(self._w, None)
        self._w.attr = 'exporter'
        self._w.focus_attr = 'dir focus'

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

class PiboxNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return PiboxTreeWidget(self)

class ImporterNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return ImporterTreeWidget(self)

class ExporterNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return ExporterTreeWidget(self)


class PiboxParentNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes """

    def load_widget(self):
        return PiboxTreeWidget(self)

    def load_child_keys(self):
        data = self.get_value()
        if 'children' in data:
            files = []
            dirs = []
            i=0
            for child in data['children']:
                path = child['path']+os.sep+child['name']
                if(os.path.isdir(path)):
                    dirs.append((child['name'],i))
                else:
                    files.append((child['name'],i))
                i+=1
            dirs.sort(key=lambda tup: tup[0])
            files.sort(key=lambda tup: tup[0])
            out = []
            for n in dirs:
                out.append(n[1])
            for n in files:
                out.append(n[1])
            return out
            #return range(len(data['children']))
        else: return []

    def load_child_node(self, key):
        """Return either an PiboxNode or PiboxParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = PiboxParentNode
        else:
            childclass = PiboxNode

        return childclass(childdata, parent=self, key=key, depth=childdepth)

class ImporterParentNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes """
    def load_widget(self):
        return ImporterTreeWidget(self)

    def load_child_keys(self):
        data = self.get_value()
        if 'children' in data:
            return range(len(data['children']))
        else: return []

    def load_child_node(self, key):
        """Return either an PiboxNode or PiboxParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = ImporterParentNode
        else:
            childclass = ImporterNode

        return childclass(childdata, parent=self, key=key, depth=childdepth)

class ExporterParentNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes """
    def load_widget(self):
        return ExporterTreeWidget(self)

    def load_child_keys(self):
        data = self.get_value()
        if 'children' in data:
            return range(len(data['children']))
        else: return []

    def load_child_node(self, key):
        """Return either an PiboxNode or PiboxParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = ExporterParentNode
        else:
            childclass = ExporterNode

        return childclass(childdata, parent=self, key=key, depth=childdepth)

class PiboxWalker(urwid.TreeWalker):
    def __init__(self, start_from):
        self.focus = start_from
        urwid.connect_signal(self, 'modified', self.walking)
    def walking(self):
        self.focus.get_widget().path_details()

def empty_importer(i):
    for the_file in os.listdir(IMPORT_DIR):
        file_path = os.path.join(IMPORT_DIR, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e) 
    build_pibox_list('importer')

def empty_exporter(i):
    for the_file in os.listdir(EXPORT_DIR):
        file_path = os.path.join(EXPORT_DIR, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e) 
    build_pibox_list('exporter')

def unhandled_input(k):
    # update display of focus directory
    if k in ('q','Q'):
        raise urwid.ExitMainLoop()

def get_pibox_dir(rootdir):
    """
    Creates a nested dictionary that represents the folder structure of rootdir
    """
    dir = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(rootdir):
        folders = path[start:].split(os.sep)
        subdir = dict.fromkeys(files)
        parent = reduce(dict.get, folders[:-1], dir)
        parent[folders[-1]] = subdir
    return format_pibox_dir(dir, rootdir[:-len(rootdir)+start-1])
    
def format_pibox_dir(dir, path):
    out=[]
    for k,v in dir.items():
        children = []
        if(v):
            children=format_pibox_dir(v,path+os.sep+k)
        o = {'name':k, 'path':path}
        if len(children) > 0:
            o['children']  = children
        out.append(o)
    return out

def set_search(w, txt):
    global search_term
    if len(txt) > 0:
        search_term = txt
    else:
        search_term = None

def get_search_list():
    result = []
    pattern = '*'+search_term.lower()+'*'
    for root, dirs, files in os.walk(PIBOX_DIR):
        for name in files:
            if fnmatch.fnmatch(name.lower(), pattern):
                result.append({'name':name,'path':root})
        for name in dirs:
            if fnmatch.fnmatch(name.lower(), pattern):
                result.append({'name':name,'path':root})

    return {'name':'Search Results for ['+search_term+']:', 'path':PIBOX_DIR, 'children':result}

# def walking():
#     global current_pos
#     current_pos = listbox.get_focus()[1]
#     notifications.set_text(str(listbox.get_focus()))

def build_pibox_list(dir='*'):
    if dir in ['*', 'pibox']:
        listbox.original_widget = get_pibox_listbox()

    if dir in ['*', 'importer']:
        importer_listbox.original_widget = get_importer_listbox()

    if dir in ['*', 'exporter']:
        exporter_listbox.original_widget = get_exporter_listbox()
 
def get_pibox_listbox():
    if search_term:
        data = get_search_list()
    else:
        data = get_pibox_dir(PIBOX_DIR)[0]
    topnode = PiboxParentNode(data)
    walker = PiboxWalker(topnode)
    #urwid.connect_signal(walker, 'modified', walking)
    return  urwid.TreeListBox(walker)

def get_importer_listbox():
    data = get_pibox_dir(IMPORT_DIR)[0]
    topnode = ImporterParentNode(data)
    return  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'importer')

def get_exporter_listbox():
    data = get_pibox_dir(EXPORT_DIR)[0]
    topnode = ExporterParentNode(data)
    return  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'exporter')

def more_details(w):
    listbox.original_widget.body.focus.get_widget().more_path_details()

def main():
    loop = urwid.MainLoop(mainview, palette, unhandled_input=unhandled_input)
    loop.run()



# Main directory browser
listbox =  urwid.AttrWrap(get_pibox_listbox(), 'body')

# Import folder browser elements
importer_listbox =  get_importer_listbox()
empty_importer_button = urwid.Button('Empty Import folder')
urwid.connect_signal(empty_importer_button, 'click', empty_importer)
importer_container = urwid.Frame(
    urwid.AttrWrap(urwid.Padding(importer_listbox, left=2, right=2), 'importer'),
    header=urwid.AttrWrap(urwid.Text('Importer folder'), 'header'),
    footer =urwid.AttrWrap(empty_importer_button, 'footer')
)

# Export foler browser elements
exporter_listbox =  get_exporter_listbox()
empty_exporter_button = urwid.Button('Empty Export folder')
urwid.connect_signal(empty_exporter_button, 'click', empty_exporter)
exporter_container = urwid.Frame(
    urwid.AttrWrap(urwid.Padding(exporter_listbox, left=2, right=2), 'exporter'),
    header=urwid.AttrWrap(urwid.Text('Exporter folder'), 'header'),
    footer =urwid.AttrWrap(empty_exporter_button, 'footer')
)

# search input element
input_box = PiBoxSearchInput('Search:')
urwid.connect_signal(input_box, 'change', set_search)

# notifications bar
notifications = urwid.AttrWrap(urwid.Text(notif_default_text), 'notifications')

# primary elements
header = urwid.AttrWrap(urwid.Text('PIBOX - manage your dropbox'), 'header')
fdetails = urwid.Text('')
more_details_btn = urwid.Button('More Details')
urwid.connect_signal(more_details_btn, 'click', more_details)
more_details = urwid.Text('')
d = urwid.AttrWrap(urwid.Padding(urwid.ListBox([fdetails,more_details]), left=2, right=2),'details')
fdetails_container = urwid.Frame(
    d,
    header=urwid.AttrWrap(urwid.Text('File/Directory Properties'), 'header'),
    footer=urwid.AttrWrap(more_details_btn, 'footer')
)
sublists = urwid.AttrWrap(urwid.Pile([fdetails_container,importer_container,exporter_container]),'exporter')
main_section = urwid.Pile([listbox,('pack',urwid.AttrWrap(input_box, 'input_box'))])
cols = urwid.Columns([('weight', 3,main_section), sublists])
mainview = urwid.Frame(
    cols,
    header=urwid.AttrWrap(header, 'head'),
    footer=urwid.Padding(notifications, left=2, right=2)
)


if __name__=="__main__":
    main()
