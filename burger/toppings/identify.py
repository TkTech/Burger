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

from .topping import Topping


def identify(cf):
    """
    The first pass across the JAR will identify all possible classes it
    can, maping them by the 'type' it implements.

    We have limited information available to us on this pass. We can only
    check for known signatures and predictable constants. In the next pass,
    we'll have the initial mapping from this pass available to us.
    """
    # First up, finding the "block superclass" (as we'll call it).
    # We'll look for one of the debugging messages.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "Accessed Blocks" in c["string"]["value"]
    )

    if const:
        # We've found the block superclass, all done.
        return ("block.superclass", cf.this)

    # Next up, see if we've got the packet superclass in the same way.
    # TODO: update for Netty packets
    #const = cf.constants.find_one(
    #    ConstantType.STRING,
    #    lambda c: "Duplicate packet" in c["string"]["value"]
    #)
    #
    #if const:
    #    # We've found the packet superclass.
    #    return ("packet.superclass", cf.this)

    # The main recipe superclass.
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "X#X" in c["string"]["value"]
    )

    if const:
        return ("recipe.superclass", cf.this)

    # Item superclass
    const = cf.constants.find_one(
       ConstantType.STRING,
       lambda c: ("crafting results" in c["string"]["value"] or
                  "CONFLICT @ " in c["string"]["value"])
    )

    if const:
        return ("item.superclass", cf.this)

    # Entity list
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "Skipping Entity with id " in c["string"]["value"]
    )

    if const:
        return ("entity.list", cf.this)

    # Protocol version (Client)
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "disconnect.loginFailedInfo" in c["string"]["value"]
    )

    if const:
        return ("nethandler.client", cf.this)

    # Protocol version (Server)
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: "Outdated client!" in c["string"]["value"]
    )

    if const:
        return ("nethandler.server", cf.this)

    # Biome
    const = cf.constants.find_one(
        ConstantType.STRING,
        lambda c: ("Ice Plains") in c["string"]["value"]
    )

    if const:
        return ("biome.superclass", cf.this)


class IdentifyTopping(Topping):
    """Finds important superclasses needed by other toppings."""

    PROVIDES = [
        "identify.block.superclass",
        "identify.packet.superclass",
        "identify.recipe.superclass",
        "identify.recipe.inventory",
        "identify.recipe.cloth",
        "identify.item.superclass",
        "identify.entity.list",
        "identify.nethandler",
        "identify.biome.superclass"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar, verbose=False):
        classes = aggregate.setdefault("classes", {})
        for cf in jar.classes:
            result = identify(cf)
            if result:
                classes[result[0]] = result[1]
                if len(classes) == 8:
                    break
        print "identify classes:",classes
