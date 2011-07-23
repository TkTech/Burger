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

from .classfile import ClassFile


class JarFile(object):
    """
    Implements a loose container around ZipFile to assist with common
    JAR-related tasks.
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

    def open_class(self, cf_name):
        """
        Returns a ClassFile instance for the file cf_name.
        If cf_name does not end in .class, it is added.
        Returns None if there is no such file.
        """
        if not cf_name.endswith(".class"):
            cf_name = "%s.class" % cf_name

        cf = ClassFile(self[cf_name], str_as_buffer=True)
        return cf

    @property
    def classes(self):
        """
        Iterate over all the classes in the JAR, yielding a `Classfile`_ for
        each.
        """
        for c in self._classes:
            yield self.open_class(c)

    @property
    def all(self):
        """
        Iterate over all files in the JAR, yielding a file-like object for
        each.
        """
        for zi in self.zp.infolist():
            yield self.zp.open(name.filename)

    @property
    def class_list(self):
        """Returns a list of file names for classes in this JAR."""
        return list(self._classes)

    @property
    def count(self):
        """Returns the number of items contained in this JAR."""
        return len(self.zp.infolist())
