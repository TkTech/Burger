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
class ConstantTypes(object):
    CLASS = 7
    FIELD_REF = 9
    METHOD_REF = 10
    INTERFACE_METHOD_REF = 11
    REFERENCE = (9, 10, 11)
    STRING = 8
    INTEGER = 3
    INT = 3
    FLOAT = 4
    LONG = 5
    DOUBLE = 6
    NAME_AND_TYPE = 12
    UTF8 = 1

class ConstantPool(dict):
    def find(self, tag=None, f=None):
        ret = []
        for v in self.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            ret.append(v)

        return ret

    def find_one(self, tag=None, f=None):
        for v in self.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            return v
