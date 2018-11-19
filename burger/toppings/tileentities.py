#!/usr/bin/env python
# -*- coding: utf8 -*-

import six

from .topping import Topping

from jawa.constants import ConstantClass, String
from burger.util import class_from_invokedynamic

class TileEntityTopping(Topping):
    """Gets tile entity (block entity) types."""

    PROVIDES = [
        "identify.tileentity.list",
        "tileentities.list",
        "tileentities.tags",
        "tileentities.networkids"
    ]

    DEPENDS = [
        "identify.tileentity.superclass",
        "identify.tileentity.blockentitytag",
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        te = aggregate.setdefault("tileentity", {})

        if "tileentity.superclass" not in aggregate["classes"]:
            if verbose:
                print("Missing tileentity.superclass")
            return

        superclass = aggregate["classes"]["tileentity.superclass"]
        cf = classloader[superclass]

        # First, figure out whether this is a version where the TE superclass
        # is also the TE list.
        if cf.constants.find_one(String, lambda c: c.string.value in ('daylight_detector', 'DLDetector')):
            # Yes, it is
            listclass = superclass
            has_separate_list =-False
        else:
            # It isn't, but we can figure it out by looking at the constructor's only parameter.
            method = cf.methods.find_one(name="<init>")
            assert len(method.args) == 1
            listclass = method.args[0].name
            cf = classloader[listclass]
            has_separate_list = True

        aggregate["classes"]["tileentity.list"] = listclass

        method = cf.methods.find_one(name="<clinit>")

        tileentities = te.setdefault("tileentities", {})
        te_classes = te.setdefault("classes", {})
        tmp = {}
        for ins in method.code.disassemble():
            if ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if isinstance(const, ConstantClass):
                    # Used before 1.13
                    tmp["class"] = const.name.value
                elif isinstance(const, String):
                    tmp["name"] = const.string.value
            elif ins == "invokedynamic":
                # Used after 1.13
                tmp["class"] = class_from_invokedynamic(ins, cf)
            elif ins == "invokestatic":
                if "class" in tmp and "name" in tmp:
                    tmp["blocks"] = []
                    tileentities[tmp["name"]] = tmp
                    te_classes[tmp["class"]] = tmp["name"]
                    tmp = {}

        if "tileentity.blockentitytag" in aggregate["classes"]:
            # Block entity tag matches block names to tile entities.
            tag = aggregate["classes"]["tileentity.blockentitytag"]
            tag_cf = classloader[tag]
            method = tag_cf.methods.find_one(name="<clinit>")

            stack = []

            # There may be two fields, one for old/new name and one item/name.
            # Or there may just be item/name.
            num_maps = len(list(tag_cf.fields.find(type_="Ljava/util/Map;")))
            assert num_maps in (1, 2)

            num_getstatic = 0
            for ins in method.code.disassemble():
                if ins == "getstatic":
                    num_getstatic += 1
                    assert num_getstatic <= num_maps
                elif ins in ("ldc", "ldc_w") and num_getstatic != 0:
                    const = ins.operands[0]
                    if isinstance(const, String):
                        stack.append(const.string.value)
                elif ins == "invokeinterface":
                    if len(stack) != 2:
                        if verbose:
                            print("Unexpected stack length for BETag:", stack)
                        stack = []
                        continue

                    entity_id = stack.pop()
                    block_id = stack.pop()
                    if entity_id.startswith("minecraft:"):
                        entity_id = entity_id[len("minecraft:"):]

                    if num_getstatic == num_maps:
                        # The last map is the block name to block entity map
                        if not entity_id in tileentities:
                            if verbose:
                                # This does currently happen in 1.9
                                print ("Trying to mark %s as a block with "
                                       "tile entity %s but that tile entity "
                                       "does not exist!"
                                       % (block_id, entity_id))
                        else:
                            tileentities[entity_id]["blocks"].append(block_id)
                    else:
                        # The other map has block name to _old_ block entity
                        # name.  But we don't want that (burger currently
                        # doesn't track the old block entity name).
                        pass
        elif verbose:
            print("No block entity tag info; skipping that")

        nbt_tag_type = "L" + aggregate["classes"]["nbtcompound"] + ";"
        if "nethandler.client" in aggregate["classes"]:
            updatepacket = None
            for packet in six.itervalues(aggregate["packets"]["packet"]):
                if (packet["direction"] != "CLIENTBOUND" or
                        packet["state"] != "PLAY"):
                    continue

                packet_cf = classloader[packet["class"][:-len(".class")]] # XXX should we be including the .class sufix in the packet class if we just trim it everywhere we use it?
                # Check if the packet has the expected fields in the class file
                # for the update tile entity packet
                if (len(packet_cf.fields) >= 3 and
                        # Tile entity type int, at least (maybe also position)
                        len(list(packet_cf.fields.find(type_="I"))) >= 1 and
                        # New NBT tag
                        len(list(packet_cf.fields.find(type_=nbt_tag_type)))):
                    # There are other fields, but they vary by version.
                    updatepacket = packet
                    break

            if not updatepacket:
                if verbose:
                    print("Failed to identify update tile entity packet")
                return

            te["update_packet"] = updatepacket
            nethandler = aggregate["classes"]["nethandler.client"]
            nethandler_cf = classloader[nethandler]

            updatepacket_name = updatepacket["class"].replace(".class", "")

            method = nethandler_cf.methods.find_one(
                    args="L" + updatepacket_name + ";")

            value = None
            for ins in method.code.disassemble():
                if ins in ("bipush", "sipush"):
                    value = ins.operands[0].value
                elif ins == "instanceof":
                    if value is None:
                        # Ensure the command block callback is not counted
                        continue

                    const = ins.operands[0]
                    te_name = te_classes[const.name.value]
                    tileentities[te_name]["network_id"] = value
                    value = None
