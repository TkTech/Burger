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
        alias = entities.setdefault("alias", {})
        tmp = {}

        mode = "starting"

        stack = []
        for ins in method.code.disassemble():
            if mode == "starting":
                # We don't care about the logger setup stuff at the beginning;
                # wait until an entity definition starts.
                if ins.mnemonic in ("ldc", "ldc_w"):
                    mode = "entities"
            # elif is not used here because we need to handle modes changing
            if mode != "starting":
                if ins.mnemonic in ("ldc", "ldc_w"):
                    const = cf.constants.get(ins.operands[0].value)
                    if isinstance(const, ConstantClass):
                        stack.append(const.name.value)
                    elif isinstance(const, ConstantString):
                        stack.append(const.string.value)
                    else:
                        stack.append(const.value)
                elif ins.mnemonic == "bipush":  # bipush
                    stack.append(ins.operands[0].value)
                elif ins.opcode <= 8 and ins.opcode >= 2: # iconst
                    stack.append(ins.opcode - 3)
                elif ins.mnemonic == "new":
                    # Entity aliases (for lack of a better term) start with 'new's.
                    # Switch modes (this operation will be processed there)
                    mode = "aliases"
                    const = cf.constants.get(ins.operands[0].value)
                    stack.append(const.name.value)
                elif ins.mnemonic == "invokestatic":  # invokestatic
                    if mode == "entities":
                        tmp["class"] = stack[0]
                        tmp["name"] = stack[1]
                        if (len(stack) >= 3):
                            tmp["id"] = stack[2]
                        if (len(stack) >= 5):
                            tmp["egg_primary"] = stack[3]
                            tmp["egg_secondary"] = stack[4]
                        if "id" in tmp:
                            entity[tmp["id"]] = tmp
                    elif mode == "aliases":
                        tmp["entity"] = stack[0]
                        tmp["name"] = stack[1]
                        if (len(stack) >= 5):
                            tmp["egg_primary"] = stack[2]
                            tmp["egg_secondary"] = stack[3]
                        tmp["class"] = stack[-1] # last item, made by new.
                        alias[tmp["name"]] = tmp

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
