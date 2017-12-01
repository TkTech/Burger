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
from jawa.util.descriptor import method_descriptor

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
        ordered_blocks = blocks.setdefault("ordered_blocks", [])
        tmp = []

        stack = []
        locals = {}
        for ins in method.code.disassemble():
            #print stack
            #print "INS",ins
            if ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value
                current_block = {
                    "class": class_name,
                    "calls": {}
                }

                stack.append(current_block)
            elif ins.mnemonic.startswith("iconst"):
                stack.append(int(ins.mnemonic[-1]))
            elif ins.mnemonic.startswith("fconst"):
                stack.append(float(ins.mnemonic[-1]))
            elif ins.mnemonic == "aconst_null":
                stack.append(None)
            elif ins.mnemonic.endswith("ipush"):
                stack.append(ins.operands[0].value)
            elif ins.mnemonic == "fdiv":
                den = stack.pop()
                num = stack.pop()
                stack.append({"numerator": num, "denominator": den})
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)

                if isinstance(const, ConstantClass):
                    stack.append("%s.class" % const.name.value)
                elif isinstance(const, ConstantString):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
                #print "ldc",stack
            elif ins.mnemonic == "getstatic":
                const = cf.constants.get(ins.operands[0].value)
                if const.class_.name.value == superclass:
                    # Probably getting the static AIR resource location
                    stack.append("air")
                else:
                    stack.append({"obj": None, "field": repr(const)})
            elif ins.mnemonic == "getfield":
                const = cf.constants.get(ins.operands[0].value)
                obj = stack.pop()
                stack.append({"obj": obj, "field": repr(const)})
            elif ins.mnemonic in ("invokevirtual", "invokespecial", "invokeinterface"):
                # A method invocation
                const = cf.constants.get(ins.operands[0].value)
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                desc = method_descriptor(method_desc)
                num_args = len(desc.args)

                if method_name == "hasNext":
                    # We've reached the end of block registration
                    # (and have started iterating over registry keys)
                    break

                args = []
                for i in range(num_args):
                    args.insert(0, stack.pop())
                obj = stack.pop()

                if "calls" in obj:
                    obj["calls"][method_name + method_desc] = args
                else:
                    #print obj
                    pass
                if desc.returns.name != "void":
                    if desc.returns.name == superclass:
                        stack.append(obj)
                    else:
                        stack.append({"obj": obj, "method": const, "args": args})
            elif ins.mnemonic == "invokestatic":
                # Call to the registration method
                const = cf.constants.get(ins.operands[0].value)
                desc = method_descriptor(const.name_and_type.descriptor.value)
                num_args = len(desc.args)

                if num_args == 3:
                    current_block = stack.pop()
                    current_block["text_id"] = stack.pop()
                    current_block["numeric_id"] = stack.pop()
                else:
                    assert num_args == 2
                    current_block = stack.pop()
                    current_block["text_id"] = stack.pop()

                tmp.append(current_block)
            elif ins.mnemonic.startswith("astore"):
                if ins.mnemonic == "astore":
                    index = ins.operands[0].value
                else:
                    index = int(ins.mnemonic[-1])
                locals[index] = stack.pop()
            elif ins.mnemonic.startswith("aload"):
                if ins.mnemonic == "aload":
                    index = ins.operands[0].value
                else:
                    index = int(ins.mnemonic[-1])
                stack.append(locals[index])
            elif ins.mnemonic == "dup":
                stack.append(stack[-1])
            elif ins.mnemonic == "checkcast":
                pass
            elif verbose:
                print "Unknown instruction %s: stack is %s" % (ins, stack)

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

            ordered_blocks.append(final["text_id"])
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
