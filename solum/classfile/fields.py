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
__all__ = ["FieldTable"]

try:
    from collections import namedtuple
except ImportError:
    from ..compat import namedtuple

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
        return bool(self.flags & 0x1)

    @property
    def is_private(self):
        return bool(self.flags & 0x2)

    @property
    def is_protected(self):
        return bool(self.flags & 0x4)

    @property
    def is_static(self):
        return bool(self.flags & 0x8)

    @property
    def is_final(self):
        return bool(self.flags & 0x10)

    @property
    def is_volatile(self):
        return bool(self.flags & 0x40)

    @property
    def is_transient(self):
        return bool(self.flags & 0x80)

    @property
    def is_synthetic(self):
        return bool(self.flags & 0x1000)

    @property
    def is_enum(self):
        return bool(self.flags & 0x4000)

class FieldTable(object):
    def __init__(self, read, constants):
        field_length = read(">H")[0]

        tmp = {}
        while field_length:
            field_length -= 1

            flags, name_i, desc_i = read(">HHH")
            field_name = constants[name_i]["value"]

            tmp[field_name] = Field(
                flags,
                name_i,
                desc_i,
                AttributeTable(read, constants),
                field_name,
                field_descriptor(constants[desc_i]["value"])
            )

        self.__store = tmp

    @property
    def storage(self):
        return self.__store

    def __getitem__(self, index):
        return self.storage[index]

    def find(self, type_=None, f=None):
        storage = self.storage

        if not type_ and not f:
            return storage.values()
        elif type_ and f:
            tmp = (v for v in storage.itervalues() if v.type_ == type_)
            return filter(f, tmp)
        elif type_:
            return [v for v in storage.itervalues() if v.type_ == type_]
        else:
            return filter(f, storage.itervalues())

