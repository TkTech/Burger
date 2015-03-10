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
__all__ = ["ClassFile", "ClassError"]

import struct

from .constants import ConstantPool
from .fields import FieldTable
from .methods import MethodTable
from .attributes import AttributeTable


class ClassError(Exception):
    """
    Raised as a generic error whenever an error occurs with class
    parsing or if something (a value, field, keyname, etc...) violate
    the class file specification.
    """


class ClassFile(object):
    def __init__(self, source, str_as_buffer=False):
        """
        Load the ClassFile from the given `source`, which may be a file-like
        object, a path, or (if `str_as_buffer` is True) as the contents of
        a class.

        Note: If passing the value from JarFile.map_classes(), `str_as_buffer`
              should be True.
        """
        if str_as_buffer:
            # Assume the source is the binary contents of a ClassFile
            self._load_from_buffer(source)
        elif hasattr(source, "read"):
            # Assume we have a file-like object
            self._load_from_file(source)
        else:
            # Assume we have the path to a class file
            self._load_from_path(source)

    def _load_from_path(self, source):
        """Attempts to load the ClassFile from the file at `source`."""
        fin = open(source, "rb")
        self._load_from_file(fin)
        fin.close()

    def _load_from_file(self, source):
        """Attempts to load the ClassFile from the given file-like-object."""
        contents = source.read()
        self._load_from_buffer(contents)
        # Small bug means we never lose the reference to contents if
        # we don't nuke it ourselves.
        del contents

    def _load_from_buffer(self, source):
        """Attempts to load the ClassFile from the given buffer."""
        # Set the starting position in the buffer
        self.__pos = 0

        def read(format):
            length = struct.calcsize(format)
            tmp = struct.unpack_from(format, source, self.__pos)
            self.__pos += length
            return tmp

        magic_number = read(">I")[0]
        if magic_number != 0xCAFEBABE:
            # Every ClassFile since the dawn of time uses this one
            # magic number. If it isn't present, it's not a valid ClassFile.
            raise ClassError("invalid magic number (not a class?)")

        # Wonder what they were thinking...
        ver_min, ver_max = read(">HH")
        self._version = (ver_max, ver_min)

        self._constants = ConstantPool(read)

        self._flags, this, superclass = read(">HHH")

        self.this = self.constants[this]["name"]["value"]
        self.superclass = self.constants[superclass]["name"]["value"]

        # Interfaces are literally just a list of indexes into the
        # constant pool (if any)
        if_count = read(">H")[0]
        tmp = read(">%sH" % if_count)
        self._interfaces = [self.constants[x] for x in tmp]

        self._fields = FieldTable(read, self.constants)

        self._methods = MethodTable(read, self.constants)

        self._attributes = AttributeTable(read, self.constants)

    @property
    def version(self):
        """
        Returns a tuple in the form of (major_version, minor_version),
        representing the version of Java used to construct this ClassFile,
        or with which it is compatible.
        """
        return self._version

    @property
    def version_string(self):
        """
        Returns a human-readable string representing the version of Java used
        to construct this ClassFile. If version is given, it assumes it is
        a tuple in the style (major_version, minor_version) and uses that
        instead.
        """
        return {
            0x2D: "JDK 1.1",
            0x2E: "JDK 1.2",
            0x2F: "JDK 1.3",
            0x30: "JDK 1.4",
            0x31: "J2SE 5.0",
            0x32: "J2SE 6.0"
        }.get(self.version[0], "unknown")

    @property
    def constants(self):
        """Returns the ConstantPool instance."""
        return self._constants

    @property
    def interfaces(self):
        """Returns a list of inherited interfaces."""
        return self._interfaces

    @property
    def fields(self):
        """Returns a FieldTable instance."""
        return self._fields

    @property
    def methods(self):
        """Returns a MethodTable instance."""
        return self._methods

    @property
    def attributes(self):
        """Returns an AttributeTable instance."""
        return self._attributes

    @property
    def flags(self):
        """Returns the access flags for this class."""
        return self._flags

    @property
    def is_public(self):
        return bool(self.flags & 0x01)

    @property
    def is_final(self):
        return bool(self.flags & 0x10)

    @property
    def is_super(self):
        return bool(self.flags & 0x20)

    @property
    def is_interface(self):
        return bool(self.flags & 0x200)

    @property
    def is_abstract(self):
        return bool(self.flags & 0x400)

    @property
    def is_synthetic(self):
        return bool(self.flags & 0x1000)

    @property
    def is_annotation(self):
        return bool(self.flags & 0x2000)

    @property
    def is_enum(self):
        return bool(self.flags & 0x4000)
