
#!/usr/bin/python
"""Download/sync/manage folders from Dropbox

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

                     | |__   _  _    | |/ /  __ _  (_) | |  __ _   ___ | |_  
                     | '_ \ | || |   | ' <  / _` | | | | | / _` | (_-< | ' \ 
                     |_.__/  \_, |   |_|\_\ \__,_| |_| |_| \__,_| /__/ |_||_|
                             |__/                                            
===========================================================================                                                           

"""

from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import six
import sys
import time
import unicodedata
import json
import urwid

if sys.version.startswith('2'):
    input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox

parser = argparse.ArgumentParser(description='Download/sync/manage folders from Dropbox')
parser.add_argument('funct', nargs='?', default='main',
                    help='Which process should I run')

dir_path = os.path.dirname(os.path.realpath(__file__))

def main():
    open(dir_path+"/pibox.log", 'w').close()
    dblog('program started in '+dir_path)
    args = parser.parse_args()

    if not os.path.isfile(dir_path+'/cfg.json'):
        piboxd()
        format_outp('[ CONFIG FILE NOT FOUND ] Please use these commands to create one', 'fail')
        return setup()

    with open(dir_path+'/cfg.json') as json_file:  
        cfga = json.load(json_file)

    rootdir = os.path.expanduser(cfga['rootdir'])
    
    dbx = connect_dbx(cfga['token'])

    if args.funct == 'cfg':
        piboxd()
        format_outp('Type "help" for a list of commands', 'blue')
        return cfg(dbx, cfga)
    elif args.funct == 'explore':
        return explore(dbx, cfga)

    with open(dir_path+'/flist.json') as json_file:  
        flist = json.load(json_file)

    for folder in cfga['folders']:
        scan_remote_folder(dbx, folder, flist)
        upload_new(dbx, rootdir, folder, flist)

    with open(dir_path+'/flist.json', 'w') as outfile:  
        json.dump(flist, outfile)

    fetch_if_not_in_local(dbx, flist, rootdir)
    dblog('END')
    return

def connect_dbx(token):
    dbx = dropbox.Dropbox(token)
    try:
        dbx.users_get_current_account()
    except AuthError as err:
        sys.exit("ERROR: Invalid access token; try re-generating an access token from the app console on the web.")
    return dbx

def explore(dbx, cfga):
    with open(dir_path+'/flist.json') as json_file:  
        choices = json.load(json_file)
    def menu(title, choices):
        body = [urwid.Text(title), urwid.Divider()]
        for c in choices:
            button = urwid.Button(c)
            urwid.connect_signal(button, 'click', submenu, c)
            body.append(urwid.AttrMap(button, None, focus_map='reversed'))
        return urwid.ListBox(urwid.SimpleFocusListWalker(body))

    def item_chosen(button, choice):
        response = urwid.Text([u'You chose ', choice, u'\n'])
        done = urwid.Button(u'Ok')
        urwid.connect_signal(done, 'click', exit_program)
        main.original_widget = urwid.Filler(urwid.Pile([response,
            urwid.AttrMap(done, None, focus_map='reversed')]))
    def submenu(button, c):
        main.original_widget = urwid.Padding(menu(u'Directory Browser - '+c, choices[c]), left=2, right=2)

    def exit_on_q(key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    main = urwid.Padding(menu(u'Directory Browser', cfga['folders']), left=2, right=2)
    top = urwid.Overlay(main, urwid.SolidFill(u'\N{MEDIUM SHADE}'),
        align='center', width=('relative', 60),
        valign='middle', height=('relative', 60),
        min_width=20, min_height=9)
    urwid.MainLoop(top, palette=[('reversed', 'standout', '')],  unhandled_input=exit_on_q).run()
    


def setup():
    cfga = {'folders':[]}
    token = raw_input('Enter your API token: ')
    if len(token.strip()):
        cfga['token'] = token.strip()
        format_outp('token set', 'success')
    else:
        format_outp('please enter a valid token!', 'fail')
        setup()
    path = raw_input('Enter the path to a local dir where you will store your files: ')
    if os.path.isdir(path.strip()):
        cfga['rootdir'] = path.strip()
        format_outp('path set', 'success')
    else:
        format_outp('please enter a valid dir!', 'fail')
        setup()
    with open(dir_path+'/cfg.json', 'w') as outfile:  
        json.dump(cfga, outfile)
    f = open(dir_path+'/flist.json', 'w')   
    f.write('{}')
    f.close()
    format_outp('Great! That\'s the most important settings configured. Now please use the configuration guide below to make any further adjustments such as choosing Dropbox folders to sync.' , 'success')
    format_outp('Type "help" for a list of commands', 'blue')
    dbx = connect_dbx(cfga['token'])
    return cfg(dbx, cfga)

def cfg(dbx, cfga, var=None):
    if not var:
        var = raw_input('command:')
    if var == 'help':
        print('------------------')
        format_outp('Commands:', 'success')
        print("{:20} {:5} {:30}".format("token ", ":", "Display API token"))
        print("{:20} {:5} {:30}".format("set-token", ":", "Set your API token"))
        print("{:20} {:5} {:30}".format("set-rootdir", ":", "Set the local directory where you will sync your files"))
        print("{:20} {:5} {:30}".format("sync [folder] ", ":", "synchronise a local folder with a remote one"))
        print("{:20} {:5} {:30}".format("unsync [folder] ", ":", "remove a folder from the sync list"))
        print("{:20} {:5} {:30}".format("list-synced ", ":", "list the folders in the sync list"))
        print("{:20} {:5} {:30}".format("list-remote ", ":", "list remote folders at Dropbox"))
        print("{:20} {:5} {:30}".format("import-dir ", ":", "set a directory to import files from"))
        print("{:20} {:5} {:30}".format("export-dir ", ":", "set a directory to export files to"))
        print("{:20} {:5} {:30}".format("dump ", ":", "Display the config file contents (unsaved changes will not show"))
        print("{:20} {:5} {:30}".format("save ", ":", "Save all changes"))
        print("{:20} {:5} {:30}".format("exit ", ":", "Exit the config interface"))
        print('------------------')
        cfg(dbx, cfga)
    elif var == 'exit':
        with open(dir_path+'/cfg.json') as json_file:  
            cfgb = json.load(json_file)
        if cfga != cfgb:
            conf = raw_input('exit without saving? (y/n): ')
            if conf == 'y':
                return
            else:
                cfg(dbx, cfga)
        return
    elif var == 'save':
        with open(dir_path+'/cfg.json', 'w') as outfile:  
            json.dump(cfga, outfile)
        cfg(dbx, cfga)
    elif var == 'dump':
        with open(dir_path+'/cfg.json', 'r') as handle:
            parsed = json.load(handle)
        print( json.dumps(parsed, indent=4, sort_keys=True))
        cfg(dbx, cfga)
    elif var == 'set-rootdir':
        path = raw_input('enter path to local directory: ')
        if os.path.isdir(path):
            cfga['rootdir'] = path.strip()
            format_outp('path set', 'success')
            cfg(dbx, cfga)
        else:
            format_outp('please enter a valid dir!', 'fail')
            cfg(dbx, cfga, 'set-rootdir')
    elif var == 'set-token':
        token = raw_input('enter token here:')
        cfga['token'] = token.strip()
        format_outp('token set', 'success')
        cfg(dbx, cfga)
    elif var == 'token':
        if 'token' in cfga:
            format_outp(cfga['token'], 'hl')
        else:
            format_outp('Token not set yet. Use the following command to set it now:', 'fail')
            format_outp('set-token [token]')
        cfg(dbx, cfga)
    elif var.find('sync') == 0:
        fs = list_folder(dbx, '/')
        foldertoadd = var[5:].strip()
        if foldertoadd in cfga['folders']:
            format_outp('Folder already in list', 'fail')
        elif foldertoadd not in fs:
            format_outp('Folder not in remote', 'fail')
        else:
            cfga['folders'].append(str(foldertoadd))
            format_outp('folder added', 'success')
        cfg(dbx, cfga)
    elif str(var).find('unsync') == 0:
        foldertorm = var[7:].strip()
        if foldertorm in cfga['folders']:
            cfga['folders'].remove(str(foldertorm))
            format_outp('folder removed','success')
        else:
            format_outp('folder not in list','fail')
        cfg(dbx, cfga)
    elif var == 'list-synced':
        print('------------------')
        format_outp(' - '+"\n - ".join(cfga['folders']))
        cfg(dbx, cfga)
    elif var == 'list-remote':
        print('------------------')
        fs = list_folder(dbx, '/')
        for f in fs:
            fmt = 'hl'
            if f in cfga['folders']:
                fmt = 'success'
            format_outp('- '+ f, fmt)
        format_outp('** synced folders are highlighted green', 'blue')
        cfg(dbx, cfga)
    elif var == 'import-dir':
        f = raw_input('enter a directory path:')
        f = f.strip()
        if os.path.isdir(f):
            cfga['import-dir'] = f
            format_outp('import directory set', 'success')
        else:
            format_outp('directory not found', 'fail')
        cfg(dbx, cfga)
    elif var == 'export-dir':
        f = raw_input('enter a directory path:')
        f = f.strip()
        if os.path.isdir(f):
            cfga['export-dir'] = f
            format_outp('export directory set', 'success')
        else:
            format_outp('directory not found', 'fail')
        cfg(dbx, cfga)
    else:
        format_outp('unrecognised command', 'fail')
        cfg(dbx, cfga)

def format_outp(msg, case='hl'):
    fmt = '0';
    if case == 'hl':
        fmt = '93'
    elif case == 'blue':
        fmt = '96'
    elif case == 'success':
        fmt = '32;1'
    elif case == 'fail':
        fmt = '31;1'
    os.system('echo "\e['+fmt+'m'+str(msg)+' \e[0m\r"')


def dblog(msg):
    f= open(dir_path+"/pibox.log","a")
    pmsg = '[ %s ] : %s \r\n' % (str(datetime.datetime.now()), msg.encode('utf-8'))
    f.write(pmsg)
    f.close()

def scan_remote_folder(dbx, folder, flist):
    dblog('fetching remote folder: '+folder)
    listing = list_folder(dbx, folder)
    dblog('recieved: '+folder)
    for name,f in listing.items():
        dblog('scanning :' + name)
        if isinstance(f, dropbox.files.FileMetadata):
            dblog('is FILE: '+folder + '/' + name)
            if folder not in flist:
                flist[folder] = {}
            flist[folder][name] = {
                'size':listing[name].size,
                'upd':str(listing[name].client_modified)
            }
        elif isinstance(f, dropbox.files.FolderMetadata):
            dblog('is FOLDER: ' + folder + '/' + name)

            scan_remote_folder(dbx, folder+'/'+name, flist)


def list_folder(dbx, folder, subfolder=''):
    """List a folder.

    Return a dict mapping unicode filenames to
    FileMetadata|FolderMetadata entries.
    """
    path = '/%s/%s' % (folder, subfolder.replace(os.path.sep, '/'))
    while '//' in path:
        path = path.replace('//', '/')
    path = path.rstrip('/')
    try:
        with stopwatch('list_folder'):
            res = dbx.files_list_folder(path)
    except dropbox.exceptions.ApiError as err:
        print('Folder listing failed for', path, '-- assumed empty:', err)
        #dblog('ERR: ' + err)
        return {}
    else:
        rv = {}
        for entry in res.entries:
            rv[entry.name] = entry
        return rv

def fetch_if_not_in_local(dbx, flist, rootdir):
    for f, a in flist.items():
        localpath = rootdir+'/'+f
        dblog('checking if local instance of file exists: '+localpath)
        if os.path.isdir(localpath):
            dblog('Folder exists: '+ localpath)
        else:
            dblog('Folder not found, creating now:' +localpath)
            os.makedirs(localpath)
        for fname, vals in a.items():
            if not isinstance(fname, six.text_type):
                fname = fname.decode('utf-8')
            fpath = localpath+'/'+fname
            if os.path.isfile(fpath):
                dblog('File exists locally: ' + fpath)
                md_tupl = time.strptime(vals['upd'], '%Y-%m-%d %H:%M:%S')
                md = time.mktime(md_tupl)
                if md > int(os.path.getmtime(fpath)):
                    dblog(fpath+' is newer on the server, removing (will be refetched on next run)')
                    os.remove(fpath)
                elif vals['size'] != os.path.getsize(fpath):
                    dblog('File size mismatch, refetching: '+ fpath + ' :: '+str(vals['size']) + '/'+str(os.path.getsize(fpath)))
                    download_full(dbx, f, fname, rootdir, vals['upd'])
            else:
                dblog('File not found, fetching now: '+ fpath + ' :: '+vals['upd'])
                download_full(dbx, f, fname, rootdir, vals['upd'])

def upload_new(dbx, rootdir, folder, flist):
    for dn, dirs, files in os.walk(rootdir+'/'+folder):
        subfolder = dn[len(rootdir):].strip(os.path.sep)
        print('Descending into', subfolder, '...')
        #path = '%s/%s' % (folder, subfolder.replace(os.path.sep, '/'))
        # First do all the files.
        for name in files:
            fullname = os.path.join(dn, name)
            if not isinstance(name, six.text_type):
                name = name.decode('utf-8')
            nname = unicodedata.normalize('NFC', name)
            if name.startswith('.'):
                print('Skipping dot file:', name)
            elif name.startswith('@') or name.endswith('~'):
                print('Skipping temporary file:', name)
            elif name.endswith('.pyc') or name.endswith('.pyo'):
                print('Skipping generated file:', name)
            elif subfolder not in flist or nname not in flist[subfolder]:
                print('fullname',fullname)
                if os.path.isdir(rootdir+'/'+subfolder):
                    flist[subfolder] = {}
                print('==== nname:', nname)
                print(flist[subfolder])
                upload(dbx, fullname, subfolder, name)       

        # Then choose which subdirectories to traverse.
        keep = []
        for name in dirs:
            if name.startswith('.'):
                print('Skipping dot directory:', name)
            elif name.startswith('@') or name.endswith('~'):
                print('Skipping temporary directory:', name)
            elif name == '__pycache__':
                print('Skipping generated directory:', name)
            
            else:
                keep.append(name)
        dirs[:] = keep

def upload(dbx, fullname, subfolder, name, overwrite=False):
    """Upload a file.
    Return the request response, or None in case of error.
    """
    path = '/%s/%s' % (subfolder.replace(os.path.sep, '/'), name)
    while '//' in path:
        path = path.replace('//', '/')
    mode = (dropbox.files.WriteMode.overwrite
            if overwrite
            else dropbox.files.WriteMode.add)
    mtime = os.path.getmtime(fullname)
    with open(fullname, 'rb') as f:
        data = f.read()
    with stopwatch('upload %d bytes' % len(data)):
        try:
            res = dbx.files_upload(
                data, path, mode,
                client_modified=datetime.datetime(*time.gmtime(mtime)[:6]),
                mute=True)
        except dropbox.exceptions.ApiError as err:
            print('*** API error', err)
            return None
    print('uploaded as', res.name.encode('utf8'))
    return res


def download_full(dbx, folder, name, localfolder, modification_time, subfolder=''):
    """Download a file.
 
    Return the bytes of the file, or None if it doesn't exist.
    """
    dblog('downloading file: '+name)
    path = '/%s/%s/%s' % (folder, subfolder.replace(os.path.sep, '/'), name)
    localpath = '/%s/%s/%s' % (localfolder, folder.replace(os.path.sep, '/'), name)
    while '//' in localpath:
        localpath = localpath.replace('//', '/')
    while '//' in path:
        path = path.replace('//', '/')
    print('PATH',path)
    print('LOCAL PATH',localpath)
    success = True
    with stopwatch('download'):
        try:
            dbx.files_download_to_file(localpath, path)
        except dropbox.exceptions.ApiError as err:
            success = False
            print('*** API error', err)
            dblog('*** API error: '+' - '+path+' - '+str(err))
    if success:
        dblog('downloaded: ' + name)
        md_tupl = time.strptime(modification_time, '%Y-%m-%d %H:%M:%S')
        md = time.mktime(md_tupl)
        os.utime(localpath, (time.time(), md))


def piboxd():
    print("""
__/\\\\\\\\\\\\\\\\\\\\\\\\\\__________/\\\\\\\\\\\\\\\\\\\\\\\\______________________________________________        
 _\\/\\\\\\/////////\\\\\\_______\\/\\\\\\////////\\\\\\____________________________________________       
  _\\/\\\\\\_______\\/\\\\\\__/\\\\\\_\\/\\\\\\______\\//\\\\\\_______________________________/\\\\\\\\\\\\\\\\\\__      
   _\\/\\\\\\\\\\\\\\\\\\\\\\\\\\/__\\///__\\/\\\\\\_______\\/\\\\\\__/\\\\/\\\\\\\\\\\\\\______/\\\\\\\\\\_____/\\\\\\/////\\\\\\_     
    _\\/\\\\\\/////////_____/\\\\\\_\\/\\\\\\_______\\/\\\\\\_\\/\\\\\\/////\\\\\\___/\\\\\\///\\\\\\__\\/\\\\\\\\\\\\\\\\\\\\__    
     _\\/\\\\\\_____________\\/\\\\\\_\\/\\\\\\_______\\/\\\\\\_\\/\\\\\\___\\///___/\\\\\\__\\//\\\\\\_\\/\\\\\\//////___   
      _\\/\\\\\\_____________\\/\\\\\\_\\/\\\\\\_______/\\\\\\__\\/\\\\\\_________\\//\\\\\\__/\\\\\\__\\/\\\\\\_________  
       _\\/\\\\\\_____________\\/\\\\\\_\\/\\\\\\\\\\\\\\\\\\\\\\\\/___\\/\\\\\\__________\\///\\\\\\\\\\/___\\/\\\\\\_________ 
        _\\///______________\\///__\\////////////_____\\///_____________\\/////_____\\///__________
    	""")

@contextlib.contextmanager
def stopwatch(message):
    """Context manager to print how long a block of code took."""
    t0 = time.time()
    try:
        yield
    finally:
        t1 = time.time()
        print('Total elapsed time for %s: %.3f' % (message, t1 - t0))

if __name__ == '__main__':
    main()
