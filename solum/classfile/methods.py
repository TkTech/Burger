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
__all__ = ["MethodTable"]

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from collections import namedtuple

from .attributes import AttributeTable
from ..descriptor import method_descriptor
from ..bytecode import Disassembler

_Method = namedtuple("Method", (
    "flags",
    "name_index",
    "descriptor_index",
    "attributes",
    "name",
    "returns",
    "args"
))

class Method(_Method):
    @property
    def code(self):
        """Returns the Code attribute, if there is one."""
        return self.attributes.find_one(name="Code")

    @property
    def instructions(self):
        if not hasattr(self, "_dism"):
            self._dism = Disassembler(self.code.code)

        return self._dism

    @property
    def is_public(self):
        return bool(self.flags & 0x01)
        
    @property
    def is_private(self):
        return bool(self.flags & 0x02)
        
    @property
    def is_protected(self):
        return bool(self.flags & 0x04)
        
    @property
    def is_static(self):
        return bool(self.flags & 0x08)
        
    @property
    def is_final(self):
        return bool(self.flags & 0x10)
        
    @property
    def is_synchronized(self):
        return bool(self.flags & 0x20)
    
    @property
    def is_bridge(self):
        return bool(self.flags & 0x40)
        
    @property
    def is_varargs(self):
        return bool(self.flags & 0x80)
        
    @property
    def is_native(self):
        return bool(self.flags & 0x100)
        
    @property
    def is_abstract(self):
        return bool(self.flags & 0x400)
        
    @property
    def is_strict(self):
        return bool(self.flags & 0x800)
        
    @property
    def is_synthetic(self):
        return bool(self.flags & 0x1000)

class MethodTable(list):
    def __init__(self, read, constants):
        method_length = read(">H")[0]

        tmp = []
        while method_length:
            method_length -= 1

            flags, name_i, desc_i = read(">HHH")
            name = constants[name_i]["value"]
            desc = method_descriptor(constants[desc_i]["value"])

            tmp.append(Method(
                flags,
                name_i,
                desc_i,
                AttributeTable(read, constants),
                name,
                desc[1],
                desc[0]
            ))

        self.__store = tmp

    @property
    def storage(self):
        return self.__store

    def find(self, name=None, args=None, returns=None, f=None):
        ret = []
        for method in self.storage:
            if name and name != method.name:
                continue

            if args and args != method.args:
                continue

            if returns and returns != method.returns:
                continue

            if f and not f(method):
                continue

            ret.append(method)

        return ret


    def find_one(self, name=None, args=None, returns=None, f=None):
        for method in self.storage:
            if name and name != method.name:
                continue

            if args and args != method.args:
                continue

            if returns and returns != method.returns:
                continue

            if f and not f(method):
                continue

            return method

        return None
