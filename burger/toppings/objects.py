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

from copy import copy

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class ObjectTopping(Topping):
    """Gets most vehicle/object types."""

    PROVIDES = [
        "entities.object"
    ]

    DEPENDS = [
        "identify.nethandler.client",
        "identify.entity.trackerentry",
        "entities.entity",
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        if "entity.trackerentry" not in aggregate["classes"] or "nethandler.client" not in aggregate["classes"]:
            return

        entities = aggregate["entities"]

        # Find the spawn object packet ID using EntityTrackerEntry.createSpawnPacket
        # (which handles other spawn packets too, but the first item in it is correct)
        entitytrackerentry = aggregate["classes"]["entity.trackerentry"]
        entitytrackerentry_cf = ClassFile(StringIO(jar.read(entitytrackerentry + ".class")))

        createspawnpacket_method = entitytrackerentry_cf.methods.find_one(args="",
                f=lambda x: x.access_flags.acc_private and not x.access_flags.acc_static and not x.returns.name == "void")

        packet_class_name = None

        for ins in createspawnpacket_method.code.disassemble():
            if ins.mnemonic == "new":
                # The first new is for EntityItem, which uses spawn object.
                # This _might_ change in which case we'd get the wrong packet, but it hopefully won't.
                const = entitytrackerentry_cf.constants.get(ins.operands[0].value)
                packet_class_name = const.name.value
                break

        if packet_class_name is None:
            print "Failed to find spawn object packet"
            return

        # Get the packet info for the spawn object packet - not required but it is helpful information
        for key, packet in aggregate["packets"]["packet"].iteritems():
            if packet_class_name in packet["class"]:
                # "in" is used because packet["class"] would have ".class" at the end
                entities["info"]["spawn_object_packet"] = key
                break

        objects = entities.setdefault("object", {})

        # Now find the spawn object packet handler and use it to figure out IDs
        nethandler = aggregate["classes"]["nethandler.client"]
        nethandler_cf = ClassFile(StringIO(jar.read(nethandler + ".class")))
        method = nethandler_cf.methods.find_one(args="L" + packet_class_name + ";")

        potential_id = 0
        current_id = 0

        for ins in method.code.disassemble():
            if ins.mnemonic == "if_icmpne":
                current_id = potential_id
            elif ins.mnemonic in ("bipush", "sipush"):
                potential_id = ins.operands[0].value
            elif ins.opcode <= 8 and ins.opcode >= 2: # iconst
                potential_id = ins.opcode - 3
            elif ins.mnemonic == "new":
                const = nethandler_cf.constants.get(ins.operands[0].value)
                tmp = {"id": current_id, "class": const.name.value}
                objects[tmp["id"]] = tmp

        classes = {}
        for entity in entities["entity"].itervalues():
            classes[entity["class"]] = entity

        from .entities import EntityTopping
        for o in objects.itervalues():
            if o["class"] in classes:
                o["entity"] = copy(classes[o["class"]])
                del o["entity"]["class"]
            else:
                cf = ClassFile(StringIO(jar.read(o["class"] + ".class")))
                size = EntityTopping.size(cf)
                if size:
                    o["entity"] = {"width": size[0], "height": size[1]}
                    if size[2]:
                        o["entity"]["texture"] = size[2]

        entities["info"]["object_count"] = len(objects)
