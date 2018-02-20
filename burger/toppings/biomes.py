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
import types

from jawa.util.descriptor import method_descriptor

from jawa.constants import *

class BiomeTopping(Topping):
    """Gets most biome types."""

    PROVIDES = [
        "biomes"
    ]

    DEPENDS = [
        "identify.biome.superclass",
        "identify.biome.list"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "biome.superclass" not in aggregate["classes"]:
            return
        if "biome.list" in aggregate["classes"]:
            BiomeTopping.process_19(aggregate, classloader, verbose)
        else:
            BiomeTopping.process_18(aggregate, classloader, verbose)

    @staticmethod
    def process_18(aggregate, classloader, verbose):
        """Processes biomes for Minecraft 1.8"""
        biomes_base = aggregate.setdefault("biomes", {})
        biomes = biomes_base.setdefault("biome", {})
        biome_fields = biomes_base.setdefault("biome_fields", {})

        superclass = aggregate["classes"]["biome.superclass"]
        cf = classloader.load(superclass + ".class")
        
        mutate_method_desc = None
        mutate_method_name = None
        void_methods = cf.methods.find(returns="L" + superclass + ";", args="", f=lambda m: m.access_flags.acc_protected and not m.access_flags.acc_static)
        for method in void_methods:
            for ins in method.code.disassemble():
                if ins.mnemonic == "sipush" and ins.operands[0].value == 128:
                    mutate_method_desc = method.descriptor.value
                    mutate_method_name = method.name.value

        make_mutated_method_desc = None
        make_mutated_method_name = None
        int_methods = cf.methods.find(returns="L" + superclass + ";", args="I", f=lambda m: m.access_flags.acc_protected and not m.access_flags.acc_static)
        for method in int_methods:
            for ins in method.code.disassemble():
                if ins.mnemonic == "new":
                    make_mutated_method_desc = method.descriptor.value
                    make_mutated_method_name = method.name.value

        method = cf.methods.find_one("<clinit>")
        heights_by_field = {}
        tmp = None
        stack = None

        def store_biome_if_valid(biome):
            """Stores the given biome if it is a valid, complete biome."""
            if biome is not None and "name" in biome and biome["name"] != " and ":
                biomes[biome["name"]] = biome
                if "field" in biome:
                    biome_fields[biome["field"]] = biome["name"]

        # OK, start running through the initializer for biomes.
        for ins in method.code.disassemble():
            if ins.mnemonic == "new":
                store_biome_if_valid(tmp)

                stack = []
                const = cf.constants.get(ins.operands[0].value)
                tmp = {
                    "rainfall": 0.5,
                    "height": [0.1, 0.2],
                    "temperature": 0.5,
                    "class": const.name.value
                }
            elif tmp is None:
                continue
            elif ins.mnemonic == "invokespecial":
                const = cf.constants.get(ins.operands[0].value)
                name = const.name_and_type.name.value
                if len(stack) == 2 and (type(stack[1]) == types.FloatType or type(stack[0]) == types.FloatType):
                    # Height constructor
                    tmp["height"] = [stack[0], stack[1]]
                    stack = []
                elif len(stack) >= 1 and type(stack[0]) == types.IntType: # 1, 2, 3-argument beginning with int = id
                    tmp["id"] = stack[0]
                    stack = []
                elif name != "<init>":
                    tmp["rainfall"] = 0
            elif ins.mnemonic == "invokevirtual":
                const = cf.constants.get(ins.operands[0].value)
                name = const.name_and_type.name.value
                desc = const.name_and_type.descriptor.value
                if name == mutate_method_name and desc == mutate_method_desc:
                    # New, separate biome
                    tmp = tmp.copy()
                    tmp["name"] += " M"
                    tmp["id"] += 128
                    if "field" in tmp:
                        del tmp["field"]
                    tmp["height"][0] += .1
                    tmp["height"][1] += .2
                    store_biome_if_valid(tmp)
                elif name == make_mutated_method_name and desc == make_mutated_method_desc:
                    # New, separate biome, but with a custom ID
                    tmp = tmp.copy()
                    tmp["name"] += " M"
                    tmp["id"] += stack.pop()
                    if "field" in tmp:
                        del tmp["field"]
                    tmp["height"][0] += .1
                    tmp["height"][1] += .2
                    store_biome_if_valid(tmp)
                elif len(stack) == 1:
                    stack.pop()
                elif len(stack) == 2:
                    tmp["rainfall"] = stack.pop()
                    tmp["temperature"] = stack.pop()
            elif ins.mnemonic == "putstatic":
                const = cf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                if "height" in tmp and not "name" in tmp:
                    # Actually creating a height
                    heights_by_field[field] = tmp["height"]
                else:
                    tmp["field"] = field
            elif ins.mnemonic == "getstatic":
                # Loading a height map or preparing to mutate a biome
                const = cf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                if field in heights_by_field:
                    # Heightmap
                    tmp["height"] = heights_by_field[field]
                else:
                    # Store the old one first
                    store_biome_if_valid(tmp)
                    if field in biome_fields:
                        tmp = biomes[biome_fields[field]]
            # numeric values & constants
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, String):
                    tmp["name"] = const.string.value
                if isinstance(const, (Integer, Float)):
                    stack.append(const.value)

            elif ins.opcode <= 8 and ins.opcode >= 2:  # iconst
                stack.append(ins.opcode - 3)
            elif ins.opcode >= 0xb and ins.opcode <= 0xd:  # fconst
                stack.append(ins.opcode - 0xb)
            elif ins.mnemonic == "bipush":
                stack.append(ins.operands[0].value)
            elif ins.mnemonic == "sipush":
                stack.append(ins.operands[0].value)

        store_biome_if_valid(tmp)

    @staticmethod
    def process_19(aggregate, classloader, verbose):
        """Processes biomes for Minecraft 1.9"""
        biomes_base = aggregate.setdefault("biomes", {})
        biomes = biomes_base.setdefault("biome", {})
        biome_fields = biomes_base.setdefault("biome_fields", {})

        superclass = aggregate["classes"]["biome.superclass"]
        cf = classloader.load(superclass + ".class")

        method = cf.methods.find_one(returns="V", args="", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)
        heights_by_field = {}
        first_new = True
        biome = None
        stack = []

        # OK, start running through the initializer for biomes.
        for ins in method.code.disassemble():
            if ins.mnemonic == "anewarray":
                # End of biome initialization; now creating the list of biomes
                # for the explore all biomes achievement but we don't need
                # that info.
                break

            if ins.mnemonic == "new":
                if first_new:
                    # There are two 'new's in biome initialization - the first
                    # one is for the biome generator itself and the second one
                    # is the biome properties.  There's some info that is only
                    # stored on the first new (well, actually, beforehand)
                    # that we want to save.
                    const = cf.constants.get(ins.operands[0].value)

                    text_id = stack.pop()
                    numeric_id = stack.pop()

                    biome = {
                        "id": numeric_id,
                        "text_id": text_id,
                        "rainfall": 0.5,
                        "height": [0.1, 0.2],
                        "temperature": 0.5,
                        "class": const.name.value
                    }
                    stack = []

                first_new = not(first_new)
            elif ins.mnemonic == "invokestatic":
                # Call to the static registration method
                # We already saved its parameters at the constructor, so we
                # only need to store the biome now.
                biomes[biome["text_id"]] = biome
            elif ins.mnemonic == "invokespecial":
                # Possibly the constructor for biome properties, which takes
                # the name as a string.
                if len(stack) > 0 and not "name" in biome:
                    biome["name"] = stack.pop()

                stack = []
            elif ins.mnemonic == "invokevirtual":
                const = cf.constants.get(ins.operands[0].value)
                name = const.name_and_type.name.value
                desc = method_descriptor(const.name_and_type.descriptor.value)

                if len(desc.args) == 1:
                    if desc.args[0].name == "float":
                        # Ugly portion - different methods with different names
                        # Hopefully the order doesn't change
                        if name == "a":
                            biome["temperature"] = stack.pop()
                        elif name == "b":
                            biome["rainfall"] = stack.pop()
                        elif name == "c":
                            biome["height"][0] = stack.pop()
                        elif name == "d":
                            biome["height"][1] = stack.pop()
                    elif desc.args[0].name == "java/lang/String":
                        # setBaseBiome
                        biome["mutated_from"] = stack.pop()
            # numeric values & constants
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, String):
                    stack.append(const.string.value)
                if isinstance(const, (Integer, Float)):
                    stack.append(const.value)

            elif ins.opcode <= 8 and ins.opcode >= 2:  # iconst
                stack.append(ins.opcode - 3)
            elif ins.opcode >= 0xb and ins.opcode <= 0xd:  # fconst
                stack.append(ins.opcode - 0xb)
            elif ins.mnemonic == "bipush":
                stack.append(ins.operands[0].value)
            elif ins.mnemonic == "sipush":
                stack.append(ins.operands[0].value)

        # Go through the block list and add the field info.
        list = aggregate["classes"]["biome.list"]
        lcf = classloader.load(list + ".class")
        
        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        biome_name = ""
        for ins in method.code.disassemble():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = lcf.constants.get(ins.operands[0].value)
                if isinstance(const, String):
                    biome_name = const.string.value
            elif ins.mnemonic == "putstatic":
                if biome_name is None or biome_name == "Accessed Biomes before Bootstrap!":
                    continue
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                biomes[biome_name]["field"] = field
                biome_fields[field] = biome_name