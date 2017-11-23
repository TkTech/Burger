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
        cf = ClassFile(StringIO(jar.read(superclass + ".class")))

        individual_textures = True #aggregate["version"]["protocol"] >= 52 # assume >1.5 http://wiki.vg/Protocol_History#1.5.x since don't read packets TODO

        if "tile" in aggregate["language"]:
            language = aggregate["language"]["tile"]
        elif "block" in aggregate["language"]:
            language = aggregate["language"]["block"]
        else:
            language = None

        # Find the static block registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)
        # Find the registerBlock method.
        registerMethod = cf.methods.find_one(args='ILjava/lang/String;Latr;', returns="V")

        blocks = aggregate.setdefault("blocks", {})
        block = blocks.setdefault("block", {})
        block_fields = blocks.setdefault("block_fields", {})
        tmp = []
        current_block = {
                    "class": None,
                    "calls": {}
                }

        stack = []
        for ins in method.code.disassemble():
            #print "INS",ins
            if ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value
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
                    if (isinstance(stack[0], int)):
                        assert stack[0] == 0
                        # Air uses a different registration method, with a
                        # ResourceLocation instead of a string; the location isn't
                        # on the stack in this case so we need to get it manually.
                        current_block["numeric_id"] = stack[0]
                        current_block["text_id"] = "air"
                    else:
                        # Newer minecraft version, no text IDs
                        current_block["text_id"] = stack[0]
                        current_block["name"] = current_block["text_id"]
                elif len(stack) == 0:
                    # Newer minecraft version, no text IDs.
                    # Air remains a hrorible hack.
                    current_block["text_id"] = "air"
                    current_block["name"] = current_block["text_id"]
                stack = []
            elif ins.mnemonic.startswith("iconst"):
                stack.append(int(ins.mnemonic[-1]))
            elif ins.mnemonic.startswith("fconst"):
                stack.append(float(ins.mnemonic[-1]))
            elif ins.mnemonic.endswith("ipush"):
                stack.append(ins.operands[0].value)
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)

                if isinstance(const, ConstantClass):
                    stack.append("%s.class" % const.name.value)
                elif isinstance(const, ConstantString):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
                #print "ldc",stack
            elif ins.mnemonic in ("invokevirtual", "invokespecial"):
                # A method invocation
                const = cf.constants.get(ins.operands[0].value)
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                current_block["calls"][method_name] = stack
                current_block["calls"][method_name + method_desc] = stack
                stack = []
            elif ins.mnemonic == "invokestatic":
                # Some blocks are constructed as a method variable rather
                # than directly in the registration method; thus the
                # paremters are set here.
                if len(stack) == 2:
                    current_block["numeric_id"] = stack[0]
                    current_block["text_id"] = stack[1]
                elif len(stack) == 1:
                    current_block["text_id"] = stack[0]
                stack = []
                tmp.append(current_block)

        # Now that we have all of the blocks, we need a few more things
        # to make sense of what it all means. So,
        #   1. Find the function that returns 'this' and accepts a string.
        #      This is the name or texture setting function.
        #   2. Find the function that returns 'this' and accepts a float.
        #      This is the function that sets the hardness.

        string_setter = cf.methods.find_one(returns="L" + superclass + ";",
                args="Ljava/lang/String;",
                f=lambda x: not x.access_flags.acc_static)

        if string_setter:
            name_setter = string_setter.name.value + cf.constants.get(string_setter.descriptor.index).value
        else:
            name_setter = None

        #NOTE: There are a bunch more of these now...
        hardness_setters = cf.methods.find(
            returns="L" + superclass + ";",
            args="F",
            f=lambda x: x.access_flags.acc_protected
        )

        for method in hardness_setters:
            for ins in method.code.disassemble():
                if ins.mnemonic == "ifge":
                    const = cf.constants.get(method.descriptor.index)
                    hardness_setter = method.name.value + const.value
                    break

        for blk in tmp:
            if not "text_id" in blk:
                print "Dropping nameless block:", blk
                continue

            final = {}

            if "numeric_id" in blk:
                final["numeric_id"] = blk["numeric_id"]
            if "text_id" in blk:
                final["text_id"] = blk["text_id"]

            final["class"] = blk["class"]

            if name_setter in blk["calls"]:
                final["name"] = blk["calls"][name_setter][0]

            if "name" in final:
                lang_key = "%s.name" % final["name"]
            else:
                # 17w43a (1.13) and above - no specific translation string, only the id
                lang_key = "minecraft.%s" % final["text_id"]
            if language and lang_key in language:
                final["display_name"] = language[lang_key]

            if hardness_setter not in blk["calls"]:
                final["hardness"] = 0.00
            else:
                stack = blk["calls"][hardness_setter]
                if len(stack) == 0:
                    if verbose:
                        print "%s: Broken hardness value" % final["text_id"]
                    final["hardness"] = 0.00
                else:
                    final["hardness"] = blk["calls"][hardness_setter][0]

            block[final["text_id"]] = final

        # Go through the block list and add the field info.
        list = aggregate["classes"]["block.list"]
        lcf = ClassFile(StringIO(jar.read(list + ".class")))

        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        blk_name = ""
        for ins in method.code.disassemble():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = lcf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantString):
                    blk_name = const.string.value
            elif ins.mnemonic == "putstatic":
                if blk_name is None or blk_name == "Accessed Blocks before Bootstrap!":
                    continue
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                if blk_name in block:
                    block[blk_name]["field"] = field
                elif verbose:
                    print "Cannot find a block matching %s for field %s" % (blk_name, field)
                block_fields[field] = blk_name

        blocks["info"] = {
            "count": len(block),
            "real_count": len(tmp)
        }
