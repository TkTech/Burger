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
from solum import ConstantType

from .topping import Topping


class BlocksTopping(Topping):
    """Gets most available block types."""

    PROVIDES = [
        "blocks"
    ]

    DEPENDS = [
        "identify.block.superclass",
        "identify.block.list",
        "language",
        "version.protocol"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["block.superclass"]
        cf = jar.open_class(superclass)
        
        individual_textures = True #aggregate["version"]["protocol"] >= 52 # assume >1.5 http://wiki.vg/Protocol_History#1.5.x since don't read packets TODO

        if "tile" in aggregate["language"]:
            language = aggregate["language"]["tile"]
        else:
            language = None

        # Find the static block registration method
        method = cf.methods.find_one(args=(), returns="void", flags=9) # public static void ...() {}
        # Find the registerBlock method.
        registerMethod = cf.methods.find_one(args=('int', 'java.lang.String', superclass), returns="void")
        
        blocks = aggregate.setdefault("blocks", {})
        block = blocks.setdefault("block", {})
        tmp = []

        stack = []
        for ins in method.instructions:
            #print "INS",ins
            if ins.name == "new":
                # The beginning of a new block definition
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                class_name = const["name"]["value"]
                current_block = {
                    "class": class_name,
                    "calls": {}
                }
                
                if len(stack) == 2:
                    # If the block is constructed in the registration method,
                    # like `registerBlock(1, "stone", (new BlockStone()))`, then
                    # the parameters are pushed onto the stack before the
                    # constructor is called.
                    current_block["numeric_id"] = stack[0]
                    current_block["text_id"] = stack[1]
                elif len(stack) == 1:
                    # Air uses a different registration method, with a
                    # ResourceLocation instead of a string; the location isn't
                    # on the stack in this case so we need to get it manually.
                    current_block["numeric_id"] = stack[0]
                    current_block["text_id"] = "air"
                stack = []
            elif ins.name.startswith("iconst"):
                stack.append(int(ins.name[-1]))
            elif ins.name.startswith("fconst"):
                stack.append(float(ins.name[-1]))
            elif ins.name.endswith("ipush"):
                stack.append(ins.operands[0][1])
            elif ins.name in ("ldc", "ldc_w"):
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]

                if const["tag"] == ConstantType.CLASS:
                    stack.append("%s.class" % const["name"]["value"])
                elif const["tag"] == ConstantType.STRING:
                    stack.append(const["string"]["value"])
                else:
                    stack.append(const["value"])
                #print "ldc",stack
            elif ins.name in ("invokevirtual", "invokespecial"):
                # A method invocation
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                method_name = const["name_and_type"]["name"]["value"]
                method_desc = const["name_and_type"]["descriptor"]["value"]
                current_block["calls"][method_name] = stack
                current_block["calls"][method_name + method_desc] = stack
                stack = []
            elif ins.name == "invokestatic":
                if len(stack) == 2:
                    # Some blocks are constructed as a method variable rather
                    # than directly in the registration method; thus the
                    # paremters are set here.
                    current_block["numeric_id"] = stack[0]
                    current_block["text_id"] = stack[1]
                stack = []
                tmp.append(current_block)

        # Now that we have all of the blocks, we need a few more things
        # to make sense of what it all means. So,
        #   1. Find the function that returns 'this' and accepts a string.
        #      This is the name or texture setting function.
        #   2. Find the function that returns 'this' and accepts a float.
        #      This is the function that sets the hardness.
        
        string_setters = cf.methods.find(returns=superclass,
                args=("java.lang.String",),
                f=lambda x: not x.is_static)
        assert len(string_setters) == 1

        name_setter = string_setters[0].name + cf.constants[string_setters[0].descriptor_index]["value"]

        #NOTE: There are a bunch more of these now...
        hardness_setters = cf.methods.find(
            returns=superclass,
            args=("float",),
            f=lambda x: x.is_protected
        )

        for method in hardness_setters:
            for ins in method.instructions:
                if ins.name == "ifge":
                    const = cf.constants[method.descriptor_index]
                    hardness_setter = method.name + const["value"]
                    break

        for blk in tmp:
            final = {}

            if name_setter in blk["calls"]:
                final["name"] = blk["calls"][name_setter][0]

                lang_key = "%s.name" % final["name"]
                if language and lang_key in language:
                    final["display_name"] = language[lang_key]

            if hardness_setter not in blk["calls"]:
                final["hardness"] = 0.00
            else:
                final["hardness"] = blk["calls"][hardness_setter][0]

            if "numeric_id" in blk:
                final["numeric_id"] = blk["numeric_id"]
            if "text_id" in blk:
                final["text_id"] = blk["text_id"]
            final["class"] = blk["class"]

            if "text_id" in final:
                block[final["text_id"]] = final

        # Go through the block list and add the field info.
        list = aggregate["classes"]["block.list"]
        lcf = jar.open_class(list)
        
        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        blk_name = ""
        for ins in method.instructions:
            if ins.name in ("ldc", "ldc_w"):
                const_i = ins.operands[0][1]
                const = lcf.constants[const_i]
                if const["tag"] == ConstantType.STRING:
                    blk_name = const["string"]["value"]
            elif ins.name == "putstatic":
                const_i = ins.operands[0][1]
                const = lcf.constants[const_i]
                field = const["name_and_type"]["name"]["value"]
                block[blk_name]["field"] = field
            
        blocks["info"] = {
            "count": len(block),
            "real_count": len(tmp)
        }
