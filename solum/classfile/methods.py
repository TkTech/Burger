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
from ..descriptor import method_descriptor

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
    pass

class MethodTable(list):
    def __init__(self, src, constants):
        method_len = src(">H")

        while method_len > 0:
            flags, name_i, desc_i = src(">HHH")
            name = constants[name_i]["value"]
            desc = method_descriptor(constants[desc_i]["value"])

            self.append(Method(
                flags,
                name_i,
                desc_i,
                AttributeTable(src, constants),
                name,
                desc[1],
                desc[0]
            ))

            method_len -= 1

    def find(self, name=None, args=None, returns=None):
        tmp = []
        for method in self:
            if name and name != method.name:
                continue
            if args and args != method.args:
                continue
            if returns and returns != method.returns:
                continue
            
            tmp.append(method)

        return tmp

    def find_one(self, name=None, args=None, returns=None):
        for method in self:
            if name and name != method.name:
                continue
            if args and args != method.args:
                continue
            if returns and returns != method.returns:
                continue

            return method

        return None
