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
        "entities.entity",
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        if "nethandler.client" not in aggregate["classes"]:
            return

        superclass = aggregate["classes"]["nethandler.client"]
        cf = ClassFile(StringIO(jar.read(superclass + ".class")))

        # Find the vehicle handler
        SPAWN_OBJECT_PACKET_ID = "PLAY_CLIENTBOUND_14";
        packet = aggregate["packets"]["packet"][SPAWN_OBJECT_PACKET_ID]["class"]
        method = cf.methods.find_one(args="L" + packet.replace(".class", "") + ";")
        entities = aggregate["entities"]
        objects = entities.setdefault("object", {})

        potential_id = 0
        current_id = 0

        for ins in method.code.disassemble():
            if ins.mnemonic == "if_icmpne":
                current_id = potential_id
            elif ins.mnemonic == "bipush":
                potential_id = ins.operands[0].value
            elif ins.opcode <= 8 and ins.opcode >= 2:
                potential_id = ins.opcode - 3
            elif ins.mnemonic == "new":
                const = cf.constants.get(ins.operands[0].value)
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
