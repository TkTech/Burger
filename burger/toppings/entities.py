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


class EntityTopping(Topping):
    """Gets most entity types."""

    PROVIDES = [
        "entities.entity"
    ]

    DEPENDS = [
        "identify.entity.list"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["entity.list"]
        cf = jar.open_class(superclass)

        # Find the static constructor
        method = cf.methods.find_one("<clinit>")
        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})
        tmp = {}

        def skip_it():
            """
            Skip the misc. crap at the beginning of the constructor,
            and resume when we hit the first item.
            """
            found_ldc = False
            for ins in method.instructions:
                if found_ldc:
                    yield ins
                elif ins.opcode in (18, 19):  # ldc
                    found_ldc = True
                    yield ins

        for ins in skip_it():
            if ins.opcode in (18, 19):  # ldc
                const = cf.constants[ins.operands[0][1]]
                if const["tag"] == ConstantType.CLASS:
                    tmp["class"] = const["name"]["value"]
                elif const["tag"] == ConstantType.STRING:
                    tmp["name"] = const["string"]["value"]
            elif ins.opcode == 16:  # bipush
                tmp["id"] = ins.operands[0][1]
            elif ins.opcode <= 8 and ins.opcode >= 2:
                tmp["id"] = ins.opcode - 3
            elif ins.opcode == 184:  # invokestatic
                if "id" in tmp:
                    entity[tmp["id"]] = tmp
                tmp = {}

        for e in entity.itervalues():
            size = EntityTopping.size(jar.open_class(e["class"]))
            if size:
                e["width"], e["height"], texture = size
                if texture:
                    e["texture"] = texture

        entities["info"] = {
            "entity_count": len(entity)
        }

    @staticmethod
    def size(cf):
        method = cf.methods.find_one("<init>")
        if method is None:
            return

        stage = 0
        tmp = []
        texture = None
        for ins in method.instructions:
            if ins.opcode == 42 and stage == 0:  # aload_0
                stage = 1
            elif ins.opcode == 18:
                const = cf.constants[ins.operands[0][1]]
                if const["tag"] == ConstantType.FLOAT and stage in (1, 2):
                # ldc
                    tmp.append(round(const["value"], 2))
                    stage += 1
                else:
                    stage = 0
                    tmp = []
                    if const["tag"] == ConstantType.STRING:
                        texture = const["string"]["value"]
            elif ins.opcode == 182 and stage == 3:  # invokevirtual
                return tmp + [texture]
                break
            else:
                stage = 0
                tmp = []
