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
            if len(self.get_edit_text())>0:
                SEARCHBAR.build_search_list()
            else:
                NOTIFIER.set('you didn\'t enter a search term!', 'error')
        elif key == 'esc':
            WINDOW.frame.set_state('default')
            WINDOW.frame.set_focus_path(['body',0,0,1])
            SEARCHBAR.clear_search_list()
        elif key == 'up':
            if 'SEARCHLIST' in globals():
                WINDOW.frame.set_focus_path(['body',0,0,3])
            else:
                WINDOW.frame.set_focus_path(['body',0,0,1])
        elif key == 'right':
            WINDOW.frame.set_focus_path(['body',0,0,3,1])
        elif  len(self.get_edit_text())>0:
            if len(BROWSER.listbox.selected) > 0:
                BROWSER.listbox.selected = []
                BROWSER.listbox.body.reset_all_nodes_style()
            WINDOW.frame.set_state('search focussed')
        else:
            if len(BROWSER.listbox.selected) > 0:
                BROWSER.listbox.selected = []
                BROWSER.listbox.body.reset_all_nodes_style()
            WINDOW.frame.set_state('search empty')

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
                try:
                    res = DBX.files_create_folder_v2(
                        remote_path,
                        autorename=True)
                except dropbox.exceptions.ApiError as err:
                    NOTIFIER.set('*** API error: '+ str(err))
                    WINDOW.frame.set_state('default')
                    return None
                new_local_loc = self.target_dir+os.sep+os.path.basename(res.metadata.path_lower)
                os.mkdir(new_local_loc)
                NOTIFIER.set('New directory %s created at %s' % (dirname,self.target_dir), 'success')
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
            WINDOW.frame.set_state('default')

        elif key == 'esc':
            WINDOW.frame.set_state('default')
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
            WINDOW.frame.set_state('default')
            return None
        new_local_path = os.sep + CONFIG.get('rootdir').strip(os.sep) + res.metadata.path_lower
        try:
            os.rename(self.target_dir, new_local_path)
        except OSError as err:
            NOTIFIER.set(err,'error')
            return
        NOTIFIER.set('%s > renamed to > %s' % (self.target_dir[rootlen:],new_local_path[rootlen:]),'success')
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
        self._w = urwid.AttrMap(self._w, None)

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
                self._w.attr_map = {None:'file select'}
                self._w.focus_map = {None:'file select focus'}
            else:
                self._w.attr_map = {None:'dir select'}
                self._w.focus_map = {None:'dir select focus'}
        else:
            if  os.path.isfile(self.full_path):
                self._w.attr_map = {None:'file'}
                self._w.focus_map = {None:'file focus'}
            else:
                self._w.attr_map = {None:'dir'}
                self._w.focus_map = {None:'dir focus'}

    def load_inner_widget(self):
        # if we have a shared folder create a label for it
        if 'shared' in self.get_node().get_value():
            shared = urwid.AttrMap(urwid.Text('[shared]'), 'shared')
        else:
            shared = urwid.Text('')
        # if our path exists in flist then get the display name
        if SYNCED_FILES.get(self.full_path):
            fname = SYNCED_FILES.get(self.full_path)['name']
        else:
            fname = self.name
        # if we're at the root node simply set a textual name
        if self.get_node().get_depth()<1:
            self.inner_w =  urwid.Text('[1] '+self.name)
        # otherwise try to determine sync status
        elif 'sync' in self.get_node().get_value():
            self.sync_status = self.get_node().get_value()['sync']
            if self.sync_status == 'sync':
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrMap(
                                            urwid.Text(u"\u25CF"),
                                            'sync')),
                                (len(fname)+1,
                                            urwid.Text(fname)),
                                (8,shared)
                            ])
            elif self.sync_status == 'unsync':
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrMap(
                                            urwid.Text(u"\u25CB"),'unsync')),
                                (len(fname)+1,urwid.Text(fname)),
                                (8,shared)
                            ])
            else:
                self.inner_w = urwid.Columns([
                                (2, urwid.AttrMap(
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
                self.path_properties_data.append(urwid.AttrMap(urwid.Text('[ SYNCED ]'),'sync'))
            elif self.sync_status == 'unsync':
                self.path_properties_data.append(urwid.AttrMap(urwid.Text('[ SYNCING ]'),'unsync'))
            else:
                self.path_properties_data.append(urwid.AttrMap(urwid.Text('[ NOT SYNCED ]'),'nosync'))
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
        BROWSER.listbox_container.original_widget =  urwid.AttrMap(urwid.ListBox([inputbox]), 'search_box_active')

    def new_dir(self):
        if os.path.isdir(self.full_path):
            new_dir_location = self.full_path
        else:
            new_dir_location = self.path
        caption = 'New directory name:\n'
        inputbox = PiDropDirInput(caption, 'new_dir', new_dir_location)
        BROWSER.listbox_container.original_widget =  urwid.AttrMap(urwid.ListBox([inputbox]), 'search_box_active')

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
        self._w = urwid.AttrMap(self._w, None)
        self._w.attr_map = {None:'importer'}
        self._w.focus_map = {None:'importer focus'}

    def get_display_text(self):
        return self.get_node().get_value()['name']

    def selectable(self):
        return True

    def set_style(self):

        if self.full_path in IMPORTER.listbox.selected:
            self._w.attr_map = {None:'dir select'}
            self._w.focus_map = {None:'dir select focus'}
        else:
            self._w.attr_map = {None:'importer'}
            self._w.focus_map = {None:'importer focus'}

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
        self._w = urwid.AttrMap(self._w, None)
        self._w.attr_map = {None:'exporter'}
        self._w.focus_map = {None:'exporter focus'}

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

        if not WINDOW.frame.is_allowed_key(key):
            return key

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
        self._w = urwid.AttrMap(self._w, None)
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

class PiDropTreeList(urwid.TreeListBox):

    selected = [] # List of paths that are selected for operations
    fmode = None # path operation mode (move, delete,...)

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):

        if not WINDOW.frame.is_allowed_key(key):
            return key

        w = self.body.focus.get_widget()

        if key in ["s", "S"]:
            self.add_to_selected()
            if len(self.selected) > 0:
                WINDOW.frame.set_state('files selected')
            else:
                WINDOW.frame.set_state('default')

        elif key in ['m','M']:
            self.confirm_move_files()

        elif key in ['d','D']:
            self.confirm_del_files()
            WINDOW.frame.set_state('confirm delete')

        elif key in ['e','E']:
            self.confirm_export_files()
            WINDOW.frame.set_state('confirm export')

        elif key in ["i", "I"]:
            self.confirm_import_files()

        elif key in ["n",'N']:
            w.new_dir()
            WINDOW.frame.set_state('new dir')

        elif key in ["r", "R"]:
            w.init_rename_path()
            WINDOW.frame.set_state('rename')

        elif key in ["p", "P"]:
            w.more_path_details()

        elif key == 'enter':

            WINDOW.frame.set_state('default')

            if self.fmode == 'move':
                self.move_files()

            elif self.fmode == 'delete':
                self.delete_files()

            elif self.fmode == 'export':
                self.export_files()

            elif self.fmode == 'import':
                self.import_files()

        elif key == 'esc':
            IMPORTER.listbox.reset()
            self.reset()

        else:
            return key

    def reset(self):
        self.selected = []
        self.fmode = None
        WINDOW.frame.set_state('default')
        NOTIFIER.clear(None)
        self.reload_walker()

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
        w.set_style(self.selected)

    def confirm_move_files(self):
        if len(self.selected) > 0:
            self.fmode = 'move'
            WINDOW.frame.set_state('confirm move')
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
        self.selected = []
        self.fmode = None

    def confirm_del_files(self):
        if len(self.selected) < 1:
            self.add_to_selected()
        self.fmode = 'delete'

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
        self.selected = []
        self.fmode = None
        self.reload_walker()

    def confirm_export_files(self):
        if len(self.selected) < 1:
            self.add_to_selected()
        self.fmode = 'export'

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
        EXPORTER.listbox.reload_walker()
        self.body.reset_all_nodes_style()

    def confirm_import_files(self):
        if len(IMPORTER.listbox.selected) > 0:
            self.fmode = 'import'
            WINDOW.frame.set_state('confirm import')
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
        self.reload_walker()
        IMPORTER.listbox.reload_walker()
        NOTIFIER.set('%d Selected files and folders were imported.' % (i), 'success')
        IMPORTER.listbox.selected = []
        IMPORTER.listbox.set_importer_state()
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

        if not WINDOW.frame.is_allowed_key(key):
            return key

        if key in ["s", "S"]:
            self.add_to_selected()
            BROWSER.listbox.selected = []
            BROWSER.listbox.body.reset_all_nodes_style()
        elif key in ["a", "A"]:
            self.select_all_toggle()
            BROWSER.listbox.selected = []
            BROWSER.listbox.body.reset_all_nodes_style()
        elif key in ["p", "P"]:
            self.body.focus.get_widget().more_path_details()
        elif key == 'esc':
            self.reset()
            WINDOW.frame.set_state('importer focussed')
        else:
            return key

    def reset(self):
        self.selected = []
        self.reload_walker()

    def select_all_toggle(self):
        nodes = self.body.__iter__()
        if len(self.selected) < 1:
            all = True
        else: all = False
        self.selected = []
        for node in nodes:
            w = node.get_widget()
            if os.path.isdir(w.full_path):
                if node.get_depth() > 0:
                    w.expanded = False
                else:
                    w.expanded = True
                w.update_expanded_icon()
            if all and node.get_depth()==1:
                self.selected.append(w.full_path)
            w.set_style()
        self.set_importer_state()

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
            else:
                self.selected.append(w.full_path)
                if os.path.isdir(w.full_path):
                    w.expanded = False
                    w.update_expanded_icon()
            w.set_style()
            self.set_importer_state()

    def set_importer_state(self):
        if len(self.selected) > 0:
            WINDOW.frame.set_state('importer files selected')
        else:
            WINDOW.frame.set_state('importer focussed')

    def reload_walker(self):
        loading(IMPORTER.listbox_container)
        data = IMPORTER.get_dir()[0]
        topnode = ImporterParentNode(data)
        self.body = DirWalker(topnode)
        IMPORTER.listbox_container.original_widget = urwid.Padding(IMPORTER.listbox, left=2, right=2)

class ExporterTreeList(urwid.TreeListBox):

    def reload_walker(self):
        loading(EXPORTER.listbox_container)
        data = EXPORTER.get_dir()[0]
        topnode = ExporterParentNode(data)
        self.body = DirWalker(topnode)
        EXPORTER.listbox_container.original_widget = urwid.Padding(EXPORTER.listbox, left=2, right=2)

class DirFrame(urwid.Frame):

    def __init__(self, body, header, footer, p):
        self.__super.__init__(body, header, footer)
        self.parent = p

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):

        if not WINDOW.frame.is_allowed_key(key):
            return key

        if key in ['e', 'E']:
            self.parent.empty(None)

        elif key in ['r','R']:
            self.parent.reload(None)

        else:
            return key

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
        empty = urwid.Button('Empty')
        urwid.connect_signal(empty, 'click', self.empty)
        reload = urwid.Button('Reload')
        urwid.connect_signal(reload, 'click', self.reload)
        return urwid.Columns([(9,empty),urwid.Divider('   '),(10,reload)])

    def build(self):
        footer = urwid.Padding(self.btns, left=2, right=2)
        footer = urwid.Pile([urwid.Divider(' '),footer,urwid.Divider(' ')])
        footer = urwid.AttrMap(footer, 'footer')
        self.listbox_container = urwid.AttrMap(urwid.Padding(self.listbox, left=2, right=2), self.style)
        self.frame = DirFrame(
            self.listbox_container,
            header = urwid.AttrMap(urwid.Text(self.title), 'header'),
            footer = urwid.AttrMap(footer, 'footer'),
            p = self
        )
        return self.frame

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
        lb = urwid.AttrMap(self.listbox, 'body')
        self.listbox_container = urwid.AttrMap(urwid.Frame(lb), 'body')
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
        self.content = urwid.AttrMap(
                            urwid.ListBox([
                                    urwid.Text('file and folder details will appear here')
                            ]),'body')

    def build(self):
        pile = urwid.Pile([self.content])
        self.frame = urwid.Frame(
            urwid.AttrMap(urwid.Padding(pile, left=2, right=2),'body'),
            header=urwid.AttrMap(urwid.Text('File/Directory Properties'), 'body')
        )
        self.frame._selectable =False
        return self.frame

class SearchBarWidget(object):

    search_term = None
    in_folder = False # folder to perform search in. False = all
    regex = False

    state = 'search empty'

    def __init__(self):
        self.inputbox = self.set_inputbox()

    def build(self):
        ftog = urwid.CheckBox('current folder only', on_state_change=self.ftoggle)
        regextog = urwid.CheckBox('regex', on_state_change=self.regextoggle)
        self.bar = urwid.Columns([urwid.AttrMap(self.inputbox, 'search_box'),(24, ftog),(10, regextog) ])

        def focus_changed(pos):
            self.bar._invalidate()
            if pos == 0:
                if len(self.inputbox.get_edit_text()) > 0:
                    self.state = 'search focussed'
                else:
                    self.state = 'search empty'
            else:
                self.state = 'search opts'

            WINDOW.frame.set_state(self.state)

        self.bar._contents.set_focus_changed_callback(focus_changed)

        return self.bar



    def set_inputbox(self):
        inp = PiDropSearchInput('[2] Search:')
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


    def clear_search_list(self,d=None):
        global SEARCHLIST
        self.inputbox.set_edit_text('')
        self.search_term = None
        if 'SEARCHLIST' in globals():
            del SEARCHLIST
            WINDOW.left.original_widget = urwid.Pile([
                ('pack',NOTIFIER.message),
                urwid.Padding(BROWSER.listbox, left=1, right=1),
                ('pack',urwid.Divider(' ')),
                ('pack',urwid.Padding(self.bar, left=2, right=2))
            ])

class SearchListWidget(object):

    def __init__(self):
        self.listbox = self.set_listbox()

    def set_listbox(self):
        data = self.get_search_list()
        topnode = PiDropParentNode(data)
        walker = PiDropWalker(topnode)
        return urwid.AttrMap(urwid.TreeListBox(walker),'body')

    def build(self):
        close_search = urwid.Button('close')
        urwid.connect_signal(close_search, 'click', SEARCHBAR.clear_search_list)
        return urwid.Pile([
            ('pack',NOTIFIER.message),
            urwid.Padding(BROWSER.listbox, left=1, right=1),
            urwid.Padding(urwid.AttrMap(urwid.LineBox(urwid.Columns([self.listbox,(9,urwid.ListBox([close_search]))])),'body'), left=1, right=1),
            ('pack',urwid.Padding(SEARCHBAR.bar, left=2, right=2))
        ],3)

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
        self.message = urwid.AttrMap(urwid.Text(''), 'body')

    def build(self):
        return self.message

    def set(self, msg, attr='notif'):
        close = urwid.Button('X')
        urwid.connect_signal(close, 'click', self.clear)
        outp = urwid.Padding(urwid.Text('\n%s\n' % (msg)),left=2,right=2)
        cols = urwid.AttrMap(urwid.Columns([outp, (5, close)]),attr)
        self.message.original_widget = cols

    def clear(self, d):
        self.message.original_widget = urwid.AttrMap(urwid.Text(''), 'body')

class KeyPromptWidget(object):

    default_text = '[B]ack to main menu | [S]elect a file/dir | [N]ew directory | [R]ename file/dir | [P]roperties | [H]elp | [Q]uit'

    def __init__(self):
        self.txt = urwid.Text(self.default_text)

    def build(self):
        return urwid.AttrMap(self.txt, 'footer')

    def set(self, text=False):
        if not text:
            text = self.default_text
        self.txt.set_text(text)

class ConfigWidget(object):

    def __init__(self):
        self.errbox = urwid.AttrMap(urwid.Text(''),'error')
        self.menu = urwid.AttrMap(urwid.ListBox([]),'body')
        self.title = urwid.Text('')

        self.screen(None, 'home')

    def build(self):

        return urwid.Padding(urwid.Pile([('pack',urwid.Divider(' ')),('pack',urwid.AttrMap(self.title,'details')),('pack',urwid.Divider(' ')), self.menu]), left=5, right=5, width=120, align='center')

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
            level_ctrl = urwid.Columns([(7,urwid.AttrMap(leveldown,'button')),(20,level),(7,urwid.AttrMap(levelup,'button'))])
            urwid.connect_signal(leveldown, 'click', self.change_sync_depth, sd-1)
            urwid.connect_signal(levelup, 'click', self.change_sync_depth, sd+1)
            remote_folders = CONFIG.get('all_remote_folders')['folders'] #list_remote_folders()
            outlist.append(level_ctrl)
            upd = urwid.Button('Update List')
            urwid.connect_signal(upd,'click',self.update_folder_list)
            update_row = urwid.Columns([(15, urwid.AttrMap(upd, 'details')),urwid.Text('(Last updated %s)' % (CONFIG.get('all_remote_folders')['upd']))])
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

class PiDropMainFrame(urwid.Frame):

    states = {
        'welcome':{
            'current':'default',
            'states':{
                'default':{
                    'prompt':'[F]ile Browser | [C]onfig | [H]elp | [Q]uit'
                }
            }
        },
        'browser':{
            'current':'default',
            'states':{
                'default':{
                    'prompt':'[B]ack to main menu | [S]elect a file/dir | [N]ew directory | [R]ename file/dir | [P]roperties | [H]elp | [Q]uit',
                    'keys':['b','s','n','r','p','h','q','d','e','esc']
                },
                'files selected':{
                    'prompt':'[S]elect a file/dir | [M]ove selected files | [D]elete selected files | [E]xport selected files | [ESC] Cancel',
                    'keys':['s','m','d','e','esc']
                },
                'confirm move':{
                    'prompt':'Select (focus) the destination and hit [ENTER] to confirm moving the selected files | [ESC] Cancel',
                    'keys':['enter','esc']
                },
                'confirm delete':{
                    'prompt':'Press [ENTER] to confirm deletion of the selected files | [ESC] Cancel',
                    'keys':['enter','esc']
                },
                'confirm export':{
                    'prompt':'Press [ENTER] to confirm copying the selected files to the export folder | [ESC] Cancel',
                    'keys':['enter','esc']
                },
                'confirm import':{
                    'prompt':'Press [ENTER] to confirm copying the selected files from the imports folder to here | [ESC] Cancel',
                    'keys':['enter','esc']
                },
                'rename':{
                    'prompt':'[ENTER] to confirm | [ESC] to cancel and go back to previous screen',
                    'keys':['enter','esc']
                },
                'new dir':{
                    'prompt':'[ENTER] to confirm creation of new dir | [ESC] to cancel and go back to previous screen',
                    'keys':['enter','esc']
                },
                'search empty':{
                    'prompt':'type a search term and hit [ENTER] to search | [ESC] to cancel',
                    'keys':['enter','esc']
                },
                'search focussed':{
                    'prompt':'[ENTER] to search | [ESC] to cancel',
                    'keys':['enter','esc']
                },
                'search opts':{
                    'prompt':'[ENTER] select/deselect',
                    'keys':['enter']
                },
                'exporter focussed':{
                    'prompt':'[E]mpty | [R]eload | [P]roperties',
                    'keys':['e','r', 'p']
                },
                'importer focussed':{
                    'prompt':'[S]elect/deselect | [A]ll/none | [E]mpty | [R]eload | [P]roperties',
                    'keys':['s','a','e','r','p']
                },
                'importer files selected':{
                    'prompt':'Focus an item in the main browser and hit [i] to import the files there | [ESC] Cancel',
                    'keys':['i','esc','p','s']
                }
            }
        },
        'config':{
            'current':'default',
            'states':{
                'default':{
                    'prompt':'config default'
                }
            }
        },
        'help':{
            'current':'default',
            'states':{
                'default':{
                    'prompt':'help default'
                }
            }
        }
    }

    screen = 'welcome'

    def keypress(self, size, key):
        key = self.__super.keypress(size, key)
        if key:
            key = self.unhandled_keys(size, key)
        return key

    def unhandled_keys(self, size, key):

        if key in ['b', 'B']:
            WINDOW.screen(None, 'welcome')
            self.set_screen('welcome')

        elif key in ["f", "F"]:
            WINDOW.screen(None, 'browser')
            self.set_screen('browser')

        elif key in ["c", "C"]:
            WINDOW.screen(None, 'config')
            self.set_screen('config')

        elif key in ["h", "H"]:
            WINDOW.screen(None, 'help')
            self.set_screen('help')

        elif key == '1':
            WINDOW.frame.set_focus_path(['body',0,0,1])

        elif key == '2':
            WINDOW.frame.set_focus_path(['body',0,0,3,0])

        elif key == '3':
            WINDOW.frame.set_focus_path(['body',0,1,2])

        elif key == '4':
            WINDOW.frame.set_focus_path(['body',0,1,3])


        else:
            return key

    def set_screen(self, screen):
        self.screen = screen
        p = self.states[screen]['states'][self.states[screen]['current']]['prompt']
        KEYPROMPT.set('KEYS: '+p)
        WINDOW.modebox.set_text('mode: %s | default' % (self.screen))

    def set_state(self, state):
        self.states[self.screen]['current'] = state
        p = self.states[self.screen]['states'][state]['prompt']
        KEYPROMPT.set('KEYS: '+p)
        WINDOW.modebox.set_text('mode: %s | %s' % (self.screen, state))

    def is_allowed_key(self, key):
        state = self.states['browser']['current']
        if key.lower() not in self.states['browser']['states'][state]['keys']:
            return False
        return True

class PiDropWindow(object):

    screens = {}

    def __init__(self):
        global DBX
        global KEYPROMPT
        KEYPROMPT = KeyPromptWidget()
        DBX = connect_dbx()
        self.palette = self.set_palette()
        self.main = urwid.AttrMap(urwid.ListBox([]), 'body')
        self.screen(None, 'welcome')
        self.header = urwid.Text('PiDrop - manage your dropbox')
        self.modebox = urwid.Text('', align='right')
        cols = urwid.Columns([('weight',4,KEYPROMPT.build()),urwid.AttrMap(self.modebox, 'mode')])
        self.footer = urwid.Pile([urwid.Divider(' '),cols,urwid.Divider(' ')])

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

    def set_palette(self):
        if CONFIG.get('palette'):
            return palettes[CONFIG.get('palette')]
        else: return palettes['light']

    def build(self):
        self.frame = PiDropMainFrame(
            self.main,
            header=urwid.AttrMap(self.header, 'header'),
            footer=urwid.AttrMap(urwid.Padding(self.footer, left=5, right=5), 'footer')
        )
        self.frame.set_screen('welcome')
        return urwid.AttrMap(self.frame,'body')

    def welcome(self):
        welcome = urwid.AttrMap(urwid.LineBox(urwid.Text('Select an option below by either clicking the option or pressing the associated key')),'details')
        browser_btn = urwid.Button('[F]ile Browser/Manager')
        urwid.connect_signal(browser_btn,'click',self.screen, 'browser')
        config_btn  = urwid.Button('[C]onfigure PiDrop')
        urwid.connect_signal(config_btn,'click',self.screen, 'config')
        help_btn  = urwid.Button('[H]elp')
        urwid.connect_signal(help_btn,'click',self.screen, 'help')
        options = urwid.ListBox([style_btn(browser_btn),style_btn(config_btn),style_btn(help_btn)])
        return urwid.Padding(urwid.Filler(urwid.Pile([('pack',urwid.Divider(' ')),('pack',welcome),('pack',urwid.Divider(' ')), options]), height=10), left=5, right=5, width=70, align='center')

    def help(self):
        self.frame.set_screen('help')
        data = help_questions
        topnode = HelpParentNode(data)
        helplist = urwid.AttrMap(urwid.TreeListBox(urwid.TreeWalker(topnode)), 'body')
        nfo = urwid.LineBox(urwid.Text("""
            Welcome to the help menu.
            -------------------------
            Use your mouse or the arrow keys on your keyboard to navigate through though question/answer list below.

            Throughout this UI you will find a list of available keys for the current screen in the footer."""))
        return urwid.Pile([('pack',urwid.Divider(' ')),('pack',nfo),('pack',urwid.Divider(' ')), helplist])

    def config(self):
        self.frame.set_screen('config')
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

        self.frame.set_screen('browser')

        SYNCED_FILES = SyncedFiles()
        PROPSBOX = PropsWidget()
        IMPORTER = ImporterWidget(CONFIG.get('import-dir'), 'importer', '[3] Import Folder')
        EXPORTER = ExporterWidget(CONFIG.get('export-dir'), 'exporter', '[4] Export Folder')
        BROWSER = FileBrowserWidget()
        SEARCHBAR = SearchBarWidget()
        NOTIFIER = NotificationsWidget()

        right_boxes = urwid.Pile([
            ('pack',urwid.Divider(' ')),
            urwid.AttrMap(urwid.LineBox(PROPSBOX.build()), 'body', 'body_focus'),
            urwid.AttrMap(urwid.LineBox(IMPORTER.build()), 'body', 'body_focus'),
            urwid.AttrMap(urwid.LineBox(EXPORTER.build()), 'body', 'body_focus')]
        )

        def rightcol_fchanged(pos):
            right_boxes._invalidate()
            if WINDOW.frame.states['browser']['current'] != 'importer files selected':
                if pos == 2:
                    WINDOW.frame.set_state('importer focussed')
                elif pos == 3:
                    WINDOW.frame.set_state('exporter focussed')

        right_boxes._contents.set_focus_changed_callback(rightcol_fchanged)
        self.right = urwid.AttrMap(
            urwid.Padding(
                right_boxes,
                right=1
            ),
            'body'
        )
        self.left = urwid.AttrMap(urwid.Pile([
            ('pack',NOTIFIER.build()),
            urwid.Padding(BROWSER.build(), left=1, right=1),
            ('pack',urwid.Divider(' ')),
            ('pack',urwid.Padding(SEARCHBAR.build(), left=2, right=2))
        ]),'body')
        self.left.original_widget.state = 1

        def left_fchanged(pos):
            self.left.original_widget._invalidate()
            self.left.original_widget.state = pos
            if pos == 1:
                WINDOW.frame.set_state('default')
            elif pos == 3:
                WINDOW.frame.set_state(SEARCHBAR.state)

        self.left.original_widget._contents.set_focus_changed_callback(left_fchanged)

        cols = urwid.Columns([('weight', 3,self.left), self.right])

        def cols_fchanged(pos):
            cols._invalidate()
            if pos == 1:
                rightcol_fchanged(right_boxes.focus_position)
            elif WINDOW.frame.states['browser']['current'] != 'importer files selected':
                #WINDOW.frame.set_state('default')
                left_fchanged(self.left.original_widget.state)

        cols._contents.set_focus_changed_callback(cols_fchanged)

        return urwid.Pile([cols])

class Cfg(object):

    def __init__(self):
        self.data = self.load()

    def get(self, key=False):
        if not key:
            return self.data
        elif key in self.data:
            return self.data[key]
        return False

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
    pile = urwid.Filler(urwid.Pile([('pack',urwid.Divider(' ')),('pack',urwid.AttrMap(urwid.Text('Loading...'),'loading')),('pack',urwid.Divider(' '))]), height=10)
    target.original_widget = urwid.AttrMap(urwid.Frame(
        urwid.Padding(pile, left=5, right=5, width=10, align='center')
    ),'body')
    LOOP.draw_screen()

def style_btn(btn):
    return urwid.AttrMap(btn,'button', 'button focus')

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
