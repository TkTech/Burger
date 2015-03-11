#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
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
from solum import ConstantType

from .topping import Topping


class ItemsTopping(Topping):
    """Provides some information on most available items."""
    PROVIDES = [
        "items"
    ]

    DEPENDS = [
        "identify.item.superclass",
        "language",
        "version.protocol"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["item.superclass"]
        individual_textures = True #aggregate["version"]["protocol"] >= 52 # assume >1.5 TODO
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

        name_setter = icon_setter = None

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
                if len(stack) == 2 and not individual_textures:
                    item["icon"] = {"x": stack[0], "y": stack[1]}
                elif len(stack) == 1:
                    if isinstance(stack[0], str):
                        const = cf.constants[instruction.operands[0][1]]
                        method_name = const["name_and_type"]["name"]["value"]
                        if not name_setter and stack[0] == "shovelIron":
                            name_setter = method_name
                        elif not icon_setter and stack[0] == "iron_shovel":
                            icon_setter = method_name
                        if method_name == name_setter:
                            item["name"] = stack[0]
                            language_key = "%s.name" % stack[0]
                            if language and language_key in language:
                                item["display_name"] = language[language_key]
                        elif method_name == icon_setter:
                            item["icon"] = stack[0]
                    else:
                        item["stack_size"] = stack[0]
                stack = []

            elif opcode == 0xb7:                    # invokespecial
                item["id"] = stack[0] + 256
                stack = []

            elif opcode in (0x12, 0x13):            # ldc
                    constant = cf.constants[instruction.operands[0][1]]
                    if constant["tag"] == ConstantType.STRING:
                        stack.append(constant["string"]["value"])

        items["count"] = len(item_list)
