#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.constants import ConstantClass, ConstantString
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class TileEntityTopping(Topping):
    """Gets tile entity (block entity) types."""

    PROVIDES = [
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
    def act(aggregate, jar, verbose=False):
        te = aggregate.setdefault("tileentity", {})

        if "tileentity.superclass" not in aggregate["classes"]:
            if verbose:
                print "Missing tileentity.superclass"
            return

        superclass = aggregate["classes"]["tileentity.superclass"]
        cf = ClassFile(StringIO(jar.read(superclass + ".class")))
        method = cf.methods.find_one("<clinit>")

        tileentities = te.setdefault("tileentities", {})
        te_classes = te.setdefault("classes", {})
        tmp = {}
        for ins in method.code.disassemble():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantClass):
                    tmp["class"] = const.name.value
                elif isinstance(const, ConstantString):
                    tmp["name"] = const.string.value
            elif ins.mnemonic == "invokestatic":
                if "class" in tmp and "name" in tmp:
                    tmp["blocks"] = []
                    tileentities[tmp["name"]] = tmp
                    te_classes[tmp["class"]] = tmp["name"]
                    tmp = {}

        if "tileentity.blockentitytag" in aggregate["classes"]:
            # Block entity tag matches block names to tile entities.
            tag = aggregate["classes"]["tileentity.blockentitytag"] + ".class"
            tag_cf = ClassFile(StringIO(jar.read(tag)))
            method = tag_cf.methods.find_one("<clinit>")

            stack = []

            # There may be two fields, one for old/new name and one item/name.
            # Or there may just be item/name.
            num_maps = len(list(tag_cf.fields.find(type_="Ljava/util/Map;")))
            assert num_maps in (1, 2)

            num_getstatic = 0
            for ins in method.code.disassemble():
                if ins.mnemonic == "getstatic":
                    num_getstatic += 1
                    assert num_getstatic <= num_maps
                elif ins.mnemonic in ("ldc", "ldc_w") and num_getstatic != 0:
                    const = tag_cf.constants.get(ins.operands[0].value)
                    if isinstance(const, ConstantString):
                        stack.append(const.string.value)
                elif ins.mnemonic == "invokeinterface":
                    if len(stack) != 2:
                        if verbose:
                            print "Unexpected stack length for BETag:", stack
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
            print "No block entity tag info; skipping that"

        nbt_tag_type = "L" + aggregate["classes"]["nbtcompound"] + ";"
        if "nethandler.client" in aggregate["classes"]:
            updatepacket = None
            for packet in aggregate["packets"]["packet"].itervalues():
                if (packet["direction"] != "CLIENTBOUND" or
                        packet["state"] != "PLAY"):
                    continue

                packet_cf = ClassFile(StringIO(jar.read(packet["class"])))
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
                print "Failed to identify update tile entity packet"
                return

            te["update_packet"] = updatepacket
            nethandler = aggregate["classes"]["nethandler.client"] + ".class"
            nethandler_cf = ClassFile(StringIO(jar.read(nethandler)))

            updatepacket_name = updatepacket["class"].replace(".class", "")

            method = nethandler_cf.methods.find_one(
                    args="L" + updatepacket_name + ";")

            value = None
            for ins in method.code.disassemble():
                if ins.mnemonic.startswith("iconst_"):
                    value = ins.mnemonic[-1]
                elif ins.mnemonic == "bipush":
                    value = ins.operands[0].value
                elif ins.mnemonic == "instanceof":
                    if value is None:
                        # Ensure the command block callback is not counted
                        continue

                    const = nethandler_cf.constants.get(ins.operands[0].value)
                    te_name = te_classes[const.name.value]
                    tileentities[te_name]["network_id"] = value
                    value = None
