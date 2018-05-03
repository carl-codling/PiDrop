#!/usr/bin/python
"""
Text based UI for pidrop dropbox cl tools

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
import re

import dropbox

from themes import *
from helpers import *
from pidrop_help import *

CWD = os.path.dirname(os.path.realpath(__file__))

class PiDropSearchInput(urwid.Edit):

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key == 'enter':
            SEARCHBAR.build_search_list()
            #self.set_edit_text('')
        elif key == 'esc':
            KEYPROMPT.set()
            SEARCHLIST.clear_search_list()

class PiDropDirInput(urwid.Edit):

    def __init__(self, caption, fmode, target_dir):
        self.__super.__init__(caption)
        self.fmode = fmode
        self.target_dir = target_dir

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key == 'enter':
            dirname = self.get_edit_text()

            if self.fmode == 'new_dir' and len(dirname) > 0:
                remote_path = self.target_dir[len(CONFIG.get('rootdir'))-1:]+os.sep+dirname
                NOTIFIER.set(remote_path, 'success')
                try:
                    res = DBX.files_create_folder_v2(
                        remote_path,
                        autorename=True)
                except dropbox.exceptions.ApiError as err:
                    NOTIFIER.set('*** API error: '+ str(err))
                    return None
                new_local_loc = self.target_dir+os.sep+os.path.basename(res.metadata.path_lower)
                os.mkdir(new_local_loc)
                NOTIFIER.set('New directory %s created at %s' % (dirname,self.target_dir), 'success')
                KEYPROMPT.set()
                SYNCED_FILES.set({'name':dirname}, new_local_loc)
                if os.path.isdir(BROWSER.focus_widget.full_path):
                    targ = BROWSER.focus_widget.get_node()
                else:
                    targ = BROWSER.focus_widget.get_node().get_parent()
                if 'children' in targ._value:
                    targ._value['children'].append({'name':dirname, 'path':self.target_dir, 'sync':'sync'})
                else:
                    targ._value['children'] = [{'name':dirname, 'path':self.target_dir, 'sync':'sync'}]
                targ.__init__(targ._value, targ._parent, targ._key, targ._depth)

            elif self.fmode == 'rename':
                self.rename_path(dirname)

            BROWSER.listbox_container.original_widget = BROWSER.listbox

        elif key == 'esc':
            KEYPROMPT.set()
            BROWSER.listbox_container.original_widget = BROWSER.listbox

    def rename_path(self, new_name):
        rootlen = len(CONFIG.get('rootdir'))-1
        current_name = self.target_dir.split(os.sep)[-1]
        new_path = self.target_dir[:-len(current_name)] + new_name
        try:
            res = DBX.files_move_v2(
                self.target_dir[rootlen:], new_path[rootlen:],
                autorename=True)
        except dropbox.exceptions.ApiError as err:
            NOTIFIER.set('*** API error: %s' % (str(err)), 'error')
            KEYPROMPT.set()
            return None
        new_local_path = os.sep + CONFIG.get('rootdir').strip(os.sep) + res.metadata.path_lower
        try:
            os.rename(self.target_dir, new_local_path)
        except OSError as err:
            NOTIFIER.set(err,'error')
            return
        NOTIFIER.set('%s > renamed to > %s' % (self.target_dir[rootlen:],new_local_path[rootlen:]),'success')
        KEYPROMPT.set()
        new_fname = res.metadata.path_display.split(os.sep)[-1]
        SYNCED_FILES.set({'name':new_fname}, new_local_path)
        BROWSER.focus_widget.get_node()._value['name'] = new_fname
        namelen = len(new_fname)+1
        BROWSER.focus_widget.get_node()._value['path'] = new_local_path[:-namelen]
        BROWSER.focus_widget.__init__(BROWSER.focus_widget.get_node())

class PiDropTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')

    indent_cols =5
    path_properties_data = []

    def __init__(self, node):
        self.name = node.get_value()['name']
        self.path = node.get_value()['path']
        self.full_path = self.path+os.sep+self.name
        self.__super.__init__(node)
        self._w = urwid.AttrWrap(self._w, None)

        self.set_style()

        if os.path.isdir(self.full_path) and 'children' in node.get_value():
            if self.full_path in BROWSER.collapsed:
                self.expanded = BROWSER.collapsed[self.full_path]
            elif node.get_depth() > 0:
                self.expanded = False
            self.update_expanded_icon()

    def set_style(self, selected=[]):
        if self.full_path in selected:
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
        # if we have a shared folder create a label for it
        if 'shared' in self.get_node().get_value():
            shared = urwid.AttrWrap(urwid.Text('[shared]'), 'shared')
        else:
            shared = urwid.Text('')
        # if our path exists in flist then get the display name
        if SYNCED_FILES.get(self.full_path):
            fname = SYNCED_FILES.get(self.full_path)['name']
        else:
            fname = self.name
        # if we're at the root node simply set a textual name
        if self.get_node().get_depth()<1:
            self.inner_w =  urwid.Text(self.name)
        # otherwise try to determine sync status
        elif 'sync' in self.get_node().get_value():
            self.sync_status = self.get_node().get_value()['sync']
            if self.sync_status == 'sync':
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrWrap(
                                            urwid.Text(u"\u25CF"),
                                            'sync')),
                                (len(fname)+1,
                                            urwid.Text(fname)),
                                (8,shared)
                            ])
            elif self.sync_status == 'unsync':
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrWrap(
                                            urwid.Text(u"\u25CB"),'unsync')),
                                (len(fname)+1,urwid.Text(fname)),
                                (8,shared)
                            ])
            else:
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrWrap(
                                            urwid.Text(u"\u25A2"),'nosync')),
                                (len(fname)+1,urwid.Text(fname)),
                                (8,shared)])
        else:
            self.inner_w = urwid.Text(fname)
        return self.inner_w

    def selectable(self):
        return True

    def update_expanded_icon(self):
        self.__super.update_expanded_icon()
        BROWSER.collapsed[self.full_path] = self.expanded

    def path_details(self):
        if self.path == '[[SEARCH]]':
            PROPSBOX.content.original_widget = urwid.ListBox([])
            return
        self.path_properties_data = [urwid.Text('')]
        if(hasattr(self, 'sync_status')):
            if self.sync_status == 'sync':
                self.path_properties_data.append(urwid.AttrWrap(urwid.Text('[ SYNCED ]'),'sync'))
            elif self.sync_status == 'unsync':
                self.path_properties_data.append(urwid.AttrWrap(urwid.Text('[ SYNCING ]'),'unsync'))
            else:
                self.path_properties_data.append(urwid.AttrWrap(urwid.Text('[ NOT SYNCED ]'),'nosync'))
        self.path_properties_data.append(urwid.Text('Full path: '+self.full_path))
        if os.path.isfile(self.full_path):
            fsize = os.path.getsize(self.full_path)
            self.path_properties_data.append(urwid.Text('Size: '+readable_bytes(fsize)))
        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)

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
            self.path_properties_data.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(self.full_path))
            self.path_properties_data.append(urwid.Text('Last modified: %s' % (str(mod))))
            typ = subprocess.check_output(['file', '--mime-type', self.full_path])
            typstr = 'File type: %s' % (typ[len(self.full_path)+2:])
            typstr = typstr.strip()
            self.path_properties_data.append(urwid.Text(typstr))
            synced_file = SYNCED_FILES.get(self.full_path)
            if synced_file and 'media_info' in synced_file:
                for k,v in  synced_file['media_info'].items():
                    if k == 'Duration: ':
                        v = str(datetime.timedelta(milliseconds=int(v))).split('.')[0]
                    self.path_properties_data.append(urwid.Text(k+v))

        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)

    def init_rename_path(self):
        if self.get_node().get_depth() < 1:
            NOTIFIER.set('Cannot rename the root folder from here','error')
            return
        caption = 'Rename %s to:\n' % (self.name)
        inputbox =PiDropDirInput(caption, 'rename', self.full_path)
        BROWSER.listbox_container.original_widget =  urwid.AttrWrap(urwid.ListBox([inputbox]), 'search_box_active')
        KEYPROMPT.set('[enter] to confirm | [esc] to cancel and go back to previous screen')

    def new_dir(self):
        if os.path.isdir(self.full_path):
            new_dir_location = self.full_path
        else:
            new_dir_location = self.path
        caption = 'New directory name:\n'
        inputbox = PiDropDirInput(caption, 'new_dir', new_dir_location)
        BROWSER.listbox_container.original_widget =  urwid.AttrWrap(urwid.ListBox([inputbox]), 'search_box_active')
        KEYPROMPT.set('[enter] to confirm creation of new dir | [esc] to cancel and go back to previous screen')


class ImporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')

    path_properties_data = []

    def __init__(self, node):
        self.name = node.get_value()['name']
        self.path = node.get_value()['path']
        self.full_path = self.path+os.sep+self.name
        self.__super.__init__(node)
        if os.path.isdir(self.full_path) and 'children' in self.get_node().get_value():
            self.update_expanded_icon()
        self._w = urwid.AttrWrap(self._w, None)
        self._w.attr = 'importer'
        self._w.focus_attr = 'dir focus'

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

    def path_details(self):
        self.path_properties_data = [urwid.Text('')]
        self.path_properties_data.append(urwid.Text('Full path: '+self.full_path))
        if os.path.isfile(self.full_path):
            fsize = os.path.getsize(self.full_path)
            self.path_properties_data.append(urwid.Text('Size: '+readable_bytes(fsize)))
        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)

    def more_path_details(self):
        if os.path.isdir(self.full_path):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(self.full_path):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            self.path_properties_data.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(self.full_path))
            self.path_properties_data.append(urwid.Text('Last modified: %s' % (str(mod))))
            typ = subprocess.check_output(['file', '--mime-type', self.full_path])
            typstr = 'File type: %s' % (typ[len(self.full_path)+2:])
            typstr = typstr.strip()
            self.path_properties_data.append(urwid.Text(typstr))

        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)


class ExporterTreeWidget(urwid.TreeWidget):
    """ Display widget for leaf nodes """
    unexpanded_icon = urwid.AttrMap(urwid.TreeWidget.unexpanded_icon, 'dirmark')
    expanded_icon = urwid.AttrMap(urwid.TreeWidget.expanded_icon, 'dirmark')

    path_properties_data = []

    def __init__(self, node):
        self.name = node.get_value()['name']
        self.path = node.get_value()['path']
        self.full_path = self.path+os.sep+self.name
        self.__super.__init__(node)
        if os.path.isdir(self.full_path) and 'children' in self.get_node().get_value():
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
        self.path_properties_data = [urwid.Text('')]
        self.path_properties_data.append(urwid.Text('Full path: '+self.full_path))
        if os.path.isfile(self.full_path):
            fsize = os.path.getsize(self.full_path)
            self.path_properties_data.append(urwid.Text('Size: '+readable_bytes(fsize)))
        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)

    def more_path_details(self):
        if os.path.isdir(self.full_path):
            fsize = 0
            nfiles = 0
            for (path, dirs, files) in os.walk(self.full_path):
              for f in files:
                nfiles += 1
                fname = os.path.join(path, f)
                fsize += os.path.getsize(fname)
            self.path_properties_data.append(urwid.Text('Size: %s (in %d files)' % (readable_bytes(fsize),nfiles)))
        else:
            mod = time.ctime(os.path.getmtime(self.full_path))
            self.path_properties_data.append(urwid.Text('Last modified: %s' % (str(mod))))
            typ = subprocess.check_output(['file', '--mime-type', self.full_path])
            typstr = 'File type: %s' % (typ[len(self.full_path)+2:])
            typstr = typstr.strip()
            self.path_properties_data.append(urwid.Text(typstr))

        PROPSBOX.content.original_widget = urwid.ListBox(self.path_properties_data)


class PiDropNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return  PiDropTreeWidget(self)

    def has_children(self):
        return False


class ImporterNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return ImporterTreeWidget(self)

class ExporterNode(urwid.TreeNode):
    """ Data storage object for leaf nodes """
    def load_widget(self):
        return ExporterTreeWidget(self)


class PiDropParentNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes """

    def load_widget(self):
        return PiDropTreeWidget(self)

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
        """Return either an PiDropNode or PiDropParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = PiDropParentNode
        else:
            childclass = PiDropNode

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
        """Return either an PiDropNode or PiDropParentNode"""
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
        """Return either an PiDropNode or PiDropParentNode"""
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
        """Return either an PiDropNode or PiDropParentNode"""
        childdata = self.get_value()['children'][key]
        childdepth = self.get_depth() + 1
        if 'children' in childdata:
            childclass = ExporterParentNode
        else:
            childclass = ExporterNode

        return childclass(childdata, parent=self, key=key, depth=childdepth)

class DirWalker(urwid.TreeWalker):
    def __init__(self, start_from):
        self.focus = start_from
        urwid.connect_signal(self, 'modified', self.walking)
    def walking(self):
        self.focus.get_widget().path_details()

class PiDropWalker(urwid.TreeWalker):

    def __init__(self, start_from):
        self.focus = start_from
        urwid.connect_signal(self, 'modified', self.walking)

    def walking(self):
        BROWSER.focus_widget = self.focus.get_widget()
        BROWSER.current_focus_path = self.focus.get_widget().full_path
        self.focus.get_widget().path_details()

    def reset_all_nodes_style(self):
        nodes = self.__iter__()
        for p in nodes:
            p.get_widget().set_style()

    def reset_focus(self):
        nodes = self.__iter__()
        if not BROWSER.current_focus_path:
            return
        for p in nodes:
            if p.get_value()['path']+os.sep+p.get_value()['name'] == BROWSER.current_focus_path:
                self.set_focus(p)
                return
        # if we can't find the specific node we try the parent
        nodes = self.__iter__()
        for p in nodes:
            if p.get_value()['path']+os.sep+p.get_value()['name'] == os.path.abspath(os.path.join(BROWSER.current_focus_path, os.pardir)):
                self.set_focus(p)
                return

    def __iter__(self):
        """
        Return an iterator over the positions in this ListBox.
        If self._body does not implement positions() then iterate
        from the focus widget down to the bottom, then from above
        the focus up to the top.  This is the best we can do with
        a minimal list walker implementation.
        """
        positions_fn = getattr(self, 'positions', None)
        if positions_fn:
            for pos in positions_fn():
                yield pos
            return

        focus_widget, focus_pos = self.get_focus()
        if focus_widget is None:
            return
        pos = focus_pos
        while True:
            yield pos
            w, pos = self.get_next(pos)
            if not w: break
        pos = focus_pos
        while True:
            w, pos = self.get_prev(pos)
            if not w: break
            yield pos

class MainContainer(urwid.Pile):
    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        if key in ['b', 'B']:
            WINDOW.screen(None, 'welcome')
        if key in ["f", "F"]:
            WINDOW.screen(None, 'browser')
        if key in ["c", "C"]:
            WINDOW.screen(None, 'config')
        if key in ["h", "H"]:
            WINDOW.screen(None, 'help')
        else:
            return key

class PiDropTreeList(urwid.TreeListBox):

    selected = [] # List of paths that are selected for operations
    fmode = None # path operation mode (move, delete,...)

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):
        w = self.body.focus.get_widget()
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
            w.new_dir()

        elif key in ["r", "R"]:
            w.init_rename_path()

        elif key in ["p", "P"]:
            w.more_path_details()

        elif key == 'enter':

            if self.fmode == 'move':
                self.move_files()

            elif self.fmode == 'delete':
                self.delete_files()

            elif self.fmode == 'export':
                self.export_files()

            elif self.fmode == 'import':
                self.import_files()

        elif key == 'esc':
            self.selected = []
            self.fmode = None
            KEYPROMPT.set()
            NOTIFIER.clear(None)
            #build_pidrop_list()
            self.reload_walker()

        else:
            return key

    def add_to_selected(self):
        w = self.body.focus.get_widget()
        # Check that we're not adding a file that exists in already added dir
        parts = w.full_path[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in self.selected and jparts != w.full_path:
                NOTIFIER.set('A higher level parent directory is already in the list', 'error')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(w.full_path):
            for s in filter (lambda x: w.full_path in x, self.selected):
                if s != w.full_path:
                    NOTIFIER.set('To add this whole directory you first need to deselect any child nodes', 'error')
                    return


        if w.full_path == CONFIG.get('rootdir'):
            NOTIFIER.set('Cannot add the root directory to the selected list!', 'error')
        else:
            if w.full_path in self.selected:
                self.selected.remove(w.full_path)
            else:
                self.selected.append(w.full_path)
                if os.path.isdir(w.full_path) and 'children' in self.body.focus.get_value():
                    w.expanded = False
                    w.update_expanded_icon()
            if len(self.selected) > 0:
                KEYPROMPT.set('[M]ove selected files | [D]elete selected files | [E]xport selected files | [esc] Cancel')
            else:
                KEYPROMPT.set()
        w.set_style(self.selected)

    def confirm_move_files(self):
        if len(self.selected) > 0:
            self.fmode = 'move'
            KEYPROMPT.set('Select (focus) the destination and hit [ENTER] to confirm moving the selected files')
        else:
            self.fmode = None
            NOTIFIER.set('No files selected!', 'error')

    def move_files(self):
        loading(BROWSER.listbox_container)
        w = self.body.focus.get_widget()
        rootlen = len(CONFIG.get('rootdir'))-1
        if os.path.isdir(w.full_path):
            p = w.full_path
        else:
            p = w.path
        i=0
        for f in self.selected:
            newp = p+os.sep+f.split(os.sep)[-1]
            synced_file = SYNCED_FILES.get(f)
            if synced_file:
                newp_remote = p+os.sep+synced_file['name']
                newp_remote = newp_remote[rootlen:]
            else:
                newp_remote = newp[rootlen:]
            try:
                res = DBX.files_move_v2(
                    f[rootlen:], newp_remote,
                    autorename=True)
            except dropbox.exceptions.ApiError as err:
                NOTIFIER.set('*** API error: %s' % (str(err)))
                return None
            new_local_path = os.sep + CONFIG.get('rootdir').strip(os.sep) + res.metadata.path_lower
            os.rename(f, new_local_path)
            if synced_file:
                SYNCED_FILES.set({'name':res.metadata.path_display.split(os.sep)[-1]},new_local_path)
                SYNCED_FILES.unset(f)
            i+=1

        self.reload_walker()
        NOTIFIER.set('%d Selected files/folders were moved.' % (i), 'success')
        KEYPROMPT.set()
        self.selected = []
        self.fmode = None

    def confirm_del_files(self):
        if len(self.selected) < 1:
            self.add_to_selected()
        self.fmode = 'delete'
        KEYPROMPT.set('Press [ENTER] to confirm deletion of the selected files')

    def delete_files(self):
        rootlen = len(CONFIG.get('rootdir'))
        nfiles = 0
        nfolders = 0
        out = ''
        for f in self.selected:
            try:
                DBX.files_delete_v2(os.sep+f[rootlen:])
            except dropbox.exceptions.ApiError as err:
                    out += '*** API error: %s\n' % (str(err))
            if os.path.isdir(f):
                shutil.rmtree(f)
                out += 'dir and any contained items deleted [%s]\n' % (f)
                nfolders +=1
            else:
                os.remove(f)
                out += 'file deleted [%s]\n' % (f)
                nfiles +=1
        NOTIFIER.set('%d files and %d folders have been deleted.\n------------------------\n%s' % (nfiles,nfolders,out), 'success')
        KEYPROMPT.set()
        self.selected = []
        self.fmode = None
        self.reload_walker()

    def confirm_export_files(self):
        if len(self.selected) < 1:
            self.add_to_selected()
        self.fmode = 'export'
        KEYPROMPT.set('Press [ENTER] to confirm copying the selected files to the export folder')

    def export_files(self):
        loading(EXPORTER.listbox)
        for p in self.selected:
            dest = CONFIG.get('export-dir') + os.sep + p.split(os.sep)[-1]
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
                                NOTIFIER.set('file %f already exists' % (f), 'error')
        self.selected = []
        self.fmode = None
        NOTIFIER.set('files have been exported.', 'success')
        KEYPROMPT.set()
        EXPORTER.listbox.reload_walker()
        self.body.reset_all_nodes_style()

    def confirm_import_files(self):
        if len(IMPORTER.listbox.selected) > 0:
            self.fmode = 'import'
            KEYPROMPT.set('Press [ENTER] to confirm copying the selected files from the imports folder to here.')
        else:
            self.fmode = None
            NOTIFIER.set('No files selected!', 'error')

    def import_files(self):
        """ Import files in to a folder in the main dropbox folders
        Files added locally only, if they go to a synce folder they'll be uploaded
        on next sync"""
        loading(IMPORTER.listbox)
        if len(IMPORTER.listbox.selected) < 1:
            NOTIFIER.set('No files selected in importer', 'error')
        w = self.body.focus.get_widget()
        rootlen = len(CONFIG.get('import-dir'))
        if os.path.isdir(w.full_path):
            p = w.full_path
        else:
            p = w.path
        i=0
        for f in IMPORTER.listbox.selected:
            newp = p+os.sep+os.path.basename(f)
            os.rename(f, newp)
            i+=1
        #build_pidrop_list('importer')
        self.reload_walker()
        IMPORTER.listbox.reload_walker()
        NOTIFIER.set('%d Selected files and folders were imported.' % (i), 'success')
        KEYPROMPT.set()
        IMPORTER.listbox.selected = []
        self.fmode = None

    def reload_walker(self):
        loading(BROWSER.listbox_container)
        SYNCED_FILES.__init__()
        data = BROWSER.fetch_dir_data()[0]
        topnode = PiDropParentNode(data)
        self.body = PiDropWalker(topnode)
        self.body.reset_focus()
        self.body.reset_all_nodes_style()
        BROWSER.listbox_container.original_widget = BROWSER.listbox

class ImporterTreeList(urwid.TreeListBox):
    selected = []

    def keypress(self, size, key):
        """allow subclasses to intercept keystrokes"""
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):

        if key in ["s", "S"]:
            self.add_to_selected()
        elif key in ["p", "P"]:
            self.body.focus.get_widget().more_path_details()
        else:
            return key

    def add_to_selected(self):
        w = self.body.focus.get_widget()
        # Check that we're not adding a file that exists in already added dir
        parts = w.full_path[1:].split(os.sep)
        jparts = ''
        for part in parts:
            jparts += os.sep+part
            if jparts in self.selected and jparts != w.full_path:
                NOTIFIER.set('A higher level parent directory is already in the list', 'error')
                return

        # Check that we're not adding a folder that already has child nodes in the list
        if os.path.isdir(w.full_path):
            for s in filter (lambda x: w.full_path in x, self.selected):
                if s != w.full_path:
                    NOTIFIER.set('To add this whole directory you first need to deselect any child nodes', 'error')
                    return


        if w.full_path == CONFIG.get('import-dir'):
            NOTIFIER.set('Cannot add the root directory to the selected list!', 'error')
        else:
            if w.full_path in self.selected:
                self.selected.remove(w.full_path)
                w._w.attr = 'body'#
                w._w.focus_attr = 'dir focus'
            else:
                self.selected.append(w.full_path)
                w._w.attr = 'dir select'
                w._w.focus_attr = 'dir select focus'
                if os.path.isdir(w.full_path):
                    w.expanded = False
                    w.update_expanded_icon()
            if len(self.selected) > 0:
                KEYPROMPT.set('Focus a directory in the main director browser and press [i] to import the files there.')
            else:
                KEYPROMPT.set()

    def reload_walker(self):
        loading(IMPORTER.listbox_container)
        data = IMPORTER.get_dir()[0]
        topnode = ImporterParentNode(data)
        self.body = DirWalker(topnode)
        IMPORTER.listbox_container.original_widget = IMPORTER.listbox

class ExporterTreeList(urwid.TreeListBox):

    def reload_walker(self):
        loading(EXPORTER.listbox_container)
        data = EXPORTER.get_dir()[0]
        topnode = ExporterParentNode(data)
        self.body = DirWalker(topnode)
        EXPORTER.listbox_container.original_widget = EXPORTER.listbox

class DirWidget(object):

    def __init__(self, dir, style, title):
        self.dir = dir
        self.style = style
        self.title = title
        self.listbox = self.set_listbox()
        self.btns = self.set_btns()

    def set_listbox(self):
        data = self.get_dir()[0]
        topnode = urwid.ParentNode(data)
        return urwid.TreeListBox(urwid.TreeWalker(topnode))

    def set_btns(self):
        empty = urwid.Button('Empty '+self.title)
        urwid.connect_signal(empty, 'click', self.empty)
        reload = urwid.Button('Reload')
        urwid.connect_signal(reload, 'click', self.reload)
        return urwid.Columns([empty,reload])

    def build(self):
        footer = urwid.Padding(self.btns, left=2, right=2)
        footer = urwid.Pile([urwid.Divider(' '),footer,urwid.Divider(' ')])
        footer = urwid.AttrWrap(footer, 'footer')
        self.listbox_container = urwid.AttrWrap(urwid.Padding(self.listbox, left=2, right=2), self.style)
        return urwid.Frame(
            self.listbox_container,
            header=urwid.AttrWrap(urwid.Text(self.title), 'header'),
            footer =urwid.AttrWrap(footer, 'footer')
        )

    def reload(self,d):
        self.listbox.reload_walker()

    def get_dir(self):
        """
        Creates a nested dictionary that represents the folder structure of a dir
        """
        out = {}
        rootdir = self.dir.rstrip(os.sep)
        start = rootdir.rfind(os.sep) + 1
        for path, dirs, files in os.walk(rootdir):
            folders = path[start:].split(os.sep)
            subdir = dict.fromkeys(files)
            parent = reduce(dict.get, folders[:-1], out)
            parent[folders[-1]] = subdir
        return self.format_dir(out, rootdir[:-len(rootdir)+start-1])

    def format_dir(self, dir, path, overide_sync_check=False):
        out=[]
        rpath = ''
        for k,v in dir.items():
            osc = overide_sync_check
            fpath = path+os.sep+k
            children = []
            if(v):
                children=self.format_dir(v,fpath,osc)
            o = {'name':k, 'path':path}
            if len(children) > 0:
                o['children']  = children
            out.append(o)
        return out

    def empty(self,d):
        for the_file in os.listdir(self.dir):
            file_path = os.path.join(self.dir, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception as e:
                NOTIFIER.set(str(e), 'error')
        self.listbox.reload_walker()

class ImporterWidget(DirWidget):

    def set_listbox(self):
        data = self.get_dir()[0]
        topnode = ImporterParentNode(data)
        return ImporterTreeList(DirWalker(topnode))

class ExporterWidget(DirWidget):

    def set_listbox(self):
        data = self.get_dir()[0]
        topnode = ExporterParentNode(data)
        return ExporterTreeList(DirWalker(topnode))

class FileBrowserWidget(object):

    current_focus_path = None
    focus_widget = None
    collapsed = {} # Dict of expanded/collapsed parent nodes. Use to reset state on refresh

    def __init__(self):
        self.listbox = self.set_listbox()

    def build(self):
        lb = urwid.AttrWrap(self.listbox, 'body')
        self.listbox_container = urwid.AttrWrap(urwid.Frame(lb), 'body')
        return self.listbox_container

    def set_listbox(self):
        data = self.fetch_dir_data()[0]
        topnode = PiDropParentNode(data)
        walker = PiDropWalker(topnode)
        return  PiDropTreeList(walker)

    def fetch_dir_data(self):
        dir = {}
        rootdir = CONFIG.get('rootdir').rstrip(os.sep)
        start = rootdir.rfind(os.sep) + 1
        for path, dirs, files in os.walk(rootdir):
            folders = path[start:].split(os.sep)
            subdir = dict.fromkeys(files)
            parent = reduce(dict.get, folders[:-1], dir)
            parent[folders[-1]] = subdir
        return self.format_dir_data(dir, rootdir[:-len(rootdir)+start-1])

    def format_dir_data(self, dir, path, overide_sync_check=False):
        out=[]
        rpath = ''
        for k,v in dir.items():
            osc = overide_sync_check
            fpath = path+os.sep+k
            if overide_sync_check:
                sync = 'override'
            elif os.path.isdir(path+os.sep+k):
                if not SYNCED_FILES.get(fpath) and not fnmatch.filter(SYNCED_FILES.files, fpath+os.sep+'*'):
                    # No dirs or subdirs are being synced
                    # Override any checks in sub dirs
                    sync = 'nosync'
                    osc = True
                elif self.path_has_unsynced_children(fpath):
                    sync = 'unsync'
                else:
                    sync = 'sync'
            elif os.path.isfile(fpath) and SYNCED_FILES.get(fpath):
                sync = 'sync'
            else:
                if self.path_has_synced_parent(fpath):
                    sync = 'unsync'
                else:
                    sync = 'nosync'

            children = []
            if(v):
                children=self.format_dir_data(v,fpath,osc)
            o = {'name':k, 'path':path, 'sync':sync}
            if len(children) > 0:
                o['children']  = children
            shared = self.is_shared(fpath)
            if shared:
                o['shared'] = shared
            out.append(o)
        return out

    def is_shared(self, path):
        synced_path = SYNCED_FILES.get(path)
        if not synced_path:
            return False
        elif 'shared' in synced_path:
            return synced_path['shared']
        return False

    def path_has_synced_parent(self, p):
        rlen = len(CONFIG.get('rootdir'))
        rpath = p[rlen:]
        parts = rpath.split(os.sep)
        op = ''
        for part in parts:
            op = op+os.sep+part
            op = op.strip(os.sep)
            if op in CONFIG.get('folders'):
                return True
        return False

    def path_has_unsynced_children(self, p):
        for path, dirs, files in os.walk(p):
            for f in files:
                fullname = os.path.join(path, f)
                if not SYNCED_FILES.get(fullname):
                    return True
            for d in dirs:
                fullname = os.path.join(path, d)
                if not SYNCED_FILES.get(fullname):
                    return True
        return False

class PropsWidget(object):

    def __init__(self):
        self.content = urwid.AttrWrap(
                            urwid.ListBox([
                                    urwid.Text('file and folder details will appear here')
                            ]),'details')

    def build(self):
        pile = urwid.Pile([self.content])
        return urwid.Frame(
            urwid.AttrWrap(urwid.Padding(pile, left=2, right=2),'details'),
            header=urwid.AttrWrap(urwid.Text('File/Directory Properties'), 'header')
        )

class SearchBarWidget(object):

    search_term = None
    in_folder = False # folder to perform search in. False = all
    regex = False

    def __init__(self):
        self.inputbox = self.set_inputbox()

    def build(self):
        ftog = urwid.CheckBox('current folder only', on_state_change=self.ftoggle)
        regextog = urwid.CheckBox('regex', on_state_change=self.regextoggle)
        self.bar = urwid.Columns([urwid.AttrWrap(self.inputbox, 'search_box'),(24, ftog),(10, regextog) ])
        return self.bar

    def set_inputbox(self):
        inp = PiDropSearchInput('Search:')
        urwid.connect_signal(inp, 'change', self.set_search)
        return inp

    def set_search(self, w, txt):
        if len(txt) > 0:
            self.search_term = txt
        else:
            self.search_term = None

    def ftoggle(self, w, d):
        if d:
            if os.path.isdir(BROWSER.listbox.focus.full_path):
                self.in_folder = BROWSER.listbox.focus.full_path
            else:
                self.in_folder = BROWSER.listbox.focus.path
        else:
            self.in_folder = False

    def regextoggle(self, w, d):
        self.regex = d

    def build_search_list(self):
        global SEARCHLIST
        loading(WINDOW.left)
        SEARCHLIST = SearchListWidget()
        WINDOW.left.original_widget = SEARCHLIST.build()

class SearchListWidget(object):

    def __init__(self):
        self.listbox = self.set_listbox()

    def set_listbox(self):
        data = self.get_search_list()
        topnode = PiDropParentNode(data)
        walker = PiDropWalker(topnode)
        return urwid.AttrWrap(urwid.TreeListBox(walker),'body')

    def build(self):
        close_search = urwid.Button('close')
        urwid.connect_signal(close_search, 'click', self.clear_search_list)
        return urwid.Pile([
            ('pack',NOTIFIER.message),
            urwid.Padding(BROWSER.listbox, left=1, right=1),
            ('pack',urwid.Divider(' ')),
            urwid.Padding(urwid.AttrWrap(urwid.LineBox(urwid.Columns([self.listbox,(9,urwid.ListBox([close_search]))])),'body'), left=1, right=1),
            ('pack',urwid.Divider(' ')),
            ('pack',urwid.Padding(SEARCHBAR.bar, left=2, right=2))
        ],3)

    def clear_search_list(self,d):
        SEARCHBAR.search_term = None
        WINDOW.left.original_widget = urwid.Pile([
            ('pack',NOTIFIER.message),
            urwid.Padding(BROWSER.listbox, left=1, right=1),
            ('pack',urwid.Divider(' ')),
            ('pack',urwid.Padding(SEARCHBAR.bar, left=2, right=2))
        ])

    def get_search_list(self):
        result = []

        if SEARCHBAR.in_folder:
            f = SEARCHBAR.in_folder
        else:
            f = CONFIG.get('rootdir')

        if SEARCHBAR.regex:
            pattern = re.compile(SEARCHBAR.search_term)
            for root, dirs, files in os.walk(f):
                for name in files:
                    if pattern.match(name):
                        result.append({'name':name,'path':root})
                for name in dirs:
                    if pattern.match(name):
                        result.append({'name':name,'path':root})
        else:
            pattern = '*'+SEARCHBAR.search_term.lower()+'*'

            for root, dirs, files in os.walk(f):
                for name in files:
                    if fnmatch.fnmatch(name.lower(), pattern):
                        result.append({'name':name,'path':root})
                for name in dirs:
                    if fnmatch.fnmatch(name.lower(), pattern):
                        result.append({'name':name,'path':root})

        return {'name':'Search Results for ['+SEARCHBAR.search_term+'] in '+f+':', 'path':'[[SEARCH]]', 'children':result}

class NotificationsWidget(object):

    def __init__(self):
        self.message = urwid.AttrWrap(urwid.Text(''), 'body')

    def build(self):
        return self.message

    def set(self, msg, attr='notif'):
        close = urwid.Button('X')
        urwid.connect_signal(close, 'click', self.clear)
        outp = urwid.Padding(urwid.Text('\n%s\n' % (msg)),left=2,right=2)
        cols = urwid.AttrWrap(urwid.Columns([outp, (5, close)]),attr)
        self.message.original_widget = cols

    def clear(self, d):
        self.message.original_widget = urwid.AttrWrap(urwid.Text(''), 'body')

class KeyPromptWidget(object):

    default_text = '[B]ack to main menu | [S]elect a file/dir | [N]ew directory | [R]ename file/dir | [P]roperties | [H]elp | [Q]uit'

    def __init__(self):
        self.txt = urwid.Text(self.default_text)

    def build(self):
        return urwid.AttrWrap(self.txt, 'footer')

    def set(self, text=False):
        if not text:
            text = self.default_text
        self.txt.set_text(text)

class ConfigWidget(object):

    def __init__(self):
        self.errbox = urwid.AttrWrap(urwid.Text(''),'error')
        self.menu = urwid.AttrWrap(urwid.ListBox([]),'body')
        self.title = urwid.Text('')

        self.screen(None, 'home')

    def build(self):

        return urwid.Padding(MainContainer([('pack',urwid.Divider(' ')),('pack',urwid.AttrWrap(self.title,'details')),('pack',urwid.Divider(' ')), self.menu]), left=5, right=5, width=120, align='center')

    def screen(self, d, screen):
        if screen == 'home':
            self.menu.original_widget = self.home()
        if screen == 'dirs':
            self.menu.original_widget = self.dirs()
        if screen == 'theme':
            self.menu.original_widget = self.theme()
        if screen == 'sync':
            self.menu.original_widget = self.sync()
        if screen == 'updown':
            self.menu.original_widget = self.updown()

    def updown(self):
        self.cfg = CONFIG.get()
        cfg_menu = []
        if 'connection_tout' not in self.cfg:
            self.cfg['connection_tout'] = 30
        if 'large_upload_size' not in self.cfg:
            self.cfg['large_upload_size'] = 100
        if 'chunk_size' not in self.cfg:
            self.cfg['chunk_size'] = 10
        if 'daily_limit' not in self.cfg:
            self.cfg['daily_limit'] = 0
        connection_tout = urwid.IntEdit('Connection timeout:', self.cfg['connection_tout'])
        urwid.connect_signal(connection_tout,'change',self.change_temp_cfg, 'connection_tout')
        conn_row = urwid.Columns([(26,connection_tout),(7,urwid.Text('seconds'))])
        cfg_menu.append(conn_row)
        cfg_menu.append(urwid.Divider(' '))
        large_upl_n = urwid.IntEdit('Split uploads larger than [ ', self.cfg['large_upload_size'])
        urwid.connect_signal(large_upl_n,'change',self.change_temp_cfg, 'large_upload_size')
        chunk = urwid.IntEdit('in to [ ', self.cfg['chunk_size'])
        urwid.connect_signal(chunk,'change',self.change_temp_cfg, 'chunk_size')
        chunkn_row = urwid.Columns([(33,large_upl_n),(7,urwid.Text('MB ] ')), (11,chunk), (12,urwid.Text('MB ] chunks '))])
        cfg_menu.append(chunkn_row)
        cfg_menu.append(urwid.Divider(' '))
        daily_limit = urwid.IntEdit('Daily upload/download limit: ', self.cfg['daily_limit'])
        urwid.connect_signal(daily_limit,'change',self.change_temp_cfg, 'daily_limit')
        daily_row = urwid.Columns([(36,daily_limit), (19,urwid.Text('MB (0 = no limit) '))])
        cfg_menu.append(daily_row)
        cfg_menu.append(urwid.Divider(' '))
        save = urwid.Button('Save and exit')
        urwid.connect_signal(save,'click',self.save_updown)
        back = urwid.Button('Exit without saving')
        urwid.connect_signal(back,'click',self.screen, 'home')
        cfg_menu.append(style_btn(save))
        cfg_menu.append(style_btn(back))
        return urwid.ListBox(cfg_menu)

    def save_updown(self, w):
        update_config(self.cfg)
        self.screen(None, 'home')

    def theme(self):
        outlist = []
        opts = palettes.keys()
        if CONFIG.get('palette'):
            p = CONFIG.get('palette')
        else: p = 'light'
        for name in opts:
            if name == p:
                outlist.append(urwid.CheckBox(name, state=True, user_data=name, on_state_change=self.set_theme))
            else:
                outlist.append(urwid.CheckBox(name, state=False, user_data=name, on_state_change=self.set_theme))
        back = urwid.Button('Back')
        outlist.append(urwid.Divider(' '))
        outlist.append(style_btn(back))
        urwid.connect_signal(back,'click',self.screen, 'home')
        return urwid.ListBox(outlist)

    def set_theme(self, w, state, name):
        CONFIG.set(name, 'palette')
        LOOP.screen.register_palette(palettes[name])
        LOOP.screen.clear()
        self.screen(None, 'theme')

    def home(self):
        self.title.set_text('Select an option below')
        opt_dirs = urwid.Button('Set the locations for your PiDrop directories')
        urwid.connect_signal(opt_dirs,'click',self.screen, 'dirs')
        opt_sync = urwid.Button('Select which Dropbox directories to sync')
        urwid.connect_signal(opt_sync,'click',self.screen, 'sync')
        opt_theme = urwid.Button('Select a theme')
        urwid.connect_signal(opt_theme,'click',self.screen, 'theme')
        opt_updown = urwid.Button('Upload/download settings')
        urwid.connect_signal(opt_updown,'click',self.screen, 'updown')

        back = urwid.Button('Back')
        urwid.connect_signal(back,'click', WINDOW.screen, 'welcome')
        return urwid.ListBox([style_btn(opt_dirs),style_btn(opt_sync),style_btn(opt_updown),style_btn(opt_theme),urwid.Divider(' '),style_btn(back)])

    def sync(self):
        if CONFIG.get('all_remote_folders'):
            outlist = []
            if CONFIG.get('sync_depth'):
                sd = CONFIG.get('sync_depth')
            else: sd = 1
            leveldown = urwid.Button(' - ')
            level = urwid.Text(' Directory Depth: %d' % (sd))
            levelup = urwid.Button(' + ')
            level_ctrl = urwid.Columns([(7,urwid.AttrWrap(leveldown,'button')),(20,level),(7,urwid.AttrWrap(levelup,'button'))])
            urwid.connect_signal(leveldown, 'click', self.change_sync_depth, sd-1)
            urwid.connect_signal(levelup, 'click', self.change_sync_depth, sd+1)
            remote_folders = CONFIG.get('all_remote_folders')['folders'] #list_remote_folders()
            outlist.append(level_ctrl)
            upd = urwid.Button('Update List')
            urwid.connect_signal(upd,'click',self.update_folder_list)
            update_row = urwid.Columns([(15, urwid.AttrWrap(upd, 'details')),urwid.Text('(Last updated %s)' % (CONFIG.get('all_remote_folders')['upd']))])
            outlist.append(urwid.Divider(' '))
            outlist.append(update_row)
            outlist.append(urwid.Divider(' '))
            for name in remote_folders:
                name =name.strip(os.sep)
                depth = name.count(os.sep)
                if depth < sd:
                    display_txt = '%s %s' % ('  '*depth, name.split(os.sep)[-1])
                    if name in CONFIG.get('folders'):
                        outlist.append(urwid.CheckBox(display_txt, state=True, user_data=name, on_state_change=self.set_sync))
                    else:
                        outlist.append(urwid.CheckBox(display_txt, state=False, user_data=name, on_state_change=self.set_sync))
            back = urwid.Button('Back')
            outlist.append(urwid.Divider(' '))
            outlist.append(self.errbox)
            outlist.append(style_btn(back))
            urwid.connect_signal(back,'click',self.screen, 'home')
            return urwid.ListBox(outlist)
        else:
            msg = urwid.Text('You haven\'t yet retrieved your directory structure from Dropbox. Please click the button below. This may take a few minutes...')
            btn = urwid.Button('Fetch list')
            urwid.connect_signal(btn,'click',self.update_folder_list)
            return urwid.ListBox([msg, urwid.Divider(' '), btn])

    def update_folder_list(self, d):
        folders = self.retrieve_folder_list()
        CONFIG.set({
            'folders':folders,
            'upd':str(datetime.datetime.now())
        }, 'all_remote_folders')
        self.screen(None, 'sync')

    def retrieve_folder_list(self, cursor=None):
        if cursor is not None:
            res = DBX.files_list_folder_continue(cursor)
        else:
            res = DBX.files_list_folder('', recursive=True)
        folders = []
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                folders.append(entry.path_lower)
        if res.has_more:
            folders.extend(self.retrieve_folder_list(res.cursor))
        folders.sort()
        return folders

    def change_sync_depth(self, w,i):
        folders = CONFIG.get('folders')
        if i < 1:
            i = 1
        if i > 5:
            i = 5
        for f in folders:
            if f.count('/') > i-1:
                folders.remove(f)
        CONFIG.set(folders, 'folders')
        CONFIG.set(i, 'sync_depth')
        self.screen(None, 'sync')

    def set_sync(self, w, state, name):
        folders = CONFIG.get('folders')
        if name in folders:
            if not state:
                folders.remove(name)
        elif state:
            folders.append(name)
        CONFIG.set(folders, 'folders')

    def dirs(self):
        self.cfg = CONFIG.get()
        root_dir = urwid.Edit('PiDrop Root Directory: ', self.cfg['rootdir'])
        urwid.connect_signal(root_dir,'change',self.change_temp_cfg, 'rootdir')
        import_dir = urwid.Edit('Imports Directory: ', self.cfg['import-dir'])
        urwid.connect_signal(import_dir,'change',self.change_temp_cfg, 'import-dir')
        export_dir = urwid.Edit('Exports Directory: ', self.cfg['export-dir'])
        urwid.connect_signal(export_dir,'change',self.change_temp_cfg, 'export-dir')
        save = urwid.Button('Save and exit')
        urwid.connect_signal(save,'click',self.save_dirs)
        back = urwid.Button('Exit without saving')
        urwid.connect_signal(back,'click',self.screen, 'home')
        cfg_menu = [root_dir,import_dir,export_dir,self.errbox]
        cfg_menu.append(style_btn(save))
        cfg_menu.append(style_btn(back))
        return urwid.ListBox(cfg_menu)

    def change_temp_cfg(self, w, v, setting):
        self.cfg[setting] = v

    def save_dirs(self, w):
        if not os.path.isdir(self.cfg['rootdir']):
            self.errbox.set_text('\nRoot Directory is not a valid directory\n')
        elif not os.path.isdir(self.cfg['export-dir']):
            self.errbox.set_text('\nExport Directory is not a valid directory\n')
        elif not os.path.isdir(self.cfg['import-dir']):
            self.errbox.set_text('\nImport Directory is not a valid directory\n')
        else:
            update_config(self.cfg)
            self.screen(None, 'dirs')


class PiDropWindow(object):

    screens = {}
    prompts = {
        'welcome':' ',
        'browser':False,
        'help':'[B]ack to main menu | [F]ile browser | [C]onfig | [Q]uit',
        'config':'[B]ack to main menu | [F]ile browser | [H]elp | [Q]uit'
    }

    def __init__(self):
        global DBX
        global KEYPROMPT
        KEYPROMPT = KeyPromptWidget()
        DBX = connect_dbx()
        self.palette = self.set_palette()
        self.main = urwid.AttrWrap(urwid.ListBox([]), 'body')
        self.screen(None, 'welcome')
        self.header = urwid.Text('PiDrop - manage your dropbox')
        self.footer = urwid.Pile([urwid.Divider(' '),KEYPROMPT.build(),urwid.Divider(' ')])

    def screen(self, d, screen):
        if 'LOOP' in globals():
            loading(self.main)
        if screen in self.screens:
            self.main.original_widget = self.screens[screen]
        elif screen == 'welcome':
            self.screens[screen] = self.welcome()
            self.main.original_widget = self.screens[screen]
        elif screen == 'browser':
            self.screens[screen] = self.browser()
            self.main.original_widget = self.screens[screen]
        elif screen == 'help':
            self.screens[screen] = self.help()
            self.main.original_widget = self.screens[screen]
        elif screen == 'config':
            self.screens[screen] = self.config()
            self.main.original_widget = self.screens[screen]
        KEYPROMPT.set(self.prompts[screen])

    def set_palette(self):
        if CONFIG.get('palette'):
            return palettes[CONFIG.get('palette')]
        else: return palettes['light']

    def build(self):
        return urwid.AttrWrap(urwid.Frame(
            self.main,
            header=urwid.AttrWrap(self.header, 'header'),
            footer=urwid.AttrWrap(self.footer, 'footer')
        ),'body')

    def welcome(self):
        welcome = urwid.AttrWrap(urwid.LineBox(urwid.Text('Select an option below by either clicking the option or pressing the associated key')),'details')
        browser_btn = urwid.Button('[F]ile Browser/Manager')
        urwid.connect_signal(browser_btn,'click',self.screen, 'browser')
        config_btn  = urwid.Button('[C]onfigure PiDrop')
        urwid.connect_signal(config_btn,'click',self.screen, 'config')
        help_btn  = urwid.Button('[H]elp')
        urwid.connect_signal(help_btn,'click',self.screen, 'help')
        options = urwid.ListBox([style_btn(browser_btn),style_btn(config_btn),style_btn(help_btn)])
        return urwid.Padding(urwid.Filler(MainContainer([('pack',urwid.Divider(' ')),('pack',welcome),('pack',urwid.Divider(' ')), options]), height=10), left=5, right=5, width=70, align='center')

    def help(self):
        data = help_questions
        topnode = HelpParentNode(data)
        helplist = urwid.AttrWrap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'body')
        nfo = urwid.LineBox(urwid.Text("""
            Welcome to the help menu.
            -------------------------
            Use your mouse or the arrow keys on your keyboard to navigate through though question/answer list below.

            Throughout this UI you will find a list of available keys for the current screen in the footer."""))
        return MainContainer([('pack',urwid.Divider(' ')),('pack',nfo),('pack',urwid.Divider(' ')), helplist])

    def config(self):
        w = ConfigWidget()
        return w.build()

    def browser(self):
        global IMPORTER
        global EXPORTER
        global PROPSBOX
        global BROWSER
        global SEARCHBAR
        global NOTIFIER
        global SYNCED_FILES

        SYNCED_FILES = SyncedFiles()
        IMPORTER = ImporterWidget(CONFIG.get('import-dir'), 'importer', 'Import Folder')
        EXPORTER = ExporterWidget(CONFIG.get('export-dir'), 'exporter', 'Export Folder')
        PROPSBOX = PropsWidget()
        BROWSER = FileBrowserWidget()
        SEARCHBAR = SearchBarWidget()
        NOTIFIER = NotificationsWidget()

        self.right = urwid.AttrWrap(
            urwid.Padding(
                urwid.Pile([
                    ('pack',urwid.Divider(' ')),
                    urwid.LineBox(PROPSBOX.build()),
                    urwid.LineBox(IMPORTER.build()),
                    urwid.LineBox(EXPORTER.build())]
                ),
                right=1
            ),
            'body'
        )
        self.left = urwid.AttrWrap(urwid.Pile([
            ('pack',NOTIFIER.build()),
            urwid.Padding(BROWSER.build(), left=1, right=1),
            ('pack',urwid.Divider(' ')),
            ('pack',urwid.Padding(SEARCHBAR.build(), left=2, right=2))
        ]),'body')

        return MainContainer([urwid.Columns([('weight', 3,self.left), self.right])])

class Cfg(object):

    def __init__(self):
        self.data = self.load()

    def get(self, key=False):
        if not key:
            return self.data
        elif key in self.data:
            return self.data[key]
        return false

    def load(self):
        if not os.path.isfile(CWD+'/cfg.json'):
            return {}
        with open(CWD+'/cfg.json') as json_file:
            return json.load(json_file)

    def set(self, data, key=False):
        if key:
            self.data[key] = data
        else:
            self.data = data
        with open(CWD+'/cfg.json', 'w') as outfile:
                json.dump(self.data, outfile)

class SyncedFiles(object):

    def __init__(self):
        self.files = self.load()

    def load(self):
        if not os.path.isfile(CWD+'/flist.json'):
            return {}
        else:
            with open(CWD+'/flist.json') as json_file:
                return json.load(json_file)

    def get(self, key):
        if key in self.files:
            return self.files[key]
        return False

    def set(self, data, key=False):
        if key:
            self.files[key] = data
        else:
            self.files = data
        self.save_to_file()

    def unset(self, key):
        if key in self.files:
            del self.files[key]
        self.save_to_file()

    def save_to_file(self):
        with open(CWD+'/flist.json', 'w') as fp:
            json.dump(self.files, fp)

def unhandled_input(k):
    # update display of focus directory
    if k in ('q','Q'):
        raise urwid.ExitMainLoop()

def loading(target):
    pile = urwid.Filler(MainContainer([('pack',urwid.Divider(' ')),('pack',urwid.AttrWrap(urwid.Text('Loading...'),'loading')),('pack',urwid.Divider(' '))]), height=10)
    target.original_widget = urwid.AttrWrap(urwid.Frame(
        urwid.Padding(pile, left=5, right=5, width=10, align='center')
    ),'body')
    LOOP.draw_screen()

def style_btn(btn):
    return urwid.AttrWrap(btn,'button', 'button focus')

def connect_dbx():
    if CONFIG.get('connection_tout'):
        tout = CONFIG.get('connection_tout')
    else:
        tout = 30

    connect = dropbox.Dropbox(CONFIG.get('token'), timeout=int(tout))
    try:
        connect.users_get_current_account()
    except:
        sys.exit("ERROR: Invalid access token; try re-generating an access token from the app console on the web.")
    return connect

def ui_init():
    global LOOP
    global WINDOW
    global CONFIG
    CONFIG = Cfg()
    WINDOW = PiDropWindow()
    LOOP = urwid.MainLoop(WINDOW.build(), WINDOW.palette, unhandled_input=unhandled_input)
    LOOP.run()
