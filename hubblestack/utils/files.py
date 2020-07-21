# -*- coding: utf-8 -*-
'''
Functions for working with files
'''

# Import Python libs
import contextlib
import errno
import logging
import os
import shutil

import hubblestack.utils.stringutils
import hubblestack.utils.exceptions

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    # fcntl is not available on windows
    HAS_FCNTL = False

log = logging.getLogger(__name__)

def fopen(*args, **kwargs):
    '''
    Wrapper around open() built-in to set CLOEXEC on the fd.

    This flag specifies that the file descriptor should be closed when an exec
    function is invoked;

    When a file descriptor is allocated (as with open or dup), this bit is
    initially cleared on the new file descriptor, meaning that descriptor will
    survive into the new program after exec.

    NB! We still have small race condition between open and fcntl.
    '''
    try:
        # Don't permit stdin/stdout/stderr to be opened. The boolean False
        # and True are treated by Python 3's open() as file descriptors 0
        # and 1, respectively.
        if args[0] in (0, 1, 2):
            raise TypeError(
                '{0} is not a permitted file descriptor'.format(args[0])
            )
    except IndexError:
        pass
    binary = None
    if 'encoding' not in kwargs:
        # if text mode is used and the encoding
        # is not specified, set the encoding to 'utf-8'.
        binary = False
        if len(args) > 1:
            args = list(args)
            if 'b' in args[1]:
                binary = True
        if kwargs.get('mode', None):
            if 'b' in kwargs['mode']:
                binary = True
        if not binary:
            kwargs['encoding'] = __salt_system_encoding__
    elif (kwargs.pop('binary', False)):
        if len(args) > 1:
            args = list(args)
            if 'b' not in args[1]:
                args[1] = args[1].replace('t', 'b')
                if 'b' not in args[1]:
                    args[1] += 'b'
        elif kwargs.get('mode'):
            if 'b' not in kwargs['mode']:
                kwargs['mode'] = kwargs['mode'].replace('t', 'b')
                if 'b' not in kwargs['mode']:
                    kwargs['mode'] += 'b'
        else:
            # the default is to read
            kwargs['mode'] = 'rb'

    if not binary and not kwargs.get('newline', None):
        kwargs['newline'] = ''

    f_handle = open(*args, **kwargs)  # pylint: disable=resource-leakage

    if is_fcntl_available():
        # modify the file descriptor on systems with fcntl
        # unix and unix-like systems only
        try:
            FD_CLOEXEC = fcntl.FD_CLOEXEC   # pylint: disable=C0103
        except AttributeError:
            FD_CLOEXEC = 1                  # pylint: disable=C0103
        old_flags = fcntl.fcntl(f_handle.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(f_handle.fileno(), fcntl.F_SETFD, old_flags | FD_CLOEXEC)

    return f_handle

def is_fcntl_available():
    '''
    Simple function to check if the ``fcntl`` module is available or not.
    '''
    return HAS_FCNTL

@contextlib.contextmanager
def flopen(*args, **kwargs):
    '''
    Shortcut for fopen with lock and context manager.
    '''
    filename, args = args[0], args[1:]
    writing = 'wa'
    with fopen(filename, *args, **kwargs) as f_handle:
        try:
            if is_fcntl_available(check_sunos=True):
                lock_type = fcntl.LOCK_SH
                if args and any([write in args[0] for write in writing]):
                    lock_type = fcntl.LOCK_EX
                fcntl.flock(f_handle.fileno(), lock_type)
            yield f_handle
        finally:
            if is_fcntl_available(check_sunos=True):
                fcntl.flock(f_handle.fileno(), fcntl.LOCK_UN)

def is_binary(path):
    '''
    Detects if the file is a binary, returns bool. Returns True if the file is
    a bin, False if the file is not and None if the file is not available.
    '''
    if not os.path.isfile(path):
        return False
    try:
        with fopen(path, 'rb') as fp_:
            try:
                data = fp_.read(2048)
                data = data.decode(__salt_system_encoding__)
                return hubblestack.utils.stringutils.is_binary(data)
            except UnicodeDecodeError:
                return True
    except os.error:
        return False

def remove(path):
    '''
    Runs os.remove(path) and suppresses the OSError if the file doesn't exist
    '''
    try:
        os.remove(path)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise

def rename(src, dst):
    '''
    On Windows, os.rename() will fail with a WindowsError exception if a file
    exists at the destination path. This function checks for this error and if
    found, it deletes the destination path first.
    '''
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
        try:
            os.remove(dst)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise hubblestack.utils.exceptions.HubbleError(
                    'Error: Unable to remove {0}: {1}'.format(
                        dst,
                        exc.strerror
                    )
                )
        os.rename(src, dst)

def safe_rm(tgt):
    '''
    Safely remove a file
    '''
    try:
        os.remove(tgt)
    except (IOError, OSError):
        pass

def recursive_copy(source, dest):
    '''
    Recursively copy the source directory to the destination,
    leaving files with the source does not explicitly overwrite.

    (identical to cp -r on a unix machine)
    '''
    for root, _, files in hubblestack.utils.path.os_walk(source):
        path_from_source = root.replace(source, '').lstrip(os.sep)
        target_directory = os.path.join(dest, path_from_source)
        if not os.path.exists(target_directory):
            os.makedirs(target_directory)
        for name in files:
            file_path_from_source = os.path.join(source, path_from_source, name)
            target_path = os.path.join(target_directory, name)
            shutil.copyfile(file_path_from_source, target_path)

def safe_walk(top, topdown=True, onerror=None, followlinks=True, _seen=None):
    '''
    A clone of the python os.walk function with some checks for recursive
    symlinks. Unlike os.walk this follows symlinks by default.
    '''
    if _seen is None:
        _seen = set()

    # We may not have read permission for top, in which case we can't
    # get a list of the files the directory contains.  os.path.walk
    # always suppressed the exception then, rather than blow up for a
    # minor reason when (say) a thousand readable directories are still
    # left to visit.  That logic is copied here.
    try:
        # Note that listdir and error are globals in this module due
        # to earlier import-*.
        names = os.listdir(top)
    except os.error as err:
        if onerror is not None:
            onerror(err)
        return

    if followlinks:
        status = os.stat(top)
        # st_ino is always 0 on some filesystems (FAT, NTFS); ignore them
        if status.st_ino != 0:
            node = (status.st_dev, status.st_ino)
            if node in _seen:
                return
            _seen.add(node)

    dirs, nondirs = [], []
    for name in names:
        full_path = os.path.join(top, name)
        if os.path.isdir(full_path):
            dirs.append(name)
        else:
            nondirs.append(name)

    if topdown:
        yield top, dirs, nondirs
    for name in dirs:
        new_path = os.path.join(top, name)
        if followlinks or not os.path.islink(new_path):
            for x in safe_walk(new_path, topdown, onerror, followlinks, _seen):
                yield x
    if not topdown:
        yield top, dirs, nondirs
