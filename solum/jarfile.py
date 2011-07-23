#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2010-2011 Tyler Kennedy <tk@tkte.ch>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
__all__ = ["JarFile"]

from zipfile import ZipFile

try:
    import multiprocessing
    _MULTIPROCESSING = True
except ImportError:
    _MULTIPROCESSING = False

from .classfile import ClassFile


class JarFile(object):
    """
    Implements a loose container around ZipFile to assist with common
    JAR-related tasks, as well as to streamline asynchronous processing
    of class files.
    """
    def __init__(self, source):
        self._zp = ZipFile(source)
        self._classes = []
        self._other = []
        self._manifest = None

        # FIXME: Find a ZipInfo workaround for < 2.5.
        for zi in self.zp.namelist():
            if zi.endswith(".class"):
                self._classes.append(zi)
            else:
                self._other.append(zi)

        # Record the manifest file if it exists. Any valid JAR will
        # have this file, but if this is a JAR produced by a tool,
        # hand-built or not yet finished, it may not.
        try:
            manifest = self.zp.getinfo("META-INF/MANIFEST.MF")
            self._manifest = self.zp.read(manifest)
        except KeyError:
            self._manifest = None

    def __getitem__(self, index):
        return self.zp.read(index)

    def map(self, f, files=None, parallel=False, error=False):
        """
        For each file in `files`, call `f`, passing it a string
        containing the contents of the file. If `parallel` is True,
        try to use the multiprocessing module to call `f`.

        Note: If you use parallel=True, you must ensure your program
              accounts for the quirks of the multiprocessing module.

        Note: As a ZipFile object cannot be used across multiple
              processes, every file from `files` will be loaded into
              memory. Be wary of extremely large JAR's and memory usage.
        """
        # By default pick all .class files.
        if not files:
            files = self.classes

        if parallel and error and not _MULTIPROCESSING:
            raise RuntimeError("unable to load the multiprocessing module")
        if not _MULTIPROCESSING or not parallel:
            return self._map_single(f, files=files)
        else:
            return self._map_parallel(f, files=files)

    def _map_single(self, f, files):
        def next_buff():
            for fl in files:
                yield self.zp.read(fl)
        return map(f, next_buff())

    def _map_parallel(self, f, files):
        if not _MULTIPROCESSING:
            raise RuntimeError("unable to load the multiprocessing module")

        buffers = [self.zp.read(fl) for fl in files]
        chunksize = len(buffers) / multiprocessing.cpu_count()

        pool = multiprocessing.Pool()
        return pool.map(f, buffers, chunksize=chunksize)

    @property
    def classes(self):
        """
        Returns a list of ZipInfo objects for each file ending with
        .class in the archive.
        """
        return self._classes

    @property
    def other(self):
        """
        Returns a list of ZipInfo object for each file that does not
        end with .class in the archive.
        """
        return self._other

    @property
    def zp(self):
        """
        Returns the underlying ZipFile object.
        """
        return self._zp

    @property
    def manifest(self):
        """
        Returns the contents of the manifest file if it exist, else
        returns None.
        """
        return self._manifest

    def get_class(self, cf_name):
        """
        Returns a ClassFile instance for the file cf_name.
        If cf_name does not end in .class, it is added.
        Returns None if there is no such file.
        """
        if not cf_name.endswith(".class"):
            cf_name = "%s.class" % cf_name

        cf = ClassFile(self[cf_name], str_as_buffer=True)
        return cf
