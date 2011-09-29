#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2011 Simon Marti <simon@ceilingcat.ch>
Copyright (c) 2011 Tyler Kenedy <tk@tkte.ch>

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


class ItemsTopping(Topping):
    """Provides some information on most available items."""
    PROVIDES = [
        "items"
    ]

    DEPENDS = [
        "identify.item.superclass",
        "language"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["item.superclass"]
        cf = jar.open_class(superclass)

        # Find the static constructor
        method = cf.methods.find_one("<clinit>")
        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        def instructions():
            started = False
            find_new = False
            for instruction in method.instructions:
                if started:
                    yield instruction
                    continue
                elif instruction.opcode == 0xbd:    # anewarray
                    find_new = True
                elif find_new and instruction.opcode == 0xbb:
                    started = True
                    yield instruction

        for instruction in instructions():
            opcode = instruction.opcode
            if opcode == 0xbb:                      # new
                class_const = cf.constants[instruction.operands[0][1]]
                class_name = class_const["name"]["value"]
                item = {"class": class_name}
                stack = []

            elif opcode == 0xb3:                    # putstatic
                const = cf.constants[instruction.operands[0][1]]
                item["field"] = const["name_and_type"]["name"]["value"]
                item_list[item["id"]] = item

            elif opcode >= 0x02 and opcode <= 0x8:  # iconst
                stack.append(opcode - 3)

            elif opcode in (0x10, 0x11):            # bipush / sipush
                stack.append(instruction.operands[0][1])

            elif opcode == 0xb6:                    # invokevirtual
                if len(stack) == 2:
                    item["icon"] = {"x": stack[0], "y": stack[1]}
                elif len(stack) == 1:
                    if isinstance(stack[0], str):
                        if "name" in item:
                            continue
                        item["name"] = stack[0]
                        language_key = "%s.name" % stack[0]
                        if language != None and language_key in language:
                            item["display_name"] = language[language_key]
                    else:
                        item["stack_size"] = stack[0]
                stack = []

            elif opcode == 0xb7:                    # invokespecial
                item["id"] = stack[0] + 256
                stack = []

            elif opcode == 0x12:                    # ldc
                    constant = cf.constants[instruction.operands[0][1]]
                    if constant["tag"] == ConstantType.STRING:
                        stack.append(constant["string"]["value"])

        items["count"] = len(item_list)
