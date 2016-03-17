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


from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class BiomeTopping(Topping):
    """Gets most biome types."""

    PROVIDES = [
        "biomes"
    ]

    DEPENDS = [
        "identify.biome.superclass"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        biomes = aggregate.setdefault("biomes", {})
        if "biome.superclass" not in aggregate["classes"]:
            return
        superclass = aggregate["classes"]["biome.superclass"]
        cf = ClassFile(StringIO(jar.read(superclass + ".class")))
        
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
            if biome is not None and biome.has_key("name") and biome["name"] != " and ":
                biomes[biome["name"]] = biome

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
                    "class": cf.constants.get(ins.operands[0].value).name.value
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
                elif len(stack) == 1 and "color" not in tmp:
                    tmp["color"] = stack.pop()
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
                    # Look for the biome with the given field.
                    for biome in biomes.itervalues():
                        if "field" in biome and biome["field"] == field:
                            tmp = biome
                            break
            # numeric values & constants
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantString):
                    tmp["name"] = const.string.value
                if isinstance(const, (ConstantInteger, ConstantFloat)):
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