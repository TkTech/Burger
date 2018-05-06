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
from .topping import Topping

from jawa.constants import *
from jawa.util.descriptor import method_descriptor

from burger.util import WalkerCallback, walk_method

import six

class ItemsTopping(Topping):
    """Provides some information on most available items."""
    PROVIDES = [
        "items"
    ]

    DEPENDS = [
        "identify.block.superclass",
        "identify.block.list",
        "identify.item.superclass",
        "identify.item.list",
        "language",
        "blocks",
        "version.protocol",
        "version.is_flattened"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "data" in aggregate["version"] and aggregate["version"]["data"] >= 1461: # 18w02a
            ItemsTopping._process_1point13(aggregate, classloader, verbose)
        else:
            ItemsTopping._process_1point12(aggregate, classloader, verbose)

        item_list = aggregate["items"]["item"]
        item_fields = aggregate["items"].setdefault("item_fields", {})

        # Go through the item list and add the field info.
        list = aggregate["classes"]["item.list"]
        lcf = classloader.load(list + ".class")

        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        item_name = ""
        for ins in method.code.disassemble():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = lcf.constants.get(ins.operands[0].value)
                if isinstance(const, String):
                    item_name = const.string.value
            elif ins.mnemonic == "putstatic":
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                if item_name in item_list:
                    item_list[item_name]["field"] = field
                elif verbose:
                    print("Cannot find an item matching %s for field %s" % (item_name, field))
                item_fields[field] = item_name

    @staticmethod
    def _process_1point13(aggregate, classloader, verbose):
        # Handles versions after 1.13 (specifically >= 18w02a)
        superclass = aggregate["classes"]["item.superclass"]
        blockclass = aggregate["classes"]["block.superclass"]
        blocklist = aggregate["classes"]["block.list"]

        cf = classloader.load(superclass + ".class")

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        # Figure out what the builder class is
        ctor = cf.methods.find_one(name="<init>")
        builder_class = ctor.args[0].name

        register_item_block_method = cf.methods.find_one(args='L' + blockclass + ';', returns="V")
        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.code.disassemble():
            if ins.mnemonic == "new":
                const = cf.constants.get(ins.operands[0].value)
                item_block_class = const.name.value
                break

        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})

        is_item_class_cache = {superclass: True}
        def is_item_class(name):
            if name in is_item_class_cache:
                return is_item_class_cache
            elif name == 'java/lang/Object':
                return True
            elif '/' in name:
                return False

            cf = classloader.load(name + '.class')
            result = is_item_class(cf.super_.name.value)
            is_item_class_cache[name] = result
            return result
        # Find the static block registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        class Walker(WalkerCallback):
            def __init__(self):
                self.cur_id = 0

            def on_new(self, ins, const):
                class_name = const.name.value
                return {"class": class_name}

            def on_invoke(self, ins, const, obj, args):
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                desc = method_descriptor(method_desc)

                if ins.mnemonic == "invokestatic":
                    if const.class_.name.value == superclass:
                        current_item = {}

                        text_id = None
                        idx = 0
                        for arg in desc.args:
                            if arg.name == blockclass:
                                block = args[idx]
                                text_id = block["text_id"]
                                if "name" in block:
                                    current_item["name"] = block["name"]
                                if "display_name" in block:
                                    current_item["display_name"] = block["display_name"]
                            elif arg.name == superclass:
                                current_item.update(args[idx])
                            elif arg.name == item_block_class:
                                current_item.update(args[idx])
                                text_id = current_item["text_id"]
                            elif arg.name == "java/lang/String":
                                text_id = args[idx]
                            idx += 1

                        if current_item == {} and not text_id:
                            if verbose:
                                print("Couldn't find any identifying information for the call to %s with %s" % (method_desc, args))
                            return

                        if not text_id:
                            if verbose:
                                print("Could not find text_id for call to %s with %s" % (method_desc, args))
                            return

                        # Call to the static register method.
                        current_item["text_id"] = text_id
                        current_item["numeric_id"] = self.cur_id
                        self.cur_id += 1
                        lang_key = "minecraft.%s" % text_id
                        if language != None and lang_key in language:
                            current_item["display_name"] = language[lang_key]
                        item_list[text_id] = current_item
                else:
                    if method_name == "<init>":
                        # Call to a constructor.  Check if the builder is in the args,
                        # and if so update the item with it
                        idx = 0
                        for arg in desc.args:
                            if arg.name == builder_class:
                                # obj.update(args[idx]) # there's nothing of value here
                                pass
                            elif arg.name == blockclass and "text_id" not in obj:
                                block = args[idx]
                                obj["text_id"] = block["text_id"]
                                if "name" in block:
                                    obj["name"] = block["name"]
                                if "display_name" in block:
                                    obj["display_name"] = block["display_name"]
                            idx += 1

                if desc.returns.name != "void":
                    if desc.returns.name == builder_class or is_item_class(desc.returns.name):
                        # Probably returning itself
                        return obj
                    else:
                        return object()

            def on_get_field(self, ins, const, obj):
                if const.class_.name.value == blocklist:
                    # Getting a block; put it on the stack.
                    block_name = aggregate["blocks"]["block_fields"][const.name_and_type.name.value]
                    if block_name not in aggregate["blocks"]["block"]:
                        if verbose:
                            print("No information available for item-block for %s/%s" % (const.name_and_type.name.value, block_name))
                        return {}
                    else:
                        return aggregate["blocks"]["block"][block_name]
                else:
                    return const

            def on_put_field(self, ins, const, obj, value):
                raise Exception("unexpected putfield: %s" % ins)

        walk_method(cf, method, Walker(), verbose)

    @staticmethod
    def _process_1point12(aggregate, classloader, verbose):
        superclass = aggregate["classes"]["item.superclass"]
        blockclass = aggregate["classes"]["block.superclass"]
        blocklist = aggregate["classes"]["block.list"]

        is_flattened = aggregate["version"]["is_flattened"]

        def add_block_info_to_item(field_info, item):
            """Adds data from the given field (should be in Blocks) to the given item"""
            assert field_info["class"] == blocklist

            block_name = aggregate["blocks"]["block_fields"][field_info["name"]]
            if block_name not in aggregate["blocks"]["block"]:
                if verbose:
                    print("No information available for item-block for %s/%s" % (field_info["name"], block_name))
                return
            block = aggregate["blocks"]["block"][block_name]

            if not is_flattened and "numeric_id" in block:
                item["numeric_id"] = block["numeric_id"]
            item["text_id"] = block["text_id"]
            if "name" in block:
                item["name"] = block["name"]
            if "display_name" in block:
                item["display_name"] = block["display_name"]

        cf = classloader.load(superclass + ".class")

        # Find the registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)
        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        string_setter = cf.methods.find_one(returns="L" + superclass + ";",
                args="Ljava/lang/String;",
                f=lambda x: not x.access_flags.acc_static)

        if string_setter:
            # There will be 2, but the first one is the name setter
            name_setter = string_setter.name.value + cf.constants.get(string_setter.descriptor.index).value
        else:
            name_setter = None

        register_item_block_method = cf.methods.find_one(args='L' + blockclass + ';', returns="V")
        register_item_block_method_custom = cf.methods.find_one(args='L' + blockclass + ';L' + superclass + ';', returns="V")
        register_item_method = cf.methods.find_one(args='ILjava/lang/String;L' + superclass + ';', returns="V") \
                or cf.methods.find_one(args='Ljava/lang/String;L' + superclass + ';', returns="V")

        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.code.disassemble():
            if ins.mnemonic == "new":
                const = cf.constants.get(ins.operands[0].value)
                item_block_class = const.name.value
                break

        stack = []
        current_item = {
            "class": None,
            "calls": {}
        }
        tmp = []

        for ins in method.code.disassemble():
            if ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value

                class_file = classloader.load(class_name + ".class")
                if class_file.super_.name.value == "java/lang/Object":
                    # A function created for an item shouldn't be counted - we
                    # only want items, not Functions.
                    # I would check directly against the interface but I can't
                    # seem to get that to work.
                    if class_file.this.name.value != superclass:
                        # If it's a call to 'new Item()' then it's still an item
                        continue

                current_item = {
                    "class": class_name,
                    "calls": {}
                }

                if len(stack) == 2:
                    # If the block is constructed in the registration method,
                    # like `registerBlock(1, "stone", (new BlockStone()))`, then
                    # the parameters are pushed onto the stack before the
                    # constructor is called.
                    current_item["numeric_id"] = stack[0]
                    current_item["text_id"] = stack[1]
                elif len(stack) == 1:
                    if isinstance(stack[0], six.string_types):
                        current_item["text_id"] = stack[0]
                    else:
                        # Assuming this is a field set via getstatic
                        add_block_info_to_item(stack[0], current_item)
                stack = []
            elif ins.mnemonic.startswith("fconst"):
                stack.append(float(ins.mnemonic[-1]))
            elif ins.mnemonic in ("bipush", "sipush"):
                stack.append(ins.operands[0].value)
            elif ins.mnemonic in ("ldc", "ldc_w"):
                const = cf.constants.get(ins.operands[0].value)

                if isinstance(const, ConstantClass):
                    stack.append("%s.class" % const.name.value)
                elif isinstance(const, String):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
            elif ins.mnemonic in ("invokevirtual", "invokespecial"):
                # A method invocation
                const = cf.constants.get(ins.operands[0].value)
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                current_item["calls"][method_name] = stack
                current_item["calls"][method_name + method_desc] = stack
                stack = []
            elif ins.mnemonic == "getstatic":
                const = cf.constants.get(ins.operands[0].value)
                #TODO: Is this the right way to represent a field on the stack?
                stack.append({"class": const.class_.name.value,
                        "name": const.name_and_type.name.value})
            elif ins.mnemonic == "invokestatic":
                const = cf.constants.get(ins.operands[0].value)
                name_index = const.name_and_type.name.index
                descriptor_index = const.name_and_type.descriptor.index
                if name_index == register_item_block_method.name.index and descriptor_index == register_item_block_method.descriptor.index:
                    current_item["class"] = item_block_class
                    if len(stack) == 1:
                        # Assuming this is a field set via getstatic
                        add_block_info_to_item(stack[0], current_item)
                elif name_index == register_item_method.name.index and descriptor_index == register_item_method.descriptor.index:
                    # Some items are constructed as a method variable rather
                    # than directly in the registration method; thus the
                    # paremters are set here.
                    if len(stack) == 2:
                        current_item["numeric_id"] = stack[0]
                        current_item["text_id"] = stack[1]
                    elif len(stack) == 1:
                        current_item["text_id"] = stack[0]

                stack = []
                tmp.append(current_item)
                current_item = {
                    "class": None,
                    "calls": {}
                }

        if is_flattened:
            # Current IDs are incremental, manually track them
            cur_id = 0

        for item in tmp:
            if not "text_id" in item:
                init_one_block = "<init>(L" + blockclass + ";)V"
                init_two_blocks = "<init>(L" + blockclass + ";L" + blockclass + ";)V"
                if init_one_block in item["calls"]:
                    add_block_info_to_item(item["calls"][init_one_block][0], item)
                elif init_two_blocks in item["calls"]:
                    # Skulls use this
                    add_block_info_to_item(item["calls"][init_two_blocks][0], item)
                else:
                    if verbose:
                        print("Dropping nameless item, couldn't identify ctor for a block: %s" % item)
                    continue

                if not "text_id" in item:
                    if verbose:
                        print("Even after item block handling, no name: %s" % item)
                    continue

            final = {}

            if "numeric_id" in item:
                assert not is_flattened
                final["numeric_id"] = item["numeric_id"]
            else:
                assert is_flattened
                final["numeric_id"] = cur_id
                cur_id += 1

            if "text_id" in item:
                final["text_id"] = item["text_id"]
            final["class"] = item["class"]

            if "name" in item:
                final["name"] = item["name"]
            if "display_name" in item:
                final["display_name"] = item["display_name"]

            if name_setter in item["calls"]:
                final["name"] = item["calls"][name_setter][0]

            if "name" in final:
                lang_key = "%s.name" % final["name"]
            else:
                # 17w43a (1.13) and above - no specific translation string, only the id
                lang_key = "minecraft.%s" % final["text_id"]
            if language and lang_key in language:
                final["display_name"] = language[lang_key]

            item_list[final["text_id"]] = final
