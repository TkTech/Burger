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

from .topping import Topping

from jawa.constants import ConstantString
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

def identify(class_file):
    """
    The first pass across the JAR will identify all possible classes it
    can, maping them by the 'type' it implements.

    We have limited information available to us on this pass. We can only
    check for known signatures and predictable constants. In the next pass,
    we'll have the initial mapping from this pass available to us.
    """
    # We can identify almost every class we need just by
    # looking for consistent strings.
    matches = (
        ('oreGold', 'block.superclass'),
        ('Accessed Blocks before Bootstrap!', 'block.list'),
        (' is already assigned to protocol ', 'packet.connectionstate'),
        ('The received encoded string buffer length is less than zero! Weird string!', 'packet.packetbuffer'),
        ('X#X', 'recipe.superclass'),
        ('leggingsIron', 'item.superclass'),
        ('Accessed Items before Bootstrap!', 'item.list'),
        ('Skipping Entity with id', 'entity.list'),
        ('disconnect.lost', 'nethandler.client'),
        ('Outdated server!', 'nethandler.server'),
        ('Ice Plains', 'biome.superclass'),
        ('Corrupt NBT tag', 'nbtcompound'),
        ('#%04d/%d%s', 'itemstack')
    )
    for c in class_file.constants.find(ConstantString):
        value = c.string.value
        for match, match_name in matches:
            if match not in value:
                continue

            return match_name, class_file.this.name.value
        if 'BaseComponent' in value:
            # We want the interface for chat components, but it has no
            # string constants, so we need to use the abstract class and then
            # get its first implemented interface.
            assert len(class_file.interfaces) == 1
            const = class_file.constants.get(class_file.interfaces[0])
            return 'chatcomponent', const.name.value


class IdentifyTopping(Topping):
    """Finds important superclasses needed by other toppings."""

    PROVIDES = [
        "identify.block.superclass",
        "identify.block.list",
        "identify.packet.connectionstate",
        "identify.packet.packetbuffer",
        "identify.recipe.superclass",
        "identify.recipe.inventory",
        "identify.recipe.cloth",
        "identify.item.superclass",
        "identify.item.list",
        "identify.entity.list",
        "identify.nethandler",
        "identify.biome.superclass",
        "identify.nbtcompound",
        "identify.itemstack",
        "identify.chatcomponent"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar, verbose=False):
        classes = aggregate.setdefault("classes", {})
        #TODO: Stop this silly manual conversion between solum and jawa once jawa conversion is done
        for path in jar.namelist():
            if not path.endswith(".class"):
                continue

            cf = ClassFile(StringIO(jar.read(path)))
            result = identify(cf)
            if result:
                classes[result[0]] = result[1]
                if len(classes) == len(IdentifyTopping.PROVIDES):
                    break
        print "identify classes:",classes
