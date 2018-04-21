
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
    input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox

parser = argparse.ArgumentParser(description='Download/sync/manage folders from Dropbox')
parser.add_argument('funct', nargs='?', default='main',
                    help='Which process should I run')

dir_path = os.path.dirname(os.path.realpath(__file__))

def main():
    global cfga
    global rootdir
    global path_list

    path_list = {}

    open(dir_path+"/pibox.log", 'w').close()
    dblog('program started in '+dir_path)
    args = parser.parse_args()

    if not os.path.isfile(dir_path+'/cfg.json'):
        piboxd()
        format_outp('[ CONFIG FILE NOT FOUND ] Please use these commands to create one', 'fail')
        return setup()

    with open(dir_path+'/cfg.json') as json_file:  
        cfga = json.load(json_file)

    rootdir = cfga['rootdir'].rstrip('/')
    
    connect_dbx()

    if args.funct == 'cfg':
        piboxd()
        format_outp('Type "help" for a list of commands', 'blue')
        return cfg(dbx, cfga)

    with open(dir_path+'/flist.json') as json_file:  
        flist = json.load(json_file)

    for folder in cfga['folders']:
        # scan_remote_folder(dbx, folder, flist)
        # upload_new(dbx, rootdir, folder, flist)
        syncbox(folder)

    dblog('END')
    return

def connect_dbx():
    global dbx
    dbx = dropbox.Dropbox(cfga['token'])
    try:
        dbx.users_get_current_account()
    except AuthError as err:
        sys.exit("ERROR: Invalid access token; try re-generating an access token from the app console on the web.")

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
    os.system('echo "\e[%sm%s \e[0m\r"' % (fmt, str(msg)))


def dblog(msg):
    f= open(dir_path+"/pibox.log","a")
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
            dblog(name+': is in the delete list')
            sync_deleted(listing[name])
    sync_local(folder)


def is_file_synced(data):
    """
    Runs some comparisons on file data retrieved from Dropbox against local version. 
    If comparison fails delete any conflicting data and return False.
    Otherwise return True 
    """
    local_path = '/'.join([rootdir, data.path_display.strip('/')])
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
    local_path = '/'.join([rootdir, data.path_display.strip('/')])
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
    local_path = '/'.join([rootdir, data.path_display.strip('/')])
    if os.path.isdir(local_path):
        try:
            shutil.rmtree(local_path)
        except Exception as e:
            dblog('Could not remove directory: '+str(e))
    elif os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except Exception as e:
            dblog('Could not remove file: '+str(e))
        

    
def sync_folder(data):
    """
    Create a new directory and any parent dirs found at Dropbox
    """
    path = data.path_display.strip('/')
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
    path = data.path_display.strip('/')
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

    local_path = '/'.join([rootdir, data.path_display.strip('/')])

    dblog('downloading file: '+data.path_display)
    try:
        dbx.files_download_to_file(local_path, data.path_display)
    except dropbox.exceptions.ApiError as err:
        dblog('*** API error: '+' - '+data.path_display+' - '+str(err))
        return None 
    dblog('downloaded: ' + data.path_display)
    md_tupl = time.strptime(str(data.client_modified), '%Y-%m-%d %H:%M:%S')
    md = time.mktime(md_tupl)
    try:
        os.utime(local_path, (time.time(), md))
    except Exception as e:
        dblog('Could not update file modification time: '+str(e))
        return None

def list_folder(folder):
    """
    fetch meta data contents of a Dropbox folder
    """
    path_list[folder] = []
    path = folder.strip('/')
    path = '/'+path
    try:
        res = dbx.files_list_folder(path, recursive=True, include_deleted=True)
    except dropbox.exceptions.ApiError as err:
        print('Folder listing failed for', path, '-- assumed empty:', err)
        return {}
    else:
        rv = {}
        for entry in res.entries:
            rv[entry.name] = entry
            p = rootdir.rstrip('/')+'/'+entry.path_display.strip('/')
            path_list[folder].append(p)
        return rv

def sync_local(folder):
    """
    Find any files that aren't on Dropbox and upload them
    Should only run directly after downloading files have finished syncing ie. syncbox()
    """
    flist = path_list[folder]
    print(flist)
    for dn, dirs, files in os.walk(rootdir+'/'+folder):
        subfolder = dn[len(rootdir):].strip(os.path.sep)
        dblog('Descending into'+ subfolder+ '...')
        # First do all the files.
        for name in files:
            fullname = os.path.join(dn, name)
            if not isinstance(name, six.text_type):
                name = name.decode('utf-8')
            nname = unicodedata.normalize('NFC', name)
            if name.startswith('.'):
                dblog('Skipping dot file:'+ name)
            elif name.startswith('@') or name.endswith('~'):
                dblog('Skipping temporary file:'+ name)
            elif name.endswith('.pyc') or name.endswith('.pyo'):
                dblog('Skipping generated file:'+ name)
            elif fullname not in flist:
                dblog('uploading : '+fullname)
                upload(fullname)       
            else: 
                print('PATH EXISTS',fullname)
        # Then choose which subdirectories to traverse.
        keep = []
        for name in dirs:
            if name.startswith('.'):
                dblog('Skipping dot directory:'+ name)
            elif name.startswith('@') or name.endswith('~'):
                dblog('Skipping temporary directory:'+ name)
            elif name == '__pycache__':
                dblog('Skipping generated directory:'+ name)
            
            else:
                keep.append(name)
        dirs[:] = keep

def upload(path, overwrite=False):
    """
    Upload a file to connected Dropbox acct.
    """
    mode = (dropbox.files.WriteMode.overwrite
            if overwrite
            else dropbox.files.WriteMode.add)
    mtime = os.path.getmtime(path)
    target = path[len(rootdir):]
    print('UPLOAD :: ',target)
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
    dblog('uploaded as '+ res.name.encode('utf8'))
    return res



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
