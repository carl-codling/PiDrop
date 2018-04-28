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

===========================================================================
"""

from __future__ import print_function
import sys
import os
import fnmatch
import json
import time
import datetime
import unicodedata
import six
import urwid
import shutil
import subprocess

import dropbox

from themes import *
from pidrop_help import *

class PiBoxSearchInput(urwid.Edit):

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key == 'enter':
            build_search_list()
            #self.set_edit_text('')
        elif key == 'esc':
            keys.set_text(keys_default_text)
            build_pibox_list()

class PiBoxDirInput(urwid.Edit):

    def keypress(self, size, key):
        global new_dir_location
        global file_mode
        key = self.__super.keypress(size, key)
        if key == 'enter':
            dirname = self.get_edit_text()

            if file_mode == 'new_dir' and len(dirname) > 0:
                remote_path = new_dir_location[len(cfga['rootdir'])-1:]+os.sep+dirname
                notify(remote_path, 'success')
                try:
                    res = dbx.files_create_folder_v2(
                        remote_path,
                        autorename=True)
                except dropbox.exceptions.ApiError as err:
                    notify('*** API error: '+ str(err))
                    return None
                new_local_loc = new_dir_location+os.sep+os.path.basename(res.metadata.path_lower)
                os.mkdir(new_local_loc)
                notify('New directory %s created at %s' % (dirname,new_dir_location), 'success')
                keys.set_text(keys_default_text)
                flist[new_local_loc] = {'name':dirname}
                save_flist_to_json(dir_path, flist)

            elif file_mode == 'rename':
                self.rename_path(dirname)

            file_mode = None
            new_dir_location = None
            build_pibox_list('pibox')

        elif key == 'esc':
            file_mode = None
            new_dir_location = None
            keys.set_text(keys_default_text)
            build_pibox_list('pibox')

    def rename_path(self, new_name):
        rootlen = len(cfga['rootdir'])-1
        current_name = new_dir_location.split(os.sep)[-1]
        new_path = new_dir_location[:-len(current_name)] + new_name
        try:
            res = dbx.files_move_v2(
                new_dir_location[rootlen:], new_path[rootlen:],
                autorename=True)
        except dropbox.exceptions.ApiError as err:
            notify('*** API error: %s' % (str(err)), 'error')
            keys.set_text(keys_default_text)
            return None
        new_local_path = os.sep + cfga['rootdir'].strip(os.sep) + res.metadata.path_lower
        try:
            os.rename(new_dir_location, new_local_path)
        except OSError as err:
            notify(err,'error')
            return
        notify('%s > renamed to > %s' % (new_dir_location[rootlen:],new_local_path[rootlen:]),'success')
        keys.set_text(keys_default_text)
        flist[new_local_path] = {'name':res.metadata.path_display.split(os.sep)[-1]}
        save_flist_to_json(dir_path, flist)

class PiboxTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')

    indent_cols =5

    def __init__(self, node):
        self.name = node.get_value()['name']
        self.path = node.get_value()['path']
        self.full_path = self.path+os.sep+self.name
        self.__super.__init__(node)
        self._w = urwid.AttrWrap(self._w, None)

        self.set_style()

        if os.path.isdir(self.full_path) and 'children' in node.get_value():
            if self.full_path in collapse_cache:
                self.expanded = collapse_cache[self.full_path]
            elif node.get_depth() > 0:
                self.expanded = False
            self.update_expanded_icon()

    def set_style(self):
        if self.full_path in selected_files:
            if  os.path.isfile(self.full_path):
                self._w.attr = 'file select'
                self._w.focus_attr = 'file select focus'
            else:
                self._w.attr = 'dir select'
                self._w.focus_attr = 'dir select focus'
        else:
            if  os.path.isfile(self.full_path):
                self._w.attr = 'file'
                self._w.focus_attr = 'file focus'
            else:
                self._w.attr = 'dir'
                self._w.focus_attr = 'dir focus'

    def load_inner_widget(self):
        if self.get_node().get_depth()<1:
            return urwid.Text(self.name)
        elif 'sync' in self.get_node().get_value():
            self.sync_status = self.get_node().get_value()['sync']
            if self.sync_status == 'sync':
                return urwid.Columns([(2, urwid.AttrWrap(urwid.Text(u"\u25CF"),'sync')),urwid.Text(flist[self.full_path]['name'])])
            elif self.sync_status == 'unsync':
                return urwid.Columns([(2, urwid.AttrWrap(urwid.Text(u"\u25CB"),'unsync')),urwid.Text(self.name)])
            else:
                return urwid.Columns([(2, urwid.AttrWrap(urwid.Text(u"\u25A2"),'nosync')),urwid.Text(self.name)])
        else:
            return urwid.Text(self.name)

    def selectable(self):
        return True

    def update_expanded_icon(self):
        self.__super.update_expanded_icon()
        collapse_cache[self.full_path] = self.expanded

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

        if key in ["s", "S"]:
            self.add_to_selected()

        elif key in ['m','M']:
            self.confirm_move_files()

        elif key in ['d','D']:
            self.confirm_del_files()

        elif key in ['e','E']:
            self.confirm_export_files()

        elif key in ["i", "I"]:
            self.confirm_import_files()

        elif key in ["n", "N"]:
            self.new_dir()

        elif key in ["r", "R"]:
            self.init_rename_path()

        elif key in ["p", "P"]:
            self.more_path_details()

        elif key == 'enter':
            rootlen = len(cfga['rootdir'])

            if file_mode == 'move':
                self.move_files()

            elif file_mode == 'delete':
                self.delete_files()

            elif file_mode == 'export':
                self.export_files()

            elif file_mode == 'import':
                self.import_files()

        elif key == 'esc':
            selected_files = []
            keys.set_text(keys_default_text)
            file_mode = None
            build_pibox_list()
        else:
            return key

    def add_to_selected(self):
        global selected_files;

        # Check that we're not adding a file that exists in already added dir
        parts = self.full_path[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in selected_files and jparts != self.full_path:
                notify('A higher level parent directory is already in the list', 'error')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(self.full_path):
            for s in filter (lambda x: self.full_path in x, selected_files):
                if s != self.full_path:
                    notify('To add this whole directory you first need to deselect any child nodes', 'error')
                    return


        if self.full_path == cfga['rootdir']:
            notify('Cannot add the root directory to the selected list!', 'error')
        else:
            if self.full_path in selected_files:
                selected_files.remove(self.full_path)
            else:
                selected_files.append(self.full_path)
                if os.path.isdir(self.full_path) and 'children' in self.get_node().get_value():
                    self.expanded = False
                    self.update_expanded_icon()
            if len(selected_files) > 0:
                keys.set_text('[M]ove selected files | [D]elete selected files | [E]xport selected files | [esc] Cancel')
            else:
                keys.set_text(keys_default_text)
        self.set_style()

    def confirm_move_files(self):
        global file_mode

        if len(selected_files) > 0:
            file_mode = 'move'
            keys.set_text('Select (focus) the destination and hit [ENTER] to confirm moving the selected files')
        else:
            file_mode = None
            notify('No files selected!', 'error')

    def confirm_del_files(self):
        global file_mode
        if len(selected_files) < 1:
            self.add_to_selected()
        file_mode = 'delete'
        keys.set_text('Press [ENTER] to confirm deletion of the selected files')

    def confirm_export_files(self):
        global file_mode
        if len(selected_files) < 1:
            self.add_to_selected()
        file_mode = 'export'
        keys.set_text('Press [ENTER] to confirm copying the selected files to the export folder')

    def confirm_import_files(self):
        global file_mode
        if len(import_files) > 0:
            file_mode = 'import'
            keys.set_text('Press [ENTER] to confirm copying the selected files from the imports folder to here.')
        else:
            file_mode = None
            notify('No files selected!', 'error')

    def path_details(self):
        global path_details_list
        if self.path == '[[SEARCH]]':
            fdetails.original_widget = urwid.ListBox([])
            return
        path_details_list = [urwid.Text('')]
        if(hasattr(self, 'sync_status')):
            if self.sync_status == 'sync':
                path_details_list.append(urwid.AttrWrap(urwid.Text('[ SYNCED ]'),'sync'))
            elif self.sync_status == 'unsync':
                path_details_list.append(urwid.AttrWrap(urwid.Text('[ SYNCING ]'),'unsync'))
            else:
                path_details_list.append(urwid.AttrWrap(urwid.Text('[ NOT SYNCED ]'),'nosync'))
        path_details_list.append(urwid.Text('Full path: '+self.full_path))
        if os.path.isfile(self.full_path):
            fsize = os.path.getsize(self.full_path)
            path_details_list.append(urwid.Text('Size: '+readable_bytes(fsize)))
        fdetails.original_widget = urwid.ListBox(path_details_list)


    def more_path_details(self):
        if self.path == '[[SEARCH]]':
            return
        if os.path.isdir(self.full_path):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(self.full_path):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            path_details_list.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(self.full_path))
            path_details_list.append(urwid.Text('Last modified: %s' % (str(mod))))
            typ = subprocess.check_output(['file', '--mime-type', self.full_path])
            typstr = 'File type: %s' % (typ[len(self.full_path)+2:])
            typstr = typstr.strip()
            path_details_list.append(urwid.Text(typstr))
            if self.full_path in flist and 'media_info' in flist[self.full_path]:
                for k,v in  flist[self.full_path]['media_info'].items():
                    if k == 'Duration: ':
                        v = str(datetime.timedelta(milliseconds=int(v))).split('.')[0]
                    path_details_list.append(urwid.Text(k+v))

        fdetails.original_widget = urwid.ListBox(path_details_list)


    def move_files(self):
        global selected_files
        global file_mode
        rootlen = len(cfga['rootdir'])-1
        if os.path.isdir(self.full_path):
            p = self.full_path
        else:
            p = self.path
        i=0
        for f in selected_files:
            newp = p+os.sep+f.split(os.sep)[-1]
            if f in flist:
                newp_remote = p+os.sep+flist[f]['name']
                newp_remote = newp_remote[rootlen:]
            else:
                newp_remote = newp[rootlen:]
            try:
                res = dbx.files_move_v2(
                    f[rootlen:], newp_remote,
                    autorename=True)
            except dropbox.exceptions.ApiError as err:
                notify('*** API error: %s' % (str(err)))
                return None
            new_local_path = os.sep + cfga['rootdir'].strip(os.sep) + res.metadata.path_lower
            os.rename(f, new_local_path)
            if f in flist:
                flist[new_local_path] = {'name':res.metadata.path_display.split(os.sep)[-1]}
                del flist[f]
            i+=1

        save_flist_to_json(dir_path, flist)
        build_pibox_list()
        notify('%d Selected files/folders were moved.' % (i), 'success')
        keys.set_text(keys_default_text)
        selected_files = []
        file_mode = None

    def init_rename_path(self):
        global new_dir_location
        global file_mode
        if self.get_node().get_depth() < 1:
            notify('Cannot rename the root folder from here','error')
            return
        new_dir_location = self.full_path
        file_mode = 'rename'
        listbox.original_widget =  urwid.AttrWrap(urwid.ListBox(urwid.SimpleFocusListWalker([urwid.AttrWrap(PiBoxDirInput('Rename %s to:\n' % (self.name)), 'search_box_active')])), 'body')
        keys.set_text('[enter] to confirm | [esc] to cancel and go back to previous screen')

    def delete_files(self):
        global selected_files
        global file_mode
        rootlen = len(cfga['rootdir'])
        nfiles = 0
        nfolders = 0
        for f in selected_files:
            try:
                dbx.files_delete_v2(os.sep+f[rootlen:])
            except dropbox.exceptions.ApiError as err:
                    notify('*** API error: %s' % (str(err)) , 'error')
                    return None
            if os.path.isdir(f):
                shutil.rmtree(f)
                nfolders +=1
            else:
                os.remove(f)
                nfiles +=1
        notify('%d files and %d folders have been deleted.' % (nfiles,nfolders), 'success')
        keys.set_text(keys_default_text)
        selected_files = []
        file_mode = None
        build_pibox_list('pibox')

    def export_files(self):
        global selected_files
        global file_mode

        for p in selected_files:
            dest = cfga['export-dir'] + os.sep + p.split(os.sep)[-1]
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
                                notify('file %f already exists' % (f), 'error')
        selected_files = []
        file_mode = None
        notify('files have been exported.', 'success')
        keys.set_text(keys_default_text)
        build_pibox_list()

    def import_files(self):
        """ Import files in to a folder in the main dropbox folders
        Files added locally only, if they go to a synce folder they'll be uploaded
        on next sync"""
        global import_files
        global file_mode
        rootlen = len(cfga['import-dir'])
        if os.path.isdir(self.full_path):
            p = self.full_path
        else:
            p = self.path
        i=0
        for f in import_files:
            newp = p+os.sep+f.split(os.sep)[-1]
            os.rename(f, newp)
            i+=1
        build_pibox_list()
        notify('%d Selected files and folders were imported.' % (i), 'success')
        keys.set_text(keys_default_text)
        import_files = []
        file_mode = None

    def new_dir(self):
        global new_dir_location
        global file_mode
        if os.path.isdir(self.full_path):
            new_dir_location = self.full_path
        else:
            new_dir_location = self.path
        file_mode = 'new_dir'
        listbox.original_widget =  urwid.AttrWrap(urwid.ListBox(urwid.SimpleFocusListWalker([urwid.AttrWrap(PiBoxDirInput('New directory name:\n'), 'search_box_active')])), 'body')
        keys.set_text('[enter] to confirm creation of new dir | [esc] to cancel and go back to previous screen')


class ImporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
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
        elif key in ["p", "P"]:
            self.more_path_details()
        else:
            return key

    def path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        l = []
        l.append(urwid.Text('Full path: '+location))
        if os.path.isfile(location):
            fsize = os.path.getsize(location)
            l.append(urwid.Text('Size: '+readable_bytes(fsize)))
        fdetails.original_widget = urwid.ListBox(l)

    def more_path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        l = []
        if os.path.isdir(location):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(location):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            l.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(location))
            typ = subprocess.check_output(['file', '--mime-type', location])
            l.append(urwid.Text('Last modified: %s' % (str(mod))))
            l.append(urwid.Text('File type: %s' % (typ[len(location)+2:])))
        more_details.original_widget = urwid.ListBox(l)

    def add_to_selected(self,p):
        global import_files;
        global file_mode

        # Check that we're not adding a file that exists in already added dir
        parts = p[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in import_files and jparts != p:
                notify('A higher level parent directory is already in the list', 'error')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(p):
            for s in filter (lambda x: p in x, import_files):
                if s != p:
                    notify('To add this whole directory you first need to deselect any child nodes', 'error')
                    return


        if p == cfga['import-dir']:
            notify('Cannot add the root directory to the selected list!', 'error')
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
                keys.set_text('Focus a directory in the main director browser and press [i] to import the files there.')
            else:
                file_mode = None
                keys.set_text(keys_default_text)


class ExporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
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

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        if key in ["p", "P"]:
            self.more_path_details()
        else:
            return key

    def path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        l = []
        l.append(urwid.Text('Full path: '+location))
        if os.path.isfile(location):
            fsize = os.path.getsize(location)
            l.append(urwid.Text('Size: '+readable_bytes(fsize)))
        fdetails.original_widget = urwid.ListBox(l)

    def more_path_details(self):
        location = self.get_node().get_value()['path']+os.sep+self.get_node().get_value()['name']
        l = []
        if os.path.isdir(location):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(location):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            l.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(location))
            typ = subprocess.check_output(['file', '--mime-type', location])
            l.append(urwid.Text('Last modified: %s' % (str(mod))))
            l.append(urwid.Text('File type: %s' % (typ[len(location)+2:])))
        more_details.original_widget = urwid.ListBox(l)


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


class HelpParentNode(urwid.ParentNode):
    def load_widget(self):
        return HelpTreeWidget(self)

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
            childclass = HelpParentNode
        else:
            childclass = HelpNode

        return childclass(childdata, parent=self, key=key, depth=childdepth)

class HelpNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return HelpTreeWidget(self)

class HelpTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')
    def __init__(self, node):
        self.__super.__init__(node)
        self._w = urwid.AttrWrap(self._w, None)
        val = self.get_node().get_value()
        if self.get_node().get_depth() > 0:
            self.expanded = False
        if 'children' in val:
            self.update_expanded_icon()
        if 'answer' in val:
            self._w.attr = 'file'
            self._w.focus_attr = 'file focus'
        else:
            self._w.attr = 'dir'
            self._w.focus_attr = 'dir focus'

    def get_display_text(self):
        val = self.get_node().get_value()
        if 'answer' in val:
            return val['answer']
        return val['name']

    def selectable(self):
        return True

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        if key in ['b', 'B']:
            do_welcome_screen(None)
        if key in ["f", "F"]:
            do_filebrowser(None)
        else:
            return key


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

class MainContainer(urwid.Pile):
    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        if key in ['b', 'B']:
            do_welcome_screen(None)
        if key in ["f", "F"]:
            do_filebrowser(None)
        if key in ["c", "C"]:
            do_config_menu(None)
        if key in ["h", "H"]:
            do_help_menu(None)
        else:
            return key

def empty_importer(i):
    for the_file in os.listdir(cfga['import-dir']):
        file_path = os.path.join(cfga['import-dir'], the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            notify(str(e), 'error')
    build_pibox_list('importer')

def empty_exporter(i):
    for the_file in os.listdir(cfga['export-dir']):
        file_path = os.path.join(cfga['export-dir'], the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            notify(str(e), 'error')
    build_pibox_list('exporter')

def unhandled_input(k):
    # update display of focus directory
    if k in ('q','Q'):
        raise urwid.ExitMainLoop()

def get_pibox_dir(rootdir):
    """
    Creates a nested dictionary that represents the folder structure of rootdir
    """
    load_synced_file_list()
    dir = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(rootdir):
        folders = path[start:].split(os.sep)
        subdir = dict.fromkeys(files)
        parent = reduce(dict.get, folders[:-1], dir)
        parent[folders[-1]] = subdir
    return format_pibox_dir(dir, rootdir[:-len(rootdir)+start-1])

def format_pibox_dir(dir, path, overide_sync_check=False):
    out=[]
    rpath = ''
    for k,v in dir.items():
        osc = overide_sync_check
        fpath = path+os.sep+k
        if overide_sync_check:
            sync = 'override'
        elif os.path.isdir(path+os.sep+k):
            if fpath not in flist and not fnmatch.filter(flist, fpath+os.sep+'*'):
                # No dirs or subdirs are being synced
                # Override any checks in sub dirs
                sync = 'nosync'
                osc = True
            elif path_has_unsynced_children(fpath):
                sync = 'unsync'
            else:
                sync = 'sync'
        elif os.path.isfile(fpath) and fpath in flist:
            sync = 'sync'
        else:
            if path_has_synced_parent(fpath):
                sync = 'unsync'
            else:
                sync = 'nosync'

        children = []
        if(v):
            children=format_pibox_dir(v,fpath,osc)
        o = {'name':k, 'path':path, 'sync':sync}
        if len(children) > 0:
            o['children']  = children
        out.append(o)
    return out

def path_has_synced_parent(p):
    rlen = len(cfga['rootdir'])
    rpath = p[rlen:]
    parts = rpath.split(os.sep)
    op = ''
    for part in parts:
        op = op+os.sep+part
        op = op.strip(os.sep)
        if op in cfga['folders']:
            return True
    return False


def path_has_unsynced_children(p):
    for path, dirs, files in os.walk(p):
        for f in files:
            fullname = os.path.join(path, f)
            if fullname not in flist:
                return True
        for d in dirs:
            fullname = os.path.join(path, d)
            if fullname not in flist:
                return True
    return False

def notify(msg, attr='notif'):
    close = urwid.Button('X')
    urwid.connect_signal(close, 'click', clear_notify)
    outp = urwid.Padding(urwid.Text('\n%s\n' % (msg)),left=2,right=2)
    cols = urwid.AttrWrap(urwid.Columns([outp, (5, close)]),attr)
    messages.original_widget = cols

def clear_notify(w):
    messages.original_widget = urwid.AttrWrap(urwid.Text(''), 'body')

def set_search(w, txt):
    global search_term
    if len(txt) > 0:
        search_term = txt
    else:
        search_term = None

def get_search_list():
    result = []
    pattern = '*'+search_term.lower()+'*'
    for root, dirs, files in os.walk(cfga['rootdir']):
        for name in files:
            if fnmatch.fnmatch(name.lower(), pattern):
                result.append({'name':name,'path':root})
        for name in dirs:
            if fnmatch.fnmatch(name.lower(), pattern):
                result.append({'name':name,'path':root})

    return {'name':'Search Results for ['+search_term+']:', 'path':'[[SEARCH]]', 'children':result}

def build_pibox_list(dir='*'):
    if dir in ['*', 'pibox']:
        listbox.original_widget = get_pibox_listbox()

    if dir in ['*', 'importer']:
        importer_listbox.original_widget = get_importer_listbox()

    if dir in ['*', 'exporter']:
        exporter_listbox.original_widget = get_exporter_listbox()

    if 'search_term' in globals() and search_term != None:
        search_listbox.original_widget = get_search_listbox()

    fdetails.original_widget = urwid.ListBox([])

def get_search_listbox():
    data = get_search_list()
    topnode = PiboxParentNode(data)
    walker = PiboxWalker(topnode)
    return urwid.AttrWrap(urwid.TreeListBox(walker),'body')

def build_search_list():
    global search_listbox
    search_listbox =  get_search_listbox()
    close_search = urwid.Button('close')
    urwid.connect_signal(close_search, 'click', clear_search_list)
    main_browser.original_widget = urwid.Pile([
        ('pack',messages),
        urwid.Padding(listbox, left=1, right=1),
        ('pack',divider),
        urwid.Padding(urwid.AttrWrap(urwid.LineBox(urwid.Columns([search_listbox,(9,urwid.ListBox([close_search]))])),'body'), left=1, right=1),
        ('pack',divider),
        ('pack',urwid.Padding(urwid.AttrWrap(search_box, 'search_box'), left=2, right=2))
    ],3)

def clear_search_list(d):
    global search_term
    search_term = None
    main_browser.original_widget = urwid.Pile([
        ('pack',messages),
        urwid.Padding(listbox, left=1, right=1),
        ('pack',divider),
        ('pack',urwid.Padding(urwid.AttrWrap(search_box, 'search_box'), left=2, right=2))
    ])

def get_pibox_listbox():
    data = get_pibox_dir(cfga['rootdir'])[0]
    topnode = PiboxParentNode(data)
    walker = PiboxWalker(topnode)
    #urwid.connect_signal(walker, 'modified', walking)
    return  urwid.TreeListBox(walker)

def get_importer_listbox():
    data = get_pibox_dir(cfga['import-dir'])[0]
    topnode = ImporterParentNode(data)
    return  urwid.AttrWrap(urwid.TreeListBox(PiboxWalker(topnode)), 'importer')

def get_exporter_listbox():
    data = get_pibox_dir(cfga['export-dir'])[0]
    topnode = ExporterParentNode(data)
    return  urwid.AttrWrap(urwid.TreeListBox(PiboxWalker(topnode)), 'exporter')

def more_details(w):
    listbox.original_widget.body.focus.get_widget().more_path_details()

def readable_bytes(b):
    if b < (1024*1024):
        out = '%0.1f KB' % (b/1024.0)
    elif b < (1024*1024*1024):
        out = '%0.1f MB' % (b/(1024*1024.0))
    else:
        out = '%0.1f GB' % (b/(1024*1024*1024.0))
    return out

def dir_stats(d):
    fsize = 0
    nfiles = 0
    for (path, dirs, files) in os.walk(d):
      for f in files:
        nfiles += 1
        fname = os.path.join(path, f)
        fsize += os.path.getsize(fname)
    return (readable_bytes(fsize), nfiles)

def construct_importer_listbox():
    global importer_listbox
    global importer_container
    # Importer folder browser elements
    importer_listbox =  get_importer_listbox()
    stats = dir_stats(cfga['import-dir'])
    empty_importer_button = urwid.Button('Empty Import folder')
    urwid.connect_signal(empty_importer_button, 'click', empty_importer)
    footer = urwid.Padding(empty_importer_button, left=2, right=2)
    footer = urwid.Pile([divider,footer,divider])
    footer = urwid.AttrWrap(footer, 'footer')
    importer_container = urwid.Frame(
        urwid.AttrWrap(urwid.Padding(importer_listbox, left=2, right=2), 'importer'),
        header=urwid.AttrWrap(urwid.Text('Importer folder'), 'header'),
        footer =urwid.AttrWrap(footer, 'footer')
    )

def construct_exporter_listbox():
    global exporter_listbox
    global exporter_container
    # Export folder browser elements
    exporter_listbox =  get_exporter_listbox()
    stats = dir_stats(cfga['export-dir'])
    empty_exporter_button = urwid.Button('Empty Export folder')
    urwid.connect_signal(empty_exporter_button, 'click', empty_exporter)
    footer = urwid.Padding(empty_exporter_button, left=2, right=2)
    footer = urwid.Pile([divider,footer,divider])
    footer = urwid.AttrWrap(footer, 'footer')
    exporter_container = urwid.Frame(
        urwid.AttrWrap(urwid.Padding(exporter_listbox, left=2, right=2), 'exporter'),
        header=urwid.AttrWrap(urwid.Text('Exporter folder'), 'header'),
        footer =urwid.AttrWrap(footer, 'footer')
    )

def construct_properties_box():
    global fdetails
    global fdetails_container
    fdetails = urwid.AttrWrap(urwid.ListBox([urwid.Text('file and folder details will appear here')]),'details')
    plists = urwid.Pile([fdetails])
    fdetails_container = urwid.Frame(
        urwid.AttrWrap(urwid.Padding(plists, left=2, right=2),'details'),
        header=urwid.AttrWrap(urwid.Text('File/Directory Properties'), 'header')
    )

def construct_browser_right_column():
    global right_column
    construct_importer_listbox()
    construct_exporter_listbox()
    construct_properties_box()
    #c = urwid.Terminal(['sudo', 'tail', '-f', '/home/pi/PiDrop/pibox.log'])
    right_column = urwid.AttrWrap(
        urwid.Padding(
            urwid.Pile([
                ('pack',divider),
                urwid.LineBox(fdetails_container),
                urwid.LineBox(importer_container),
                urwid.LineBox(exporter_container)]
            ),
            right=1
        ),
        'body'
    )

def construct_browser_main_column():
    global listbox
    global search_box
    # Main directory browser
    listbox =  urwid.AttrWrap(get_pibox_listbox(), 'body')
    # search input element
    search_box = PiBoxSearchInput('Search:')
    urwid.connect_signal(search_box, 'change', set_search)

def construct_browser_mainview():
    global keys
    global mainview
    global main_browser
    global messages
    # notifications bar
    keys = urwid.AttrWrap(urwid.Text(keys_default_text), 'footer')
    footer = urwid.Pile([divider,keys,divider])
    # primary elements
    header = urwid.AttrWrap(urwid.Text('PIBOX - manage your dropbox'), 'header')

    messages = urwid.AttrWrap(urwid.Text(''), 'body')

    main_browser = urwid.AttrWrap(urwid.Pile([
        ('pack',messages),
        urwid.Padding(listbox, left=1, right=1),
        ('pack',divider),
        ('pack',urwid.Padding(urwid.AttrWrap(search_box, 'search_box'), left=2, right=2))
    ]),'body')
    cols = MainContainer([urwid.Columns([('weight', 3,main_browser), right_column])])
    mainview.original_widget = urwid.Frame(
        cols,
        header=urwid.AttrWrap(header, 'head'),
        footer=urwid.Padding(footer, left=2, right=2)
    )

def save_flist_to_json(dir_path, data):
    with open(dir_path+'/flist.json', 'w') as fp:
        json.dump(data, fp)

def load_palette():
    global palette
    global palettes
    global divider
    divider = urwid.Divider(' ')

    if 'palette' in cfga:
        palette = palettes[cfga['palette']]
    else: palette = palettes['light']

def do_filebrowser(w):
    global selected_files
    global import_files
    global new_dir_location
    global search_term
    global file_mode
    global collapse_cache
    global keys_default_text
    global dbx
    keys_default_text = '[B]ack to main menu | [S]elect a file/dir | [N]ew directory | [R]ename file/dir | [P]roperties | [H]elp | [Q]uit'
    selected_files = []
    import_files = []
    new_dir_location = None
    file_mode = None
    collapse_cache = {}
    dbx = connect_dbx()
    construct_browser_right_column()
    construct_browser_main_column()
    construct_browser_mainview()

def do_config_menu(w):
    global config_list
    global cfgtitle
    global errbox
    global dbx
    dbx = connect_dbx()
    footer = urwid.AttrWrap(urwid.Text('[B]ack to main menu | [F]ile browser | [H]elp | [Q]uit'), 'footer')
    footer = urwid.Pile([divider,footer,divider])
    footer = urwid.Padding(footer, left=2, right=2)
    errbox = urwid.AttrWrap(urwid.Text(''),'error')
    cfgtitle = urwid.AttrWrap(urwid.Text('Select an option below'),'details')
    opt_dirs = urwid.Button('Set the locations for your PiDrop directories')
    urwid.connect_signal(opt_dirs,'click',do_config_menu_dirs)
    opt_sync = urwid.Button('Select which Dropbox directories to sync')
    urwid.connect_signal(opt_sync,'click',do_config_menu_sync)
    opt_theme = urwid.Button('Select a theme')
    urwid.connect_signal(opt_theme,'click',do_config_menu_theme)
    opt_updown = urwid.Button('Upload/download settings')
    urwid.connect_signal(opt_updown,'click',do_config_menu_updown)

    back = urwid.Button('Back')
    urwid.connect_signal(back,'click',do_welcome_screen)
    config_list = urwid.AttrWrap(urwid.ListBox([style_btn(opt_dirs),style_btn(opt_sync),style_btn(opt_updown),style_btn(opt_theme),divider,style_btn(back)]), 'body')
    pile = MainContainer([('pack',divider),('pack',cfgtitle),('pack',divider), config_list])
    mainview.original_widget = urwid.AttrWrap(urwid.Frame(
        urwid.Padding(pile, left=5, right=5, width=120, align='center'),
        header=urwid.AttrWrap(urwid.Text('PiDrop Config'), 'header'),
        footer=footer
    ),'body')


def do_config_menu_updown(w):
    global cfgb
    cfgb = cfga
    cfg_menu = []
    if 'connection_tout' not in cfgb:
        cfgb['connection_tout'] = 30
    if 'large_upload_size' not in cfgb:
        cfgb['large_upload_size'] = 100
    if 'chunk_size' not in cfgb:
        cfgb['chunk_size'] = 10
    if 'daily_limit' not in cfgb:
        cfgb['daily_limit'] = 0
    connection_tout = urwid.IntEdit('Connection timeout:', cfgb['connection_tout'])
    urwid.connect_signal(connection_tout,'change',change_temp_cfg, 'connection_tout')
    conn_row = urwid.Columns([(26,connection_tout),(7,urwid.Text('seconds'))])
    cfg_menu.append(conn_row)
    cfg_menu.append(divider)
    large_upl_n = urwid.IntEdit('Split uploads larger than [ ', cfgb['large_upload_size'])
    urwid.connect_signal(large_upl_n,'change',change_temp_cfg, 'large_upload_size')
    chunk = urwid.IntEdit('in to [ ', cfgb['chunk_size'])
    urwid.connect_signal(chunk,'change',change_temp_cfg, 'chunk_size')
    chunkn_row = urwid.Columns([(33,large_upl_n),(7,urwid.Text('MB ] ')), (11,chunk), (12,urwid.Text('MB ] chunks '))])
    cfg_menu.append(chunkn_row)
    cfg_menu.append(divider)
    daily_limit = urwid.IntEdit('Daily upload/download limit: ', cfgb['daily_limit'])
    urwid.connect_signal(daily_limit,'change',change_temp_cfg, 'daily_limit')
    daily_row = urwid.Columns([(36,daily_limit), (19,urwid.Text('MB (0 = no limit) '))])
    cfg_menu.append(daily_row)
    cfg_menu.append(divider)
    save = urwid.Button('Save and exit')
    urwid.connect_signal(save,'click',config_save_updown)
    back = urwid.Button('Exit without saving')
    urwid.connect_signal(back,'click',do_config_menu)
    cfg_menu.append(style_btn(save))
    cfg_menu.append(style_btn(back))
    config_list.original_widget = urwid.ListBox(cfg_menu)

def config_save_updown(w):
    update_config(cfgb)
    do_config_menu(None)

def do_config_menu_dirs(w):
    global cfgb
    cfgb = cfga
    root_dir = urwid.Edit('PiDrop Root Directory: ', cfgb['rootdir'])
    urwid.connect_signal(root_dir,'change',change_temp_cfg, 'rootdir')
    import_dir = urwid.Edit('Imports Directory: ', cfgb['import-dir'])
    urwid.connect_signal(import_dir,'change',change_temp_cfg, 'import-dir')
    export_dir = urwid.Edit('Exports Directory: ', cfgb['export-dir'])
    urwid.connect_signal(export_dir,'change',change_temp_cfg, 'export-dir')
    save = urwid.Button('Save and exit')
    urwid.connect_signal(save,'click',config_save_dirs)
    back = urwid.Button('Exit without saving')
    urwid.connect_signal(back,'click',do_config_menu)
    cfg_menu = [root_dir,import_dir,export_dir,errbox]
    cfg_menu.append(style_btn(save))
    cfg_menu.append(style_btn(back))
    config_list.original_widget = urwid.ListBox(cfg_menu)

def style_btn(btn):
    return urwid.AttrWrap(btn,'button', 'button focus')

def config_save_dirs(w):
    if not os.path.isdir(cfgb['rootdir']):
        errbox.set_text('\nRoot Directory is not a valid directory\n')
    elif not os.path.isdir(cfgb['export-dir']):
        errbox.set_text('\nExport Directory is not a valid directory\n')
    elif not os.path.isdir(cfgb['import-dir']):
        errbox.set_text('\nImport Directory is not a valid directory\n')
    else:
        update_config(cfgb)
        do_config_menu(None)

def change_temp_cfg(w, v, setting):
    cfgb[setting] = v

def do_config_menu_sync(w):
    if 'all_remote_folders' in cfga:
        outlist = []
        if 'sync_depth' in cfga:
            sd = cfga['sync_depth']
        else: sd = 1
        leveldown = urwid.Button(' - ')
        level = urwid.Text(' Directory Depth: %d' % (sd))
        levelup = urwid.Button(' + ')
        level_ctrl = urwid.Columns([(7,urwid.AttrWrap(leveldown,'button')),(20,level),(7,urwid.AttrWrap(levelup,'button'))])
        urwid.connect_signal(leveldown, 'click', change_sync_depth, sd-1)
        urwid.connect_signal(levelup, 'click', change_sync_depth, sd+1)
        remote_folders = cfga['all_remote_folders']['folders'] #list_remote_folders()
        outlist.append(level_ctrl)
        upd = urwid.Button('Update List')
        urwid.connect_signal(upd,'click',update_folder_list)
        update_row = urwid.Columns([(15, urwid.AttrWrap(upd, 'details')),urwid.Text('(Last updated %s)' % (cfga['all_remote_folders']['upd']))])
        outlist.append(divider)
        outlist.append(update_row)
        outlist.append(divider)
        for name in remote_folders:
            name =name.strip(os.sep)
            depth = name.count(os.sep)
            if depth < sd:
                display_txt = '%s %s' % ('  '*depth, name.split(os.sep)[-1])
                if name in cfga['folders']:
                    outlist.append(urwid.CheckBox(display_txt, state=True, user_data=name, on_state_change=set_sync))
                else:
                    outlist.append(urwid.CheckBox(display_txt, state=False, user_data=name, on_state_change=set_sync))
        back = urwid.Button('Back')
        outlist.append(divider)
        outlist.append(errbox)
        outlist.append(style_btn(back))
        urwid.connect_signal(back,'click',do_config_menu)
        config_list.original_widget = urwid.ListBox(outlist)
    else:
        msg = urwid.Text('You haven\'t yet retrieved your directory structure from Dropbox. Please click the button below. This may take a few minutes...')
        btn = urwid.Button('Fetch list')
        config_list.original_widget = urwid.ListBox([msg, divider, btn])
        urwid.connect_signal(btn,'click',update_folder_list)

def change_sync_depth(w,i):
    if i < 1:
        i = 1
    if i > 5:
        i = 5
    for f in cfga['folders']:
        if f.count('/') > i-1:
            cfga['folders'].remove(f)
    cfga['sync_depth'] = i
    update_config(cfga)
    do_config_menu_sync(None)

def do_config_menu_theme(w):
    outlist = []
    opts = ['light','dark','system defaults']
    if 'palette' in cfga:
        p = cfga['palette']
    else: p = 'light'
    for name in opts:
        if name == p:
            outlist.append(urwid.CheckBox(name, state=True, user_data=name, on_state_change=set_theme))
        else:
            outlist.append(urwid.CheckBox(name, state=False, user_data=name, on_state_change=set_theme))
    back = urwid.Button('Back')
    outlist.append(divider)
    outlist.append(style_btn(back))
    urwid.connect_signal(back,'click',do_config_menu)
    config_list.original_widget = urwid.ListBox(outlist)

def set_theme(w, state, name):
    cfga['palette'] = name
    do_config_menu_theme(None)
    update_config(cfga)
    loop.screen.register_palette(palettes[name])
    loop.screen.clear()

def set_sync(w, state, name):
    if name in cfga['folders']:
        if not state:
            cfga['folders'].remove(name)
            update_config(cfga)
    elif state:
        cfga['folders'].append(name)
        update_config(cfga)

def update_folder_list(d):
    folders = retrieve_folder_list()
    cfga['all_remote_folders'] = {
        'folders':folders,
        'upd':str(datetime.datetime.now())
    }
    update_config(cfga)
    do_config_menu_sync(None)

def retrieve_folder_list(cursor=None):
    if cursor is not None:
        res = dbx.files_list_folder_continue(cursor)
    else:
        res = dbx.files_list_folder('', recursive=True)
    folders = []
    for entry in res.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            folders.append(entry.path_lower)
    if res.has_more:
        folders.extend(retrieve_folder_list(res.cursor))
    folders.sort()
    return folders


def do_help_menu(w):
    footer = urwid.AttrWrap(urwid.Text('[B]ack to main menu | [F]ile browser | [C]onfig | [Q]uit'), 'footer')
    footer = urwid.Pile([divider,footer,divider])
    footer = urwid.Padding(footer, left=2, right=2)
    data = help_questions
    topnode = HelpParentNode(data)
    helplist = urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'body')
    nfo = urwid.LineBox(urwid.Text("""
        Welcome to the help menu.
        -------------------------
        Use your mouse or the arrow keys on your keyboard to navigate through though question/answer list below.

        Throughout this UI you will find a list of available keys for the current screen in the footer."""))
    pile = MainContainer([('pack',divider),('pack',nfo),('pack',divider), helplist])
    mainview.original_widget = urwid.AttrWrap(urwid.Frame(
        urwid.Padding(pile, left=2,right=2),
        header=urwid.AttrWrap(urwid.Text('PiDrop Help Menu'), 'header'),
        footer=footer
    ),'body')

def show_help_item(w,a):
    help_item.set_text(a)

def do_welcome_screen(w):
    global mainview
    welcome = urwid.AttrWrap(urwid.LineBox(urwid.Text('Select an option below by either clicking the option or pressing the associated key')),'details')
    browser_btn = urwid.Button('[F]ile Browser/Manager')
    urwid.connect_signal(browser_btn,'click',do_filebrowser)
    config_btn  = urwid.Button('[C]onfigure PiDrop')
    urwid.connect_signal(config_btn,'click',do_config_menu)
    help_btn  = urwid.Button('[H]elp')
    urwid.connect_signal(help_btn,'click',do_help_menu)
    options = urwid.ListBox([style_btn(browser_btn),style_btn(config_btn),style_btn(help_btn)])
    pile = urwid.Filler(MainContainer([('pack',divider),('pack',welcome),('pack',divider), options]), height=10)
    mainview.original_widget = urwid.AttrWrap(urwid.Frame(
        urwid.Padding(pile, left=5, right=5, width=70, align='center'),
        header=urwid.AttrWrap(urwid.Text('Welcome'), 'header')
    ),'body')

def load_config():
    global dir_path
    global cfga
    dir_path = os.path.dirname(os.path.realpath(__file__))
    if not os.path.isfile(dir_path+'/cfg.json'):
        update_config({"export-dir": "", "folders": [], "import-dir": "", "rootdir": "", "token": ""})
    with open(dir_path+'/cfg.json') as json_file:
            cfga = json.load(json_file)

def load_synced_file_list():
    global flist
    if not os.path.isfile(dir_path+'/flist.json'):
        flist = {}
    else:
        with open(dir_path+'/flist.json') as json_file:
                flist = json.load(json_file)

def update_config(data):
    with open(dir_path+'/cfg.json', 'w') as outfile:
            json.dump(data, outfile)
    load_config()

def connect_dbx():
    global dbx
    if 'connection_tout' in cfga:
        tout = cfga['connection_tout']
    else:
        tout = 30
    dbx = dropbox.Dropbox(cfga['token'], timeout=int(tout))
    try:
        dbx.users_get_current_account()
    except:
        sys.exit("ERROR: Invalid access token; try re-generating an access token from the app console on the web.")
    return dbx

def ui_init():
    global loop
    global mainview
    mainview = urwid.AttrWrap(urwid.Text('Loading'), 'body')
    load_config()
    load_palette()
    do_welcome_screen(None)
    loop = urwid.MainLoop(mainview, palette, unhandled_input=unhandled_input)
    loop.run()
