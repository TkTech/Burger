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
__all__ = ["ConstantPool", "ConstantType"]

class ConstantType(object):
    CLASS = 7
    FIELD_REF = 9
    METHOD_REF = 10
    INTERFACE_METHOD_REF = 11
    STRING = 8
    INTEGER = 3
    FLOAT = 4
    LONG = 5
    DOUBLE = 6
    NAME_AND_TYPE = 12
    UTF8 = 1

class ConstantPool(object):
    def __init__(self, read):
        self.__store = {}

        # The number of table entries, with the exception
        # of doubles and long, which are stored once but
        # counted twice.
        pool_count = read(">H")[0]

        x = 1
        tmp = {}
        while x < pool_count:
            # The type of the constant as mapped by ConstantType.
            tag = read(">B")[0]

            if tag == ConstantType.CLASS:
                tmp[x] = {"name_index": read(">H")[0]}
            elif tag in (9, 10, 11):
                class_index, name_and_type_index = read(">HH")
                tmp[x] = {
                    "class_index": class_index,
                    "name_and_type_index": name_and_type_index
                }
            elif tag == ConstantType.STRING:
                tmp[x] = {"string_index": read(">H")[0]}
            elif tag == ConstantType.INTEGER:
                tmp[x] = {"value": read(">i")[0]}
            elif tag == ConstantType.FLOAT:
                tmp[x] = {"value": read(">f")[0]}
            elif tag == ConstantType.LONG:
                tmp[x] = {"value": read(">q")[0]}
            elif tag == ConstantType.DOUBLE:
                tmp[x] = {"value": read(">d")[0]}
            elif tag == ConstantType.NAME_AND_TYPE:
                name_index, descriptor_index = read(">HH")
                tmp[x] = {
                    "name_index": name_index,
                    "descriptor_index": descriptor_index
                }
            elif tag == ConstantType.UTF8:
                length = read(">H")[0]
                tmp[x] = {"value": read(">%ss" % length)[0]}

            tmp[x]["tag"] = tag

            x += 2 if tag in (5,6) else 1

        # Resolve any indexes and store them
        for k,v in tmp.items():
            for k2,v2 in v.items():
                if k2.endswith("_index"):
                    tmp[k][k2[:-6]] = tmp[v2]

        self.__store = tmp;

    def __getitem__(self, index):
        return self.storage[index]

    def find(self, tag=None, f=None):
        """
        If given no options, returns a list of all constants.
        If either `tag` or `f` is given, it first picks all constants
        of type `tag`, then calls `f` with each constant, discarding those
        for which it returns False. If there are no results, returns an
        empty list.
        """
        if not tag and not f:
            return self.storage.items()

        ret = []
        for v in self.storage.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            ret.append(v)

        return ret

    def find_one(self, tag=None, f=None):
        """
        Identical to find(), with the exception that it returns the
        first matching item or None if there are no matches.
        """
        for v in self.storage.itervalues():
            if tag and v["tag"] != tag:
                continue

            if f and not f(v):
                continue

            return v

    @property
    def storage(self):
        """
        Returns the underlying storage object. You should never use this
        directly, instead using find() and find_one(), as it may change
        between releases.
        """
        return self.__store

