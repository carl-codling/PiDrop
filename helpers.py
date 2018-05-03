#!/usr/bin/python

import os

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
