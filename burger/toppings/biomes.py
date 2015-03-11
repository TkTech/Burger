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
from solum import ClassFile, ConstantType

from .topping import Topping


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
        cf = jar.open_class(superclass)
        method = cf.methods.find_one(name="<clinit>")
        tmp = None
        stack = None
        for ins in method.instructions:
            if ins.opcode == 187:  # new
                if tmp is not None and tmp.has_key("name"):
                    biomes[tmp["name"]] = tmp
                stack = []
                tmp = {
                    "calls": {},
                    "rainfall": 0.5,
                    "height": [0.1, 0.3],
                    "temperature": 0.5,
                    "class": cf.constants[ins.operands[0][1]]["name"]["value"]
                }
            elif tmp is None:
                continue
            elif ins.opcode == 183:  # invokespecial
                const = cf.constants[ins.operands[0][1]]
                name = const["name_and_type"]["name"]["value"]
                if len(stack) == 1:
                    tmp["id"] = stack.pop()
                elif len(stack) >= 2:
                    tmp["calls"][name] = [stack.pop(), stack.pop()]
                elif name != "<init>":
                    tmp["rainfall"] = 0
            elif ins.opcode == 182:  # invokevirtual
                if len(stack) == 1 and "color" not in tmp:
                    tmp["color"] = stack.pop()

            # numeric values & constants
            elif ins.opcode == 18 or ins.opcode == 19: # ldc, ldc_w
                const = cf.constants[ins.operands[0][1]]
                if const["tag"] == ConstantType.STRING:
                    tmp["name"] = const["string"]["value"]
                if const["tag"] in (ConstantType.FLOAT,
                                    ConstantType.INTEGER):
                    stack.append(const["value"])

            elif ins.opcode <= 8 and ins.opcode >= 2:  # iconst
                stack.append(ins.opcode - 3)
            elif ins.opcode >= 0xb and ins.opcode <= 0xd:  # fconst
                stack.append(ins.opcode - 0xb)
            elif ins.opcode == 16:  # bipush
                stack.append(ins.operands[0][1])

        if tmp is not None and tmp.has_key("name"):
            biomes[tmp["name"]] = tmp

        weather, height = BiomeTopping.map_methods(biomes)

        for biome in biomes.itervalues():
            calls = biome.pop("calls")
            if height in calls:
                biome["height"] = calls[height]
                biome["height"].reverse()
            if weather in calls:
                biome["temperature"] = calls[weather][1]
                biome["rainfall"] = calls[weather][0]

    @staticmethod
    def map_methods(biomes):
        for biome in biomes.itervalues():
            for call in biome["calls"]:
                if biome["calls"][call][1] > 1 and len(biome["calls"]) > 1:
                    keys = biome["calls"].keys()
                    keys.remove(call)
                    return (call, keys[0])
        return (None, None)
