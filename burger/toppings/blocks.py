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


class BlocksTopping(Topping):
    """Gets most available block types."""

    PROVIDES = [
        "blocks"
    ]

    DEPENDS = [
        "identify.block.superclass"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["block.superclass"]
        cf = jar.open_class(superclass)

        # Find the static constructor
        method = cf.methods.find_one("<clinit>")
        blocks = aggregate.setdefault("blocks", {})
        block = blocks.setdefault("block", {})
        tmp = []

        def skip_it():
            """
            Skip the misc. crap at the beginning of the constructor,
            and resume when we hit the first item.
            """
            watch_for_new = False
            found_new = False
            for ins in method.instructions:
                if found_new:
                    yield ins
                    continue

                if ins.name == "newarray":
                    # The next 'new' that comes along is where
                    # we want to break
                    watch_for_new = True
                elif watch_for_new and ins.name == "new":
                    found_new = True
                    yield ins
                    continue

        ditch = False
        for ins in skip_it():
            if ins.name == "new":
                # The beginning of a new block definition
                stack = []
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                class_name = const["name"]["value"]
                current_block = {
                    "class": class_name,
                    "calls": {}
                }
            elif ins.name.startswith("iconst"):
                stack.append(int(ins.name[-1]))
            elif ins.name.startswith("fconst"):
                stack.append(float(ins.name[-1]))
            elif ins.name.endswith("ipush"):
                stack.append(ins.operands[0][1])
            elif ins.name == "ldc":
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]

                if const["tag"] == ConstantType.CLASS:
                    stack.append("%s.class" % const["name"]["value"])
                elif const["tag"] == ConstantType.STRING:
                    stack.append(const["string"]["value"])
                else:
                    stack.append(const["value"])
            elif ins.name.startswith("invoke"):
                # A method invocation
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                method_name = const["name_and_type"]["name"]["value"]
                current_block["calls"][method_name] = stack
                stack = []
            elif ins.name == "putstatic":
                # Store the newly constructed object into a static
                # field. This means we have everything we're going to
                # get on this block.
                if ditch:
                    ditch = False
                    continue
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                field_name = const["name_and_type"]["name"]["value"]
                current_block["assigned_to_field"] = field_name
                tmp.append(current_block)
            elif ins.name == "aconst_null":
                # These are random incomplete blocks, we have no
                # choice but to ignore them for now.
                ditch = True

        # Now that we have all of the blocks, we need a few more things
        # to make sense of what it all means. So,
        #   1. Find the function that returns 'this' and accepts a string.
        #      This is the name setting function.
        #   2. Find the function that returns 'this' and accepts a float.
        #      This is the function that sets the hardness.
        #   3. The first parameter of a blocks <init> function will/should
        #      be the block's data ID.
        name_setter = cf.methods.find_one(
            returns=superclass,
            args=("java.lang.String",)
        ).name

        hardness_setters = cf.methods.find(
            returns=superclass,
            args=("float",),
            f=lambda x: x.is_protected
        )

        for method in hardness_setters:
            for ins in method.instructions:
                if ins.name == "ifge":
                    hardness_setter = method.name
                    break

        for blk in tmp:
            final = {}

            if name_setter in blk["calls"]:
                final["name"] = blk["calls"][name_setter][0]
            else:
                # The only time this currently occurs is with "webs"
                final["name"] = "web"

            init = blk["calls"]["<init>"]
            if not init:
                # The only time this currently occurs with cloth,
                # which is a special item with many ID's. Not much
                # we can do here.
                continue

            if hardness_setter not in blk["calls"]:
                final["hardness"] = 0.00
            else:
                final["hardness"] = blk["calls"][hardness_setter][0]

            final["id"] = init[0]
            final["field"] = blk["assigned_to_field"]
            final["class"] = blk["class"]

            block[final["id"]] = final

        blocks["info"] = {
            "count": len(block),
            "real_count": len(tmp)
        }
