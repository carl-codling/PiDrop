
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

===========================================================================

"""

from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import shutil
import six
import sys
import time
import unicodedata
import json
import urwid

if sys.version.startswith('2'):
    input = raw_input

import dropbox

from pidrop_ui import *
from helpers import *

parser = argparse.ArgumentParser(description='Download/sync/manage folders from Dropbox')
parser.add_argument('funct', nargs='?', default='main',
                    help='Which process should I run')

def main():
    global CONFIG
    global rootdir
    global path_list
    global flist

    path_list = {}

    args = parser.parse_args()

    CONFIG = Cfg()

    if not CONFIG.get('token'):
        return setup()

    if args.funct == 'ui':
        return ui_init()

    if args.funct == 'setup':
        return setup()

    rootdir = CONFIG.get('rootdir').rstrip('/')

    connect_dropbox()

    if args.funct == 'cfg':
        PiDropd()
        format_outp('Type "help" for a list of commands', 'blue')
        return cfg(dbx, CONFIG.get())

    # we store a list of files that are synced, along with display paths
    flist = {}

    open(CWD+"/pidrop.log", 'w').close()
    dblog('program started in '+CWD)

    for folder in CONFIG.get('folders'):
        # scan_remote_folder(dbx, folder, flist)
        # upload_new(dbx, rootdir, folder, flist)
        syncbox(folder)

    # store our list of syced paths for use in the UI
    SyncedFiles().set(flist)

    dblog('END')
    return

def setup():
    global dbx
    PiDropd()
    format_outp('[ CONFIG FILE NOT FOUND ] Please use these commands to create one', 'fail')
    CONFIG.set([], 'folders')
    token = input('Enter your Dropbox API token: ')
    if len(token.strip()):
        CONFIG.set(token.strip(), 'token')
        format_outp('token set', 'success')
        format_outp('Attempting to connect...', 'blue')
        dbx = connect_dropbox()
        format_outp('Connected', 'success')
    else:
        format_outp('please enter a Dropbox API token!', 'fail')
        setup()
    if not CONFIG.get('rootdir'):
        setup_dirs()

    f = open(CWD+'/flist.json', 'w')
    f.write('{}')
    f.close()
    return ui_init()

def setup_dirs():
    path = input('Enter the path to a local dir where you will store your files: ')
    path = path.strip()
    if os.path.isdir(path):
        fpi = path+os.sep+'pidrop'
        fin = path+os.sep+'pidrop_in'
        fout = path+os.sep+'pidrop_out'
        try:
            os.mkdir(fpi)
            os.mkdir(fin)
            os.mkdir(fout)
        except OSError as e:
            return print('OS error', e)
        CONFIG.set(fpi, 'rootdir')
        CONFIG.set(fin, 'import-dir')
        CONFIG.set(fout, 'export-dir')
        format_outp('path set', 'success')
    else:
        format_outp('please enter a valid dir!', 'fail')
        setup_dirs()

def cfg(dbx, cfga, var=None):
    if not var:
        var = input('command:')
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
        with open(CWD+'/cfg.json') as json_file:
            cfgb = json.load(json_file)
        if cfga != cfgb:
            conf = input('exit without saving? (y/n): ')
            if conf == 'y':
                return
            else:
                cfg(dbx, cfga)
        return
    elif var == 'save':
        with open(CWD+'/cfg.json', 'w') as outfile:
            json.dump(cfga, outfile)
        cfg(dbx, cfga)
    elif var == 'dump':
        with open(CWD+'/cfg.json', 'r') as handle:
            parsed = json.load(handle)
        print( json.dumps(parsed, indent=4, sort_keys=True))
        cfg(dbx, cfga)
    elif var == 'set-rootdir':
        path = input('enter path to local directory: ')
        if os.path.isdir(path):
            cfga['rootdir'] = path.strip()
            format_outp('path set', 'success')
            cfg(dbx, cfga)
        else:
            format_outp('please enter a valid dir!', 'fail')
            cfg(dbx, cfga, 'set-rootdir')
    elif var == 'set-token':
        token = input('enter token here:')
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
        f = input('enter a directory path:')
        f = f.strip()
        if os.path.isdir(f):
            cfga['import-dir'] = f
            format_outp('import directory set', 'success')
        else:
            format_outp('directory not found', 'fail')
        cfg(dbx, cfga)
    elif var == 'export-dir':
        f = input('enter a directory path:')
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

def dblog(msg):
    f= open(CWD+"/pidrop.log","a")
    pmsg = '[ %s ] : %s \r\n' % (str(datetime.datetime.now()), msg.encode('utf-8'))
    f.write(pmsg)
    f.close()
    print(msg)

def syncbox(folder):
    """
    Get all synced folder data from dropbox and
    run checks to see if it needs updating
    """
    listing = list_folder(folder)
    for name,f in listing.items():
        dblog('scanning :' + name)
        if isinstance(f, dropbox.files.FileMetadata):
            if not is_file_synced(listing[name]):
                dblog(name+': file not synced')
                sync_file(listing[name])

        elif isinstance(f, dropbox.files.FolderMetadata):
            if not is_dir_in_local(listing[name]):
                dblog(name+': dir not in local')
                sync_folder(listing[name])


        elif isinstance(f, dropbox.files.DeletedMetadata):
            dblog(name+': is in the DELETE list')
            sync_deleted(listing[name])
    sync_local(folder)

def is_file_synced(data):
    """
    Runs some comparisons on file data retrieved from Dropbox against local version.
    If comparison fails delete any conflicting data and return False.
    Otherwise return True
    """
    local_path = '/'.join([rootdir, data.path_lower.strip('/')])
    # Is this path currently occupied by a dir?
    if os.path.isdir(local_path):
        try:
            shutil.rmtree(local_path)
        except Exception as e:
            dblog('Could not remove directory '+str(e))
        return False
    # Does a local file already exist at this path
    elif os.path.isfile(local_path):
        md_tupl = time.strptime(str(data.client_modified), '%Y-%m-%d %H:%M:%S')
        md = time.mktime(md_tupl)
        # Compare the local and remote file modified times
        if md > int(os.path.getmtime(local_path)):
            dblog(local_path+' is newer on the server')
            try:
                os.remove(local_path)
            except Exception as e:
                dblog('Could not remove file '+str(e))
            return False
        # compare local and remote file sizes
        elif data.size != os.path.getsize(local_path):
            dblog(local_path+' file size doesn\'nt match server')
            try:
                os.remove(local_path)
            except Exception as e:
                dblog('Could not remove file '+str(e))
            return False
        else:
            dblog(local_path+' file is already synced')
            return True

    else:
        return False

def is_dir_in_local(data):
    """
    Runs some comparisons on directory data retrieved from Dropbox against local version.
    If comparison fails delete any conflicting data and return False.
    Otherwise return True
    """
    local_path = '/'.join([rootdir, data.path_lower.strip('/')])
    if os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except Exception as e:
            dblog('Could not remove file: '+str(e))
        return False
    if os.path.isdir(local_path):
        return True
    return False

def sync_deleted(data):
    """
    Deleted any paths that are marked as deleted in data recieved from Dropbox
    """
    local_path = '/'.join([rootdir, data.path_lower.strip('/')])
    dblog(local_path)
    if os.path.isdir(local_path):
        try:
            shutil.rmtree(local_path)
        except Exception as e:
            dblog('Could not remove directory: '+str(e))
            return
        dblog('REMOVED DIR: '+local_path)
    elif os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except Exception as e:
            dblog('Could not remove file: '+str(e))
            return
        dblog('REMOVED FILE: '+local_path)

def sync_folder(data):
    """
    Create a new directory and any parent dirs found at Dropbox
    """
    path = data.path_lower.strip('/')
    parts = path.split('/')
    full_path = rootdir
    i = 0
    # make sure all the parent dirs exist:
    while i < len(parts):
        full_path = '/'.join([full_path, parts[i]])
        if not os.path.isdir(full_path):
            try:
                os.mkdir(full_path)
            except Exception as e:
                dblog('Could not create directory: '+str(e))
                return None
        i+=1

def sync_file(data):
    """
    Create any parent dirs that don't exist locally before downloading a new file
    """
    path = data.path_lower.strip('/')
    parts = path.split('/')
    full_path = rootdir
    i = 0
    # make sure all the parent dirs exist:
    while i < len(parts)-1:
        full_path = '/'.join([full_path, parts[i]])
        if not os.path.isdir(full_path):
            try:
                os.mkdir(full_path)
            except Exception as e:
                dblog('Could not create directory: '+str(e))
                return None
        i+=1
    download_file(data)

def download_file(data):
    """
    Download a file from Dropbox
    """
    remaining_bwidth = get_remaining_daily_bandwidth()
    if remaining_bwidth != 'unlimited' and data.size > remaining_bwidth:
        dblog('SKIPPING DOWNLOAD - Downloading now would exceed the daily bandwidth limit')
        return None

    local_path = '/'.join([rootdir, data.path_lower.strip('/')])

    dblog('downloading file: '+data.path_lower)
    try:
        dbx.files_download_to_file(local_path, data.path_lower)
    except dropbox.exceptions.ApiError as err:
        dblog('*** API error: '+' - '+data.path_lower+' - '+str(err))
        return None
    register_bandwidth_usage(data.size)
    dblog('downloaded: ' + data.path_lower)
    md_tupl = time.strptime(str(data.client_modified), '%Y-%m-%d %H:%M:%S')
    md = time.mktime(md_tupl)
    try:
        os.utime(local_path, (time.time(), md))
    except Exception as e:
        dblog('Could not update file modification time: '+str(e))
        return None

def dbx_fetch_folder(folder, cursor=None):
    if cursor is not None:
        try:
            res = dbx.files_list_folder_continue(cursor)
        except dropbox.exceptions.ApiError as err:
            dblog('Continuing folder listing failed for'+ folder+ '-- assumed empty:'+ str(err))
            return {}
    else:
        try:
            res = dbx.files_list_folder(folder, recursive=True, include_deleted=True,  include_media_info=True)
        except dropbox.exceptions.ApiError as err:
            dblog('Folder listing failed for'+ folder+ '-- assumed empty:'+ str(err))
            return {}
    out = res.entries
    if res.has_more:
        out.extend(dbx_fetch_folder(folder, res.cursor))
    return out

def list_folder(folder):
    """
    fetch meta data contents of a Dropbox folder
    """
    path_list[folder] = []
    path = folder.strip('/')
    path = '/'+path
    # try:
    #     res = dbx.files_list_folder(path, recursive=True, include_deleted=True,  include_media_info=True)
    # except dropbox.exceptions.ApiError as err:
    #     dblog('Folder listing failed for'+ path+ '-- assumed empty:'+ str(err))
    #     return {}
    entries = dbx_fetch_folder(path)
    rv = {}
    for entry in entries:
        rv[entry.name] = entry
        p = rootdir.rstrip('/')+'/'+entry.path_lower.strip('/')
        path_list[folder].append(p)
        flist[p] = {'name':os.path.basename(entry.path_display)}
        if hasattr(entry, 'media_info') and entry.media_info != None:
            dblog('registering media info for '+entry.path_display)
            md = entry.media_info.get_metadata()
            flist[p]['media_info'] = {}
            if hasattr(md, 'time_taken') and md.time_taken != None:
                flist[p]['media_info']['Time taken: '] = str(md.time_taken)
            if hasattr(md, 'duration') and md.duration != None:
                flist[p]['media_info']['Duration: '] = str(md.duration)
            if hasattr(md, 'dimensions') and md.dimensions != None:
                flist[p]['media_info']['Dimensions: '] = str(md.dimensions.width) + 'x' + str(md.dimensions.height)
            if hasattr(md, 'location') and md.location != None:
                flist[p]['media_info']['Location: '] = str(md.location.latitude)+', '+str(md.location.longitude)
        if hasattr(entry, 'shared_folder_id') and entry.shared_folder_id != None:
            flist[p]['shared'] = entry.shared_folder_id

    return rv

def sync_local(folder):
    """
    Find any files that aren't on Dropbox and upload them
    Should only run directly after downloading files have finished syncing ie. syncbox()
    """
    if CONFIG.get('large_upload_size'):
        large_upload_size = CONFIG.get('large_upload_size')
    else:
        large_upload_size = 10
    for dn, dirs, files in os.walk(rootdir+'/'+folder):
        subfolder = dn[len(rootdir):].strip(os.path.sep)
        dblog('Descending into: '+ subfolder+ '...')
        # First do all the files.
        for name in files:
            fullname = os.path.join(dn, name)
            if not isinstance(name, six.text_type):
                name = name.decode('utf-8')
            nname = unicodedata.normalize('NFC', name)
            if name.startswith('.'):
                dblog('Skipping dot file: '+ name)
            elif name.startswith('@') or name.endswith('~'):
                dblog('Skipping temporary file: '+ name)
            elif name.endswith('.pyc') or name.endswith('.pyo'):
                dblog('Skipping generated file: '+ name)
            elif fullname not in path_list[folder]:
                dblog('uploading : '+fullname)
                size = os.path.getsize(fullname)
                if size < int(large_upload_size) * 1024 *1024:
                    upload(fullname)
                else:
                    upload_large(fullname)
            else:
                dblog('PATH EXISTS: '+fullname)
        # Then choose which subdirectories to traverse.
        keep = []
        for name in dirs:
            fullname = os.path.join(dn, name)
            if name.startswith('.'):
                dblog('Skipping dot directory: '+ name)
            elif name.startswith('@') or name.endswith('~'):
                dblog('Skipping temporary directory: '+ name)
            elif name == '__pycache__':
                dblog('Skipping generated directory: '+ name)
            elif fullname not in path_list[folder]:
                dblog('FOUND FOLDER NOT AT SERVER : '+fullname)
                create_remote_folder(fullname)
            else:
                keep.append(name)
        dirs[:] = keep

def create_remote_folder(path):
    remote_path = path[len(CONFIG.get('root_dir'))-1:]
    dblog(remote_path)
    try:
        res = dbx.files_create_folder_v2(
            remote_path,
            autorename=True)
    except dropbox.exceptions.ApiError as err:
        dblog('*** API error: '+ str(err))
        return None
    dblog('CREATED REMOTE FOLDER: '+remote_path)
    flist[path] = os.path.basename(path)

def upload(path, overwrite=False):
    """
    Upload a file to connected Dropbox acct.
    """
    file_size = os.path.getsize(path)
    remaining_bwidth = get_remaining_daily_bandwidth()
    if remaining_bwidth != 'unlimited' and file_size > remaining_bwidth:
        dblog('SKIPPING UPLOAD - Uploading now would exceed the daily bandwidth limit')
        return None

    mode = (dropbox.files.WriteMode.overwrite
            if overwrite
            else dropbox.files.WriteMode.add)
    mtime = os.path.getmtime(path)
    target = path[len(rootdir):]

    dblog('UPLOAD :: '+target)
    with open(path, 'rb') as f:
        data = f.read()
    try:
        res = dbx.files_upload(
            data, target, mode,
            client_modified=datetime.datetime(*time.gmtime(mtime)[:6]),
            mute=True)
    except dropbox.exceptions.ApiError as err:
        dblog('*** API error: '+ str(err))
        return None
    register_bandwidth_usage(file_size)
    fname = os.path.basename(path)
    fname_lower = fname.lower()
    new_path = os.path.dirname(path)+os.sep+fname_lower
    try:
        os.rename(path, new_path)
    except OSError as err:
        dblog('*** OS error: '+ str(err))
        return None
    flist[new_path] = {'name':fname}
    dblog('uploaded as '+ res.name.encode('utf8'))
    return res

def upload_large(path, overwrite=False):

    if CONFIG.get('chunk_size'):
        chunk = CONFIG.get('chunk_size')
    else:
        chunk = 10

    mode = (dropbox.files.WriteMode.overwrite
            if overwrite
            else dropbox.files.WriteMode.add)

    f = open(path)
    file_size = os.path.getsize(path)

    remaining_bwidth = get_remaining_daily_bandwidth()
    if remaining_bwidth != 'unlimited' and file_size > remaining_bwidth:
        dblog('SKIPPING LARGE UPLOAD - Uploading now would exceed the daily bandwidth limit')
        return None

    target = path[len(rootdir):]
    mtime = os.path.getmtime(path)
    client_modified = datetime.datetime(*time.gmtime(mtime)[:6])

    dblog('UPLOAD LARGE FILE :: '+readable_bytes(file_size)+' '+target)

    CHUNK_SIZE = int(chunk) * 1024 * 1024

    if file_size <= CHUNK_SIZE:

        print(dbx.files_upload(f, target))

    else:

        upload_session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
        cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id,
                                                   offset=f.tell())
        commit = dropbox.files.CommitInfo(path=target,
                                          mode=mode,
                                          client_modified=client_modified,
                                          mute=True)

        nchunks = 0
        while f.tell() < file_size:
            if ((file_size - f.tell()) <= CHUNK_SIZE):
                print(dbx.files_upload_session_finish(f.read(CHUNK_SIZE),
                                                                cursor,
                                                                commit))
            else:
                dbx.files_upload_session_append(f.read(CHUNK_SIZE),

                                                cursor.session_id,
                                                cursor.offset)
                nchunks += 1
                dblog('ADDING '+readable_bytes(CHUNK_SIZE)+' CHUNK :: '+readable_bytes(CHUNK_SIZE*nchunks))
                cursor.offset = f.tell()
            register_bandwidth_usage(CHUNK_SIZE)

    fname = os.path.basename(path)
    fname_lower = fname.lower()
    new_path = os.path.dirname(path)+os.sep+fname_lower
    try:
        os.rename(path, new_path)
    except OSError as err:
        dblog('*** OS error: '+ str(err))
        return None
    flist[new_path] = {'name':fname}

def register_bandwidth_usage(n):
    today = datetime.datetime.now()
    today = today.strftime("%Y-%m-%d")
    du = CONFIG.get('daily_usage')
    if not du or today != du['date']:
        dblog('Days don\'t match. Resetting daily usage count')
    else:
        n += int(du['usage'])
    CONFIG.set({
        'date':today,
        'usage':n
    }, 'daily_usage')

def get_remaining_daily_bandwidth():
    if not CONFIG.get('daily_limit'):
        return 'unlimited'
    dl = int(CONFIG.get('daily_limit')) * 1024 * 1024
    if not CONFIG.get('daily_usage'):
        return dl

    else:
        today = datetime.datetime.now()
        today = today.strftime("%Y-%m-%d")
        if today != CONFIG.get('daily_usage')['date']:
            CONFIG.set({
                'date':today,
                'usage':0
            }, 'daily_usage')
            return dl
        else:
            return dl - int(CONFIG.get('daily_usage')['usage'])

def connect_dropbox():
    global dbx
    if CONFIG.get('connection_tout'):
        tout = CONFIG.get('connection_tout')
    else:
        tout = 30
    dbx = dropbox.Dropbox(CONFIG.get('token'), timeout=int(tout))
    try:
        dbx.users_get_current_account()
    except:
        sys.exit("ERROR: Invalid access token; try re-generating an access token from the app console on the web.")
    return dbx

def PiDropd():
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
