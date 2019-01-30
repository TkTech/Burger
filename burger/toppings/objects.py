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

import six
from copy import copy

from .topping import Topping

from jawa.constants import *

class ObjectTopping(Topping):
    """Gets most vehicle/object types."""

    PROVIDES = [
        "entities.object"
    ]

    DEPENDS = [
        "identify.nethandler.client",
        "identify.entity.trackerentry",
        "version.data",
        "entities.entity",
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if aggregate["version"]["data"] >= 1930: # 19w05a+
            # Object IDs were removed in 19w05a, and entity IDs are now used instead.  Skip this topping entirely.
            return
        if "entity.trackerentry" not in aggregate["classes"] or "nethandler.client" not in aggregate["classes"]:
            return

        entities = aggregate["entities"]

        # Find the spawn object packet ID using EntityTrackerEntry.createSpawnPacket
        # (which handles other spawn packets too, but the first item in it is correct)
        entitytrackerentry = aggregate["classes"]["entity.trackerentry"]
        entitytrackerentry_cf = classloader[entitytrackerentry]

        createspawnpacket_method = entitytrackerentry_cf.methods.find_one(args="",
                f=lambda x: x.access_flags.acc_private and not x.access_flags.acc_static and not x.returns.name == "void")

        packet_class_name = None

        # Handle capitalization changes from 1.11
        item_entity_class = entities["entity"]["item"]["class"] if "item" in entities["entity"] else entities["entity"]["Item"]["class"]

        will_be_spawn_object_packet = False
        for ins in createspawnpacket_method.code.disassemble():
            if ins == "instanceof":
                # Check to make sure that it's a spawn packet for item entities
                const = ins.operands[0]
                if const.name == item_entity_class:
                    will_be_spawn_object_packet = True
            elif ins == "new" and will_be_spawn_object_packet:
                const = ins.operands[0]
                packet_class_name = const.name.value
                break

        if packet_class_name is None:
            if verbose:
                print("Failed to find spawn object packet")
            return

        # Get the packet info for the spawn object packet - not required but it is helpful information
        for key, packet in six.iteritems(aggregate["packets"]["packet"]):
            if packet_class_name in packet["class"]:
                # "in" is used because packet["class"] would have ".class" at the end
                entities["info"]["spawn_object_packet"] = key
                break

        objects = entities.setdefault("object", {})

        # Now find the spawn object packet handler and use it to figure out IDs
        nethandler = aggregate["classes"]["nethandler.client"]
        nethandler_cf = classloader[nethandler]
        method = nethandler_cf.methods.find_one(args="L" + packet_class_name + ";")

        potential_id = 0
        current_id = 0

        for ins in method.code.disassemble():
            if ins == "if_icmpne":
                current_id = potential_id
            elif ins in ("bipush", "sipush"):
                potential_id = ins.operands[0].value
            elif ins == "new":
                const = ins.operands[0]
                tmp = {"id": current_id, "class": const.name.value}
                objects[tmp["id"]] = tmp

        entities_by_class = {entity["class"]: entity for entity in six.itervalues(entities["entity"])}

        from .entities import EntityTopping
        EntityTopping.compute_sizes(classloader, aggregate, objects) # Needed because some objects aren't in the entity list

        for o in six.itervalues(objects):
            if o["class"] in entities_by_class:
                # If this object corresponds to a known entity, copy data from that
                entity = entities_by_class[o["class"]]
                if "id" in entity:
                    o["entity_id"] = entity["id"]
                if "name" in entity:
                    o["name"] = entity["name"]
                if "width" in entity:
                    o["width"] = entity["width"]
                if "height" in entity:
                    o["height"] = entity["height"]
                if "texture" in entity:
                    o["texture"] = entity["texture"]

        entities["info"]["object_count"] = len(objects)
