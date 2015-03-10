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
__all__ = ["AttributeTable"]

try:
    from collections import namedtuple
except ImportError:
    from ..compat import namedtuple


class Attribute(object):
    """
    Generic Attribute.
    """
    def __init__(self, read, constants):
        length = read(">I")[0]
        self.data = read(">%ss" % length)[0]

CodeException = namedtuple("CodeException", [
    "start_pc",
    "end_pc",
    "handler_pc",
    "catch_type"
])


class CodeAttribute(object):
    """
    Implements the Code attribute (S4.8.3).
    """
    def __init__(self, read, constants):
        length = read(">I")[0]
        self.max_stack, self.max_locals, code_len = read(">HHI")
        self.code, exp_len = read(">%ssH" % code_len)

        self.exception_table = []
        while exp_len:
            exp_len -= 1
            self.exception_table.append(CodeException(*read(">HHHH")))

        self.attributes = AttributeTable(read, constants)

_attribute_map = {
    "Code": CodeAttribute,
}


class AttributeTable(object):
    def __init__(self, read, constants):
        self.__store = []

        attrib_count = read(">H")[0]

        while attrib_count:
            attrib_count -= 1

            name_i = read(">H")[0]
            name = constants[name_i]["value"]

            attrib = _attribute_map.get(name, Attribute)(read, constants)
            attrib.name = name
            self.storage.append(attrib)

    @property
    def storage(self):
        return self.__store

    def find(self, name=None, f=None):
        if not name:
            return self.storage

        ret = []
        for attribute in self.storage:
            if name and attribute.name != name:
                continue

            if f and not f(attribute):
                continue

            ret.append(attribute)

        return attribute

    def find_one(self, name=None, f=None):
        for attribute in self.storage:
            if name and name != attribute.name:
                continue

            if f and not f(attribute):
                continue

            return attribute

        return None
