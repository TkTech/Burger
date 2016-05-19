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

from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

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
        cf = ClassFile(StringIO(jar.read(superclass + ".class")))

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
            for ins in method.code.disassemble():
                if ins.mnemonic == "new":
                    # Aliases of some sort come after new; these aren't handled yet
                    return
                if found_ldc:
                    yield ins
                elif ins.mnemonic in ("ldc", "ldc_w"):
                    found_ldc = True
                    yield ins

        stack = []
        for ins in skip_it():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantClass):
                    tmp["class"] = const.name.value
                elif isinstance(const, ConstantString):
                    tmp["name"] = const.string.value
                else:
                    stack.append(const.value)
            elif ins.mnemonic == "bipush":  # bipush
                stack.append(ins.operands[0].value)
            elif ins.opcode <= 8 and ins.opcode >= 2:
                stack.append(ins.opcode - 3)
            elif ins.mnemonic == "invokestatic":  # invokestatic
                if (len(stack) >= 1):
                    tmp["id"] = stack[0]
                if (len(stack) >= 3):
                    tmp["egg_primary"] = stack[1]
                    tmp["egg_secondary"] = stack[2]
                if "id" in tmp:
                    entity[tmp["id"]] = tmp
                tmp = {}
                stack = []

        for e in entity.itervalues():
            cf = ClassFile(StringIO(jar.read(e["class"] + ".class")))
            size = EntityTopping.size(cf)
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
        for ins in method.code.disassemble():
            if ins.mnemonic == "aload_0" and stage == 0:
                stage = 1
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantFloat) and stage in (1, 2):
                    tmp.append(round(const.value, 2))
                    stage += 1
                else:
                    stage = 0
                    tmp = []
                    if isinstance(const, ConstantString):
                        texture = const.string.value
            elif ins.mnemonic == "invokevirtual" and stage == 3:
                return tmp + [texture]
                break
            else:
                stage = 0
                tmp = []
