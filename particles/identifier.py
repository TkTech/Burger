#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2011 Tyler Kenendy <tk@tkte.ch>

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
from solum import ClassFile, ConstantType

from .particle import Particle

def identify(buff):
    """
    The first pass across the JAR will identify all possible classes it
    can, maping them by the 'type' it implements.

    We have limited information available to us on this pass. We can only
    check for known signatures and predictable constants. In the next pass,
    we'll have the initial mapping from this pass available to us.
    """
    # str_as_buffer is required, else it'll treat the string buffer
    # as a file path.
    cf = ClassFile(buff, str_as_buffer=True)

    # First up, finding the "block superclass" (as we'll call it).
    # We'll look for one of the debugging messages.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "when adding" in c["string"]["value"]
    )

    if const:
        # We've found the block superclass, all done.
        return ("block.superclass", cf.this)

    # Next up, see if we've got the packet superclass in the same way.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "Duplicate packet" in c["string"]["value"]
    )

    if const:
        # We've found the packet superclass.
        return ("packet.superclass", cf.this)

    # The main recipe superclass.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "X#X" in c["string"]["value"]
    )

    if const:
        return ("recipe.superclass", cf.this)

    # First of 2 auxilary recipe classes. Appears to be items with
    # inventory, + sandstone.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: c["string"]["value"] == "# #"
    )

    if const:
        return ("recipe.inventory", cf.this)

    # Second auxilary recipe class. Appears to be coloured cloth?
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: c["string"]["value"] == "###"
    )

    if const:
        return ("recipe.cloth", cf.this)

    # Item superclass
    const = cf.constants.find_one(
       ConstantType.STRING,
       lambda c: "crafting results" in c["string"]["value"]
    )

    if const:
        return ("item.superclass", cf.this)    

class IdentifierParticle(Particle):
    PROVIDES = [
        "block.superclass",
        "packet.superclass",
        "recipe.superclass",
        "recipe.inventory",
        "recipe.cloth",
        "item.superclass"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar, verbose=False):
        mapped = jar.map(identify, parallel=True)
        mapped = filter(lambda f: f, mapped)
        classes = aggregate.setdefault("classes", {})
        for k,v in mapped:
            classes[k] = v

