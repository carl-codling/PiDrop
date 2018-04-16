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
import json
import time
import unicodedata
import six
import urwid
import shutil

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
        ('file', 'dark blue', 'light gray'),
        ('dir focus', 'dark red', 'white'),
        ('dir select', 'white', 'light green'),
        ('dir select focus', 'dark green', 'white'),
        ('notifications', 'light green', 'black'),
        ('importer', 'white', 'light blue'),
        ('exporter', 'light blue', 'black'),
        ('diradder', 'dark blue', 'white')
        ]

notif_default_text = '[Q]uit program | [S]elect a file/folder | [L]ist details of file/folder | [H]elp'
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

dir_path = os.path.dirname(os.path.realpath(__file__))

notifications = urwid.AttrWrap(urwid.Text(notif_default_text), 'notifications')
listbox =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker({})), 'body')
importer_listbox =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker({})), 'importer')
exporter_listbox =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker({})), 'exporter')
selected_files = []
import_files = []
new_dir = None # placeholder for name of dir about to be created
file_mode = None # can be any of [move, delete, export]

collapse_cache = {}

class pibox_ui():
    
    def __init__(self, data=None):
        self.header = urwid.AttrWrap(urwid.Text('PIBOX - manage your dropbox'), 'header')
        build_pibox_list()

        empty_importer_button = urwid.Button('Empty Import folder')
        urwid.connect_signal(empty_importer_button, 'click', self.empty_importer)

        empty_exporter_button = urwid.Button('Empty Export folder')
        urwid.connect_signal(empty_exporter_button, 'click', self.empty_exporter)

        importer_container = urwid.Frame(
            urwid.AttrWrap(urwid.Padding(importer_listbox, left=2, right=2), 'importer'),
            header=urwid.AttrWrap(urwid.Text('Importer folder'), 'header'),
            footer =urwid.AttrWrap(empty_importer_button, 'footer'))
        exporter_container = urwid.Frame(
            urwid.AttrWrap(urwid.Padding(exporter_listbox, left=2, right=2), 'exporter'),
            header=urwid.AttrWrap(urwid.Text('Exporter folder'), 'header'),
            footer =urwid.AttrWrap(empty_exporter_button, 'footer'))
        divider = urwid.Divider('-',1,0)
        adder = urwid.Edit('New directory:')
        urwid.connect_signal(adder, 'change', self.prepare_dir_adder)
        self.dir_adder = urwid.Padding(urwid.AttrWrap(adder, 'diradder'), left=2, right=2)

        self.sublists = urwid.AttrWrap(urwid.Pile([('pack', divider),('pack', self.dir_adder),('pack', divider),importer_container,exporter_container]),'exporter')
        self.cols = urwid.Columns([('weight', 3,listbox), self.sublists])
        self.mainview = urwid.Frame(
            self.cols,
            header=urwid.AttrWrap(self.header, 'head'),
            footer=urwid.Padding(notifications, left=5, right=5))

    def main(self):
        """Run the program."""
        
        self.loop = urwid.MainLoop(self.mainview, palette,
            unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, k):
        # update display of focus directory
        if k in ('q','Q'):
            raise urwid.ExitMainLoop()
    def empty_importer(self,i):
        for the_file in os.listdir(IMPORT_DIR):
            file_path = os.path.join(IMPORT_DIR, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception as e:
                print(e) 
        build_pibox_list('importer')
    def empty_exporter(self,i):
        for the_file in os.listdir(EXPORT_DIR):
            file_path = os.path.join(EXPORT_DIR, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception as e:
                print(e) 
        build_pibox_list('exporter')
    
    def prepare_dir_adder(self,w, txt):
        global new_dir
        global file_mode
        if len(txt) < 1:
            notifications.set_text(notif_default_text)
            file_mode = None
            new_dir = None
        else:
            notifications.set_text('Select a parent directory in the main browser and then hit [enter] to create new directory "'+txt+'"')
            file_mode = 'add_dir'
            # TODO - Sanitise
            new_dir = txt

class PiboxTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon,
        'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon,
        'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
        path = self.get_node().get_value()['path']+'/'+self.get_node().get_value()['name']
        
        self._w = urwid.AttrWrap(self._w, None)
        self._w.focus_attr = 'dir focus'
        
        if os.path.isfile(path):
            self._w.attr = 'file'


        if os.path.isdir(path) and 'children' in self.get_node().get_value():
            if path in collapse_cache:
                self.expanded = collapse_cache[path]
            elif node.get_depth() > 0:
                self.expanded = False
            self.update_expanded_icon()

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

    def update_expanded_icon(self):
        self.__super.update_expanded_icon()
        collapse_cache[self.get_node().get_value()['path']+'/'+self.get_node().get_value()['name']] = self.expanded

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
            self.add_to_selected(path+'/'+fname)

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
        
        elif key in ["l", "L"]:
            self.loc_details(path+'/'+fname)
             
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
            
            elif file_mode == 'add_dir':
                self.create_dir(path, fname) 
            
        elif key == 'esc':
            selected_files = []
            notifications.set_text(notif_default_text)
            file_mode = None
            build_pibox_list() 

        else:
            return key

    def add_to_selected(self,p):
        global selected_files;
        global file_mode
        global PIBOX_DIR

        # Check that we're not adding a file that exists in already added dir
        parts = p[1:].split('/')
        jparts = ''
        for part in parts:
            jparts += '/'+part
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
                self._w.attr = 'body'#
                self._w.focus_attr = 'dir focus'
            else:
                selected_files.append(p)
                self._w.attr = 'dir select'
                self._w.focus_attr = 'dir select focus'
                if os.path.isdir(p) and 'children' in self.get_node().get_value():
                    self.expanded = False
                    self.update_expanded_icon()
            if len(selected_files) > 0:
                file_mode = 'move'
                notifications.set_text('[m]ove selected files | [d]elete selected files | [e]xport selected files')
            else:
                file_mode = None
                notifications.set_text(notif_default_text)

    def confirm_move_files(self):
        global selected_files
        global file_mode
        if len(selected_files) > 0:
            file_mode = 'move'
            notifications.set_text('Press [ENTER] to confirm moving the selected files to this location')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)

    def confirm_del_files(self):
        global selected_files
        global file_mode
        if len(selected_files) > 0:
            file_mode = 'delete'
            notifications.set_text('Press [ENTER] to confirm deletion of the selected files')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)

    def confirm_export_files(self):
        global selected_files
        global file_mode
        if len(selected_files) > 0:
            file_mode = 'export'
            notifications.set_text('Press [ENTER] to confirm copying the selected files to the export folder')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)

    def confirm_import_files(self):
        global import_files
        global file_mode
        if len(import_files) > 0:
            file_mode = 'import'
            notifications.set_text('Press [ENTER] to confirm copying the selected files from the imports folder to here.')
        else:
            file_mode = None
            notifications.set_text('No files selected!\n'+notif_default_text)
    
    def loc_details(self, location):
        if os.path.isdir(location):
            fsize = 0
            for (path, dirs, files) in os.walk(location):
              for f in files:
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            notifications.set_text('This folder is ' + self.readable_bytes(fsize) + '\n'+notif_default_text)
        else:
            fsize = os.path.getsize(location)
            mod = time.ctime(os.path.getmtime(location))
            notifications.set_text('This file is ' + self.readable_bytes(fsize) + ' | Last modified: '+str(mod)+ '\n'+notif_default_text)

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
        global dir_path
        global PIBOX_DIR
        rootlen = len(PIBOX_DIR)
        if os.path.isdir(path+'/'+fname):
            p = path+'/'+fname
        else:
            p = path
        i=0
        for f in selected_files:
            newp = '/'+p+'/'+f.split("/")[-1]
            try:
                res = dbx.files_move(
                    '/'+f[rootlen:], newp[rootlen:],
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

    def delete_files(self, path, name):
        global selected_files
        global file_mode
        global PIBOX_DIR
        rootlen = len(PIBOX_DIR)
        nfiles = 0
        nfolders = 0
        for f in selected_files:
            try:
                dbx.files_delete_v2('/'+f[rootlen:])
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
        global EXPORT_DIR
        
        for p in selected_files:
            dest = EXPORT_DIR + '/' + p.split("/")[-1]
            if os.path.isfile(p):
                shutil.copy2(p, dest)
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    if not os.path.isdir(dest):
                        os.mkdir(dest)
                    for f in files:

                        #compute current (old) & new file locations
                        oldLoc = root + '/' + f
                        newLoc = dest + '/' + f
                        if not os.path.isfile(newLoc):
                            try:
                                shutil.copy2(oldLoc, newLoc)
                            except IOError:
                                notifications.set_text('file "' + f + '" already exists')
        selected_files = []
        file_mode = None
        notifications.set_text(str('files have been exported.\n'+notif_default_text))
        build_pibox_list('exporter') 

    def import_files(self, path, fname):
        global import_files
        global file_mode
        global IMPORT_DIR
        rootlen = len(IMPORT_DIR)
        if os.path.isdir(path+'/'+fname):
            p = path+'/'+fname
        else:
            p = path
        i=0
        for f in import_files:
            newp = p+'/'+f.split("/")[-1]
            os.rename(f, newp)
            i+=1
        build_pibox_list()  
        notifications.set_text(str(i) + ' Selected files and folders were imported.\n'+notif_default_text)
        import_files = []
        file_mode = None


    def create_dir(self, path, fname):
        global new_dir
        global file_mode
        if os.path.isdir(path+'/'+fname):
            p = path+'/'+fname
        else:
            p = path
        os.mkdir(p+'/'+new_dir)
        notifications.set_text('New directory "'+new_dir+'" created.\n'+notif_default_text)
        file_mode = None
        new_dir = None
        build_pibox_list('pibox')

class ImporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon,
        'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon,
        'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
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
        global import_files;
        global file_mode;

        path = self.get_node().get_value()['path']
        fname = self.get_node().get_value()['name']
        
        if key in ["s", "S"]:
            self.add_to_selected(path+'/'+fname)

    def add_to_selected(self,p):
        global import_files;
        global file_mode
        global IMPORT_DIR

        # Check that we're not adding a file that exists in already added dir
        parts = p[1:].split('/')
        jparts = ''
        for part in parts:
            jparts += '/'+part
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
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon,
        'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon,
        'dirmark')
    def __init__(self, node):
        #print(node.get_value())
        self.__super.__init__(node)
        #self.update_expanded_icon()
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
            return range(len(data['children']))
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


def get_pibox_dir(rootdir):
    """
    Creates a nested dictionary that represents the folder structure of rootdir
    """
    dir = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    #print('start', start)
    for path, dirs, files in os.walk(rootdir):
        #print('path', path)
        #print('dirs', dirs)
        #print('files', files)
        #print('-----------')
        folders = path[start:].split(os.sep)
        #print('folders', folders)
        subdir = dict.fromkeys(files)
        #print('subdir', subdir)
        parent = reduce(dict.get, folders[:-1], dir)
        #print('parent', parent)
        #print('------------')
        parent[folders[-1]] = subdir
    return format_pibox_dir(dir, rootdir[:-len(rootdir)+start-1])
    #return dir
    
def format_pibox_dir(dir, path):
    out=[]
    for k,v in dir.items():
        children = []
        if(v):
            children=format_pibox_dir(v,path+'/'+k)
        o = {'name':k, 'path':path}
        if len(children) > 0:
            o['children']  = children
        out.append(o)
    return out

def build_pibox_list(dir='*'):
    if dir in ['*', 'pibox']:
        data = get_pibox_dir(PIBOX_DIR)[0]
        topnode = PiboxParentNode(data)
        listbox.original_widget =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'body')

    if dir in ['*', 'importer']:
        data = get_pibox_dir(IMPORT_DIR)[0]
        topnode = ImporterParentNode(data)
        importer_listbox.original_widget =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'importer')

    if dir in ['*', 'exporter']:
        data = get_pibox_dir(EXPORT_DIR)[0]
        topnode = ExporterParentNode(data)
        exporter_listbox.original_widget =  urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'exporter')

def main():
    #data = get_pibox_dir(PIBOX_DIR)
    #data = get_Pibox_tree()
    #print(data)
    #print(json.dumps(data[0]))
    pibox_ui().main()

if __name__=="__main__":
    app = main()
