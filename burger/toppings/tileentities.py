#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.constants import *
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

        if not "tileentity.superclass" in aggregate["classes"]:
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
                    tileentities[tmp["name"]] = tmp
                    te_classes[tmp["class"]] = tmp["name"]
                    tmp = {}

        if "tileentity.blockentitytag" in aggregate["classes"]:
            # Block entity tag matches block names to tile entities.
            tag_cf = ClassFile(StringIO(jar.read(aggregate["classes"]["tileentity.blockentitytag"] + ".class")))
            method = tag_cf.methods.find_one("<clinit>")

            stack = []
            for ins in method.code.disassemble():
                if ins.mnemonic in ("ldc", "ldc_w"):
                    const = tag_cf.constants.get(ins.operands[0].value)
                    if isinstance(const, ConstantString):
                        stack.append(const.string.value)
                elif ins.mnemonic == "invokeinterface":
                    if len(stack) == 2:
                        if not stack[1] in tileentities:
                            if verbose:
                                # This does currently happen in 1.9
                                print "Trying to mark %s as a block with tile entity %s but that tile entity does not exist!" % (stack[0], stack[1])
                        else:
                            tileentities[stack[1]].setdefault("blocks", []).append(stack[0])
                    stack = []
        elif verbose:
            print "No block entity tag info; skipping that"

        if "nethandler.client" in aggregate["classes"]:
            updatepacket = None
            for packet in aggregate["packets"]["packet"].itervalues():
                if packet["direction"] != "CLIENTBOUND" or packet["state"] != "PLAY":
                    continue

                packet_cf = ClassFile(StringIO(jar.read(packet["class"])))
                # Check if the packet has the expected fields in the class file for the update tile entity packet
                if (len(packet_cf.fields) >= 3 and
                        len(list(packet_cf.fields.find(type_ = "I"))) >= 1 and # Tile entity type int, at minimum
                        len(list(packet_cf.fields.find(type_ = "L" + aggregate["classes"]["nbtcompound"] + ";")))): # New NBT
                    # There are other fields, but they very by version.
                    updatepacket = packet
                    break

            if not updatepacket:
                print "Failed to identify update tile entity packet"
                return

            te["update_packet"] = updatepacket
            nethandler_cf = ClassFile(StringIO(jar.read(aggregate["classes"]["nethandler.client"] + ".class")))

            method = nethandler_cf.methods.find_one(args="L" + updatepacket["class"].replace(".class", "") + ";")

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
                    tileentities[te_classes[const.name.value]]["network_id"] = value
                    value = None
