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
try:
    from collections import namedtuple
except ImportError:
    from ..compat.namedtuple import namedtuple

from .attributes import AttributeTable
from ..descriptor import field_descriptor

_Field = namedtuple("Field", (
    "flags",
    "name_index",
    "descriptor_index",
    "attributes",
    "name",
    "type_"
))

class Field(_Field):
    @property
    def is_public(self):
        return True if self.flags & 0x0001 else False
        
    @property
    def is_private(self):
        return True if self.flags & 0x0002 else False
        
    @property
    def is_protected(self):
        return True if self.flags & 0x0004 else False
        
    @property
    def is_static(self):
        return True if self.flags & 0x0008 else False
        
    @property
    def is_final(self):
        return True if self.flags & 0x0010 else False
        
    @property
    def is_volatile(self):
        return True if self.flags & 0x0040 else False
        
    @property
    def is_transient(self):
        return True if self.flags & 0x0080 else False
        
    @property
    def is_synthetic(self):
        return True if self.flags & 0x1000 else False
        
    @property
    def is_enum(self):
        return True if self.flags & 0x4000 else False

class FieldTable(dict):
    def __init__(self, src, constants):
        field_len = src(">H")

        while field_len > 0:
            flags, name_i, desc_i = src(">HHH")
            name = constants[name_i]["value"]
            self[name] = Field(
                flags,
                name_i,
                desc_i,
                AttributeTable(src, constants),
                name,
                field_descriptor(constants[desc_i]["value"])
            )

            field_len -= 1

    def find(self, type_=None):
        """
        Returns all fields that match the given keywords. If no arguments are
        given, return all fields.

        Note: Due to implementation details, the order of fields is not kept.

        Note: Use ifind() for a more efficient version that returns a
              generator.
        """
        if type_:
            return [v for v in self.itervalues() if v.type_ == type_]

        return self.values()

    def ifind(self, type_=None):
        """
        Identical to find, with the exception that it returns a generator
        instead of a list.

        Note: This method cannot be used in concjunction with jar.map() when
              parallel=True, as generators cannot be pickled.
        """
        if not type_:
            return self.itervalues()

        return (v for v in self.itervalues() if v.type_ == type_)

    def find_one(self, name=None, type_=None):
        """
        Returns the first matching field for the given keywords. If no
        arguments are given, return the first found field.

        Note: Due to implementation details, the order of fields is not kept.
        """
        if not name and not type_:
            return self.itervalues().next() if self else None
        elif name and not type_:
            return self.get(name, None)
        elif type_ and not name:
            for v in self.itervalues():
                if v.type_ == type_:
                    return v
        elif type_ and name:
            if name not in self:
                return None

            if self[name].type_ == type_:
                return self[name]

        return None

