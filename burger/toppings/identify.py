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
        (['Accessed Biomes before Bootstrap!'], 'biome.list'),  # 1.9 only
        (['Ice Plains'], 'biome.superclass'),
        (['Accessed Blocks before Bootstrap!'], 'block.list'),
        (['lightgem'], 'block.superclass'),
        (['Skipping Entity with id'], 'entity.list'),
        (['Fetching addPacket for removed entity'], 'entity.trackerentry'),
        (['Accessed Items before Bootstrap!'], 'item.list'),
        (['yellowDust'], 'item.superclass'),
        (['#%04d/%d%s'], 'itemstack'),
        (['disconnect.lost'], 'nethandler.client'),
        (['Outdated server!', 'multiplayer.disconnect.outdated_client'],
            'nethandler.server'),
        (['Corrupt NBT tag'], 'nbtcompound'),
        ([' is already assigned to protocol '], 'packet.connectionstate'),
        (
            ['The received encoded string buffer length is ' \
            'less than zero! Weird string!'],
            'packet.packetbuffer'
        ),
        (['Data value id is too big'], 'metadata'),
        (['X#X'], 'recipe.superclass'),
        (['Accessed Sounds before Bootstrap!'], 'sounds.list'),
        (['Skipping BlockEntity with id '], 'tileentity.superclass'),
        (
            ['Unable to resolve BlockEntity for ItemInstance:'],
            'tileentity.blockentitytag'
        )
    )
    for c in class_file.constants.find(ConstantString):
        value = c.string.value
        for match_list, match_name in matches:
            for match in match_list:
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
        if 'ambient.cave' in value:
            # We _may_ have found the SoundEvent class, but there are several
            # other classes with this string constant.  So we need to check
            # for registration methods.
            def is_public_static(m):
                return m.access_flags.acc_public and m.access_flags.acc_static

            def is_private_static(m):
                return m.access_flags.acc_public and m.access_flags.acc_static

            pub_args = {
                "args": "",
                "returns": "",
                "f": is_public_static
            }
            priv_args = {
                "args": "",
                "returns": "",
                "f": is_private_static
            }

            public_register_method = class_file.methods.find_one(**pub_args)
            private_register_method = class_file.methods.find_one(**priv_args)

            if public_register_method and private_register_method:
                return 'sounds.event', class_file.this.name.value


class IdentifyTopping(Topping):
    """Finds important superclasses needed by other toppings."""

    PROVIDES = [
        "identify.biome.list",
        "identify.biome.superclass",
        "identify.block.list",
        "identify.block.superclass",
        "identify.chatcomponent",
        "identify.entity.list",
        "identify.entity.trackerentry",
        "identify.item.list",
        "identify.item.superclass",
        "identify.itemstack",
        "identify.metadata",
        "identify.nbtcompound",
        "identify.nethandler.client",
        "identify.nethandler.server",
        "identify.packet.connectionstate",
        "identify.packet.packetbuffer",
        "identify.recipe.superclass",
        "identify.sounds.event",
        "identify.sounds.list",
        "identify.tileentity.superclass",
        "identify.tileentity.blockentitytag"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar, verbose=False):
        classes = aggregate.setdefault("classes", {})
        for path in jar.namelist():
            if not path.endswith(".class"):
                continue

            cf = ClassFile(StringIO(jar.read(path)))
            result = identify(cf)
            if result:
                if result[0] in classes:
                    raise Exception(
                            "Already registered %(value)s to %(old_class)s! "
                            "Can't overwrite it with %(new_class)s" % {
                                "value": result[0],
                                "old_class": classes[result[0]],
                                "new_class": result[1]
                            })
                classes[result[0]] = result[1]
                if len(classes) == len(IdentifyTopping.PROVIDES):
                    # If everything has been found, we don't need to keep
                    # searching, so stop early for performance
                    break
        if verbose:
            print("identify classes:", classes)
