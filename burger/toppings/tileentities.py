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
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "tileentity.superclass" not in aggregate["classes"]:
            if verbose:
                print("Missing tileentity.superclass")
            return

        TileEntityTopping.identify_block_entities(aggregate, classloader, verbose)
        TileEntityTopping.identify_network_ids(aggregate, classloader, verbose)

    @staticmethod
    def identify_block_entities(aggregate, classloader, verbose):
        te = aggregate.setdefault("tileentity", {})

        superclass = aggregate["classes"]["tileentity.superclass"]
        cf = classloader[superclass]

        # First, figure out whether this is a version where the TE superclass
        # is also the TE list.
        if cf.constants.find_one(String, lambda c: c.string.value in ('daylight_detector', 'DLDetector')):
            # Yes, it is
            listclass = superclass
        else:
            # It isn't, but we can figure it out by looking at the constructor's only parameter.
            method = cf.methods.find_one(name="<init>")
            assert len(method.args) == 1
            listclass = method.args[0].name
            cf = classloader[listclass]

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

    @staticmethod
    def identify_network_ids(aggregate, classloader, verbose):
        te = aggregate.setdefault("tileentity", {})
        tileentities = te["tileentities"]
        te_classes = te["classes"]

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
                        len(list(packet_cf.fields.find(type_=nbt_tag_type))) >= 1):
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
