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
__all__ = [
    "DescriptorError",
    "method_descriptor",
    "field_descriptor",
    "split_descriptor"
]

from collections import namedtuple

class DescriptorError(Exception):
    """
    Raised when any generic error occurs while parsing a field or method
    descriptor.
    """

def method_descriptor(descriptor):
    if descriptor[0] != "(":
        # A method desciptor must start with its arguments, which are
        # wrapped in brackets.
        raise DescriptorError("no opening bracket")
    
    end = descriptor.find(")")
    if end == -1:
        raise DescriptorError("no terminating bracket")
    
    # Parse the descriptor in two parts, the (optional) method arguments
    # and the mandatory return type.
    args = split_descriptor(descriptor[1:end])
    ret = split_descriptor(descriptor[end + 1:])
    
    # There must always be a return type, even for methods which return
    # nothing (void).
    if not ret:
        raise DescriptorError("no method return type")
    
    return args, ret[0]
    
def field_descriptor(descriptor):
    return split_descriptor(descriptor)[0]
        
def split_descriptor(descriptor):
    """
    Parses a descriptor in a manner compliant with section 4.4.1 of the 
    Java5 ClassFile Format Specification.
    """
    d = descriptor
    i = 0
    ret = []
    post = ""
    while i < len(d):
        # Each "[" denotes another array dimension
        if d[i] == "[":
            post += "[]"
        else:
            # Class types being with a 'L' and are terminated by a ';'.
            if d[i] == "L":
                end = d.find(";", i)
                if end == -1:
                    raise DescriptorError("no terminating semicolon")
                ret.append(d[i + 1:end].replace("/", "."))
                i = end - 1
            elif d[i] == "B":
                ret.append("byte")
            elif d[i] == "C":
                ret.append("char")
            elif d[i] == "D":
                ret.append("double")
            elif d[i] == "F":
                ret.append("float")
            elif d[i] == "I":
                ret.append("int")
            elif d[i] == "J":
                ret.append("long")
            elif d[i] == "S":
                ret.append("short")
            elif d[i] == "Z":
                ret.append("boolean")
            elif d[i] == "V":
                ret.append("void")
            
            if post:
                ret[-1] += post
                post = ""
            
        i += 1
    
    return tuple(ret)

