#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Implements interfaces for easily and efficiently processing
Java ARchive files (or JAR).
"""
import zipfile

try:
    import multiprocessing
    _MP = True
except ImportError:
    _MP = False

class JarFile(object):
    """
    The JarFile utility class provides a simple interface over JARs to
    ease loading, as well as serial and parallel processing of the contents.
    """
    def __init__(self, source):
        """
        Create a new JarFile instance from the given `source`. `source` can
        be of any type accepted by the ZipFile constructor.
        """
        self.zp = zipfile.ZipFile(source)

    def map(self, f, set=None, parallel=False):
        """
        Calls the function `f` for each file in `set`. If `parallel` is 
        True, it will be executed in parallel across all available cores
        if possible. Note that there is no guarantee of parallelism. If
        the multiprocessing module is not available, it will silently
        continue in a serial fashion.

        Note: You must account for the quirks of the multiprocessing module
              yourself, as documented on python.org. All values returned by
              `f` must be picklable.

        If `set` is None, it will default to all files in the JAR ending
        with .class. If `set` is not None, it must be a iterable object or
        list of paths to classes in the JAR.
        """
        if parallel and _MP:
            return self.map_parallel(f, set)
        else:
            return self.map_serial(f, set)
    
    def map_serial(self, f, set=None):
        if not set:
            nl = self.zp.namelist()
            set = (z for z in nl if z.endswith(".class"))
        
        final_set = map(lambda z: self.zp.read(z), set)
        
        return map(f, final_set)

    def map_parallel(self, f, set=None):
        if not _MP:
            raise RuntimeError()

        if not set:
            nl = self.zp.namelist()
            set = (z for z in nl if z.endswith(".class"))
        
        final_set = map(lambda z: self.zp.read(z), set)

        chunksize = len(final_set) / multiprocessing.cpu_count()
        
        pool = multiprocessing.Pool()
        return pool.map(f, final_set, chunksize=chunksize)

