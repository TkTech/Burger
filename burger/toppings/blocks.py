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
from jawa.util.descriptor import method_descriptor
from jawa.transforms.simple_swap import simple_swap

import six.moves

class BlocksTopping(Topping):
    """Gets most available block types."""

    PROVIDES = [
        "blocks"
    ]

    DEPENDS = [
        "identify.block.superclass",
        "identify.block.list",
        "language",
        "version.data",
        "version.is_flattened"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "data" in aggregate["version"] and aggregate["version"]["data"] >= 1461: # 18w02a
            BlocksTopping._process_1point13(aggregate, classloader, verbose)
        else:
            BlocksTopping._process_1point12(aggregate, classloader, verbose)

        # Shared logic: Go through the block list and add the field info.
        list = aggregate["classes"]["block.list"]
        lcf = classloader.load(list + ".class")

        blocks = aggregate["blocks"]
        block = blocks["block"]
        block_fields = blocks["block_fields"]

        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        blk_name = ""
        for ins in method.code.disassemble(transforms=[simple_swap]):
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = lcf.constants.get(ins.operands[0].value)
                if isinstance(const, String):
                    blk_name = const.string.value
            elif ins.mnemonic == "putstatic":
                if blk_name is None or blk_name == "Accessed Blocks before Bootstrap!":
                    continue
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                if blk_name in block:
                    block[blk_name]["field"] = field
                elif verbose:
                    print("Cannot find a block matching %s for field %s" % (blk_name, field))
                block_fields[field] = blk_name

    @staticmethod
    def _process_1point13(aggregate, classloader, verbose):
        # Handles versions after 1.13 (specifically >= 18w02a)
        superclass = aggregate["classes"]["block.superclass"]
        cf = classloader.load(superclass + ".class")

        if "block" in aggregate["language"]:
            language = aggregate["language"]["block"]
        else:
            language = None

        # Figure out what the builder class is
        ctor = cf.methods.find_one("<init>")
        builder_class = ctor.args[0].name

        builder_cf = classloader.load(builder_class + ".class")
        # Sets hardness and resistance
        hardness_setter = builder_cf.methods.find_one(args='FF')
        # There's also one that sets both to the same value
        hardness_setter_2 = None
        for method in builder_cf.methods.find(args='F'):
            for ins in method.code.disassemble(transforms=[simple_swap]):
                if ins.mnemonic == "invokevirtual":
                    const = builder_cf.constants.get(ins.operands[0].value)
                    if (const.name_and_type.name.value == hardness_setter.name.value and
                            const.name_and_type.descriptor.value == hardness_setter.descriptor.value):
                        hardness_setter_2 = method
                        break
        assert hardness_setter_2 != None
        # ... and one that sets them both to 0
        hardness_setter_3 = None
        for method in builder_cf.methods.find(args=''):
            for ins in method.code.disassemble(transforms=[simple_swap]):
                if ins.mnemonic == "invokevirtual":
                    const = builder_cf.constants.get(ins.operands[0].value)
                    if (const.name_and_type.name.value == hardness_setter_2.name.value and
                            const.name_and_type.descriptor.value == hardness_setter_2.descriptor.value):
                        hardness_setter_3 = method
                        break
        assert hardness_setter_3 != None

        blocks = aggregate.setdefault("blocks", {})
        block = blocks.setdefault("block", {})
        block_fields = blocks.setdefault("block_fields", {})
        ordered_blocks = blocks.setdefault("ordered_blocks", [])

        # Find the static block registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        stack = []
        locals = {}

        cur_id = 0
        for ins in method.code.disassemble(transforms=[simple_swap]):
            if ins.mnemonic.startswith("fconst"):
                stack.append(float(ins.mnemonic[-1]))
            elif ins.mnemonic in ("bipush", "sipush"):
                stack.append(ins.operands[0].value)
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)

                if isinstance(const, String):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
            elif ins.mnemonic == "aconst_null":
                stack.append(None)
            elif ins.mnemonic == "getstatic":
                const = cf.constants.get(ins.operands[0].value)
                if const.class_.name.value == superclass:
                    # Probably getting the static AIR resource location
                    stack.append("air")
                else:
                    stack.append(object())
            elif ins.mnemonic == "getfield":
                stack.pop()
                stack.append(object())
            elif ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value
                tmp = {"class": class_name}
                stack.append(tmp)
            elif ins.mnemonic in ("invokevirtual", "invokespecial", "invokeinterface"):
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
                for i in six.moves.range(num_args):
                    args.insert(0, stack.pop())
                obj = stack.pop()

                if method_name == hardness_setter.name.value and method_desc == hardness_setter.descriptor.value:
                    obj["hardness"] = args[0]
                    # resistance is args[1]
                elif method_name == hardness_setter_2.name.value and method_desc == hardness_setter_2.descriptor.value:
                    obj["hardness"] = args[0]
                    # resistance is args[0]
                elif method_name == hardness_setter_3.name.value and method_desc == hardness_setter_3.descriptor.value:
                    obj["hardness"] = 0.0
                    # resistance is 0.0
                elif method_name == "<init>":
                    # Call to the constructor for the block
                    # We can't hardcode index 0 because sand has an extra parameter, so use the last one
                    # There are also cases where it's an arg-less constructor; we don't want to do anything there.
                    if num_args > 0:
                        obj.update(args[-1])

                if desc.returns.name != "void":
                    if desc.returns.name == builder_class:
                        stack.append(obj)
                    else:
                        stack.append(object())
            elif ins.mnemonic == "invokestatic":
                const = cf.constants.get(ins.operands[0].value)
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                desc = method_descriptor(method_desc)
                num_args = len(desc.args)

                args = []
                for i in six.moves.range(num_args):
                    args.insert(0, stack.pop())

                if const.class_.name.value == superclass:
                    # Call to the static register method.
                    text_id = args[0]
                    current_block = args[1]
                    current_block["text_id"] = text_id
                    current_block["numeric_id"] = cur_id
                    cur_id += 1
                    lang_key = "minecraft.%s" % text_id
                    if language != None and lang_key in language:
                        current_block["display_name"] = language[lang_key]
                    block[text_id] = current_block
                    ordered_blocks.append(text_id)
                elif const.class_.name.value == builder_class:
                    if desc.args[0].name == superclass: # Copy constructor
                        copy = dict(args[0])
                        del copy["text_id"]
                        del copy["numeric_id"]
                        del copy["class"]
                        if "display_name" in copy:
                            del copy["display_name"]
                        stack.append(copy)
                    else:
                        stack.append({}) # Append current block
            elif ins.mnemonic == "astore":
                locals[ins.operands[0].value] = stack.pop()
            elif ins.mnemonic == "aload":
                stack.append(locals[ins.operands[0].value])
            elif ins.mnemonic == "dup":
                stack.append(stack[-1])
            else:
                if verbose:
                    print("Unhandled instruction %s" % str(ins))

    @staticmethod
    def _process_1point12(aggregate, classloader, verbose):
        # Handles versions prior to 1.13
        superclass = aggregate["classes"]["block.superclass"]
        cf = classloader.load(superclass + ".class")

        is_flattened = aggregate["version"]["is_flattened"]
        individual_textures = True #aggregate["version"]["protocol"] >= 52 # assume >1.5 http://wiki.vg/Protocol_History#1.5.x since don't read packets TODO

        if "tile" in aggregate["language"]:
            language = aggregate["language"]["tile"]
        elif "block" in aggregate["language"]:
            language = aggregate["language"]["block"]
        else:
            language = None

        # Find the static block registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        blocks = aggregate.setdefault("blocks", {})
        block = blocks.setdefault("block", {})
        block_fields = blocks.setdefault("block_fields", {})
        ordered_blocks = blocks.setdefault("ordered_blocks", [])
        tmp = []

        stack = []
        locals = {}
        for ins in method.code.disassemble(transforms=[simple_swap]):
            if ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value
                current_block = {
                    "class": class_name,
                    "calls": {}
                }

                stack.append(current_block)
            elif ins.mnemonic.startswith("fconst"):
                stack.append(float(ins.mnemonic[-1]))
            elif ins.mnemonic == "aconst_null":
                stack.append(None)
            elif ins.mnemonic in ("bipush", "sipush"):
                stack.append(ins.operands[0].value)
            elif ins.mnemonic == "fdiv":
                den = stack.pop()
                num = stack.pop()
                if isinstance(den, (float, int)) and isinstance(num, dict) and "scale" in num:
                    num["scale"] /= den
                    stack.append(num)
                else:
                    stack.append({"numerator": num, "denominator": den})
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)

                if isinstance(const, ConstantClass):
                    stack.append("%s.class" % const.name.value)
                elif isinstance(const, String):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
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
                if "text_id" in obj:
                    stack.append({
                        "block": obj["text_id"],
                        "field": const.name_and_type.name.value,
                        "scale": 1
                    })
                else:
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
                for i in six.moves.range(num_args):
                    args.insert(0, stack.pop())
                obj = stack.pop()

                if "calls" in obj:
                    obj["calls"][method_name + method_desc] = args

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
            elif ins.mnemonic == "astore":
                locals[ins.operands[0].value] = stack.pop()
            elif ins.mnemonic == "aload":
                stack.append(locals[ins.operands[0].value])
            elif ins.mnemonic == "dup":
                stack.append(stack[-1])
            elif ins.mnemonic == "checkcast":
                pass
            elif verbose:
                print("Unknown instruction %s: stack is %s" % (ins, stack))

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
            fld = None
            for ins in method.code.disassemble(transforms=[simple_swap]):
                if ins.mnemonic == "putfield":
                    const = cf.constants.get(ins.operands[0].value)
                    fld = const.name_and_type.name.value
                elif ins.mnemonic == "ifge":
                    const = cf.constants.get(method.descriptor.index)
                    hardness_setter = method.name.value + const.value
                    hardness_field = fld
                    break

        if is_flattened:
            # Current IDs are incremental, manually track them
            cur_id = 0

        for blk in tmp:
            if not "text_id" in blk:
                if verbose:
                    print("Dropping nameless block:", blk)
                continue

            final = {}

            if "numeric_id" in blk:
                assert not is_flattened
                final["numeric_id"] = blk["numeric_id"]
            else:
                assert is_flattened
                final["numeric_id"] = cur_id
                cur_id += 1

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
                        print("%s: Broken hardness value" % final["text_id"])
                    final["hardness"] = 0.00
                else:
                    hardness = blk["calls"][hardness_setter][0]
                    if isinstance(hardness, dict) and "field" in hardness:
                        # Repair field info
                        assert hardness["field"] == hardness_field
                        assert "block" in hardness
                        assert hardness["block"] in block
                        hardness = block[hardness["block"]]["hardness"] * hardness["scale"]
                    final["hardness"] = hardness

            ordered_blocks.append(final["text_id"])
            block[final["text_id"]] = final
