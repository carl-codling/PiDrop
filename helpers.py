#!/usr/bin/python

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
