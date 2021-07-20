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
        "identify.item.superclass",
        "items"
    ]

    DEPENDS = [
        "identify.block.superclass",
        "identify.block.list",
        "identify.item.register",
        "identify.item.list",
        "language",
        "blocks",
        "version.protocol",
        "version.is_flattened"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        data_version = aggregate["version"]["data"] if "data" in aggregate["version"] else -1
        if data_version >= 1901: # 18w43a
            ItemsTopping._process_1point14(aggregate, classloader, verbose)
            return # This also adds classes
        elif data_version >= 1461: # 18w02a
            ItemsTopping._process_1point13(aggregate, classloader, verbose)
        else:
            ItemsTopping._process_1point12(aggregate, classloader, verbose)

        item_list = aggregate["items"]["item"]
        item_fields = aggregate["items"].setdefault("item_fields", {})

        # Go through the item list and add the field info.
        list = aggregate["classes"]["item.list"]
        lcf = classloader[list]

        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        item_name = ""
        for ins in method.code.disassemble():
            if ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if isinstance(const, String):
                    item_name = const.string.value
            elif ins == "putstatic":
                const = ins.operands[0]
                field = const.name_and_type.name.value
                if item_name in item_list:
                    item_list[item_name]["field"] = field
                elif verbose:
                    print("Cannot find an item matching %s for field %s" % (item_name, field))
                item_fields[field] = item_name

    @staticmethod
    def _process_1point14(aggregate, classloader, verbose):
        # Handles versions after 1.14 (specifically >= 18w43a)
        # All of the registration happens in the list class in this version.
        listclass = aggregate["classes"]["item.list"]
        lcf = classloader[listclass]
        superclass = next(lcf.fields.find()).type.name # The first field in the list class is an item
        cf = classloader[superclass]
        aggregate["classes"]["item.superclass"] = superclass
        blockclass = aggregate["classes"]["block.superclass"]
        blocklist = aggregate["classes"]["block.list"]

        cf = classloader[superclass]

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        # Figure out what the builder class is
        ctor = cf.methods.find_one(name="<init>")
        builder_class = ctor.args[0].name
        builder_cf = classloader[builder_class]

        # Find the max stack size method
        max_stack_method = None
        for method in builder_cf.methods.find(args='I'):
            for ins in method.code.disassemble():
                if ins.mnemonic in ("ldc", "ldc_w"):
                    const = ins.operands[0]
                    if isinstance(const, String) and const.string.value == "Unable to have damage AND stack.":
                        max_stack_method = method
                        break
            if max_stack_method:
                break
        if not max_stack_method:
            raise Exception("Couldn't find max stack size setter in " + builder_class)

        register_item_block_method = lcf.methods.find_one(args='L' + blockclass + ';', returns='L' + superclass + ';')
        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.code.disassemble():
            if ins.mnemonic == "new":
                const = ins.operands[0]
                item_block_class = const.name.value
                break

        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})
        item_fields = items.setdefault("item_fields", {})

        is_item_class_cache = {superclass: True}
        def is_item_class(name):
            if name in is_item_class_cache:
                return is_item_class_cache
            elif name == 'java/lang/Object':
                return True
            elif '/' in name:
                return False

            cf = classloader[name]
            result = is_item_class(cf.super_.name.value)
            is_item_class_cache[name] = result
            return result
        # Find the static block registration method
        method = lcf.methods.find_one(name='<clinit>')

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
                    if const.class_.name.value == listclass:
                        current_item = {}

                        text_id = None
                        for idx, arg in enumerate(desc.args):
                            if arg.name == blockclass:
                                if isinstance(args[idx], list):
                                    continue
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
                        if "max_stack_size" not in current_item:
                            current_item["max_stack_size"] = 64
                        item_list[text_id] = current_item

                        return current_item
                else:
                    if method_name == "<init>":
                        # Call to a constructor.  Check if the builder is in the args,
                        # and if so update the item with it
                        idx = 0
                        for arg in desc.args:
                            if arg.name == builder_class:
                                # Update from the builder
                                if "max_stack_size" in args[idx]:
                                    obj["max_stack_size"] = args[idx]["max_stack_size"]
                            elif arg.name == blockclass and "text_id" not in obj:
                                block = args[idx]
                                obj["text_id"] = block["text_id"]
                                if "name" in block:
                                    obj["name"] = block["name"]
                                if "display_name" in block:
                                    obj["display_name"] = block["display_name"]
                            idx += 1
                    elif method_name == max_stack_method.name.value and method_desc == max_stack_method.descriptor.value:
                        obj["max_stack_size"] = args[0]

                if desc.returns.name != "void":
                    if desc.returns.name == builder_class or is_item_class(desc.returns.name):
                        if ins.mnemonic == "invokestatic":
                            # Probably returning itself, but through a synthetic method
                            return args[0]
                        else:
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
                elif const.class_.name.value == listclass:
                    return item_list[item_fields[const.name_and_type.name.value]]
                else:
                    return const

            def on_put_field(self, ins, const, obj, value):
                if isinstance(value, dict):
                    field = const.name_and_type.name.value
                    value["field"] = field
                    item_fields[const.name_and_type.name.value] = value["text_id"]

        walk_method(cf, method, Walker(), verbose)

    @staticmethod
    def _process_1point13(aggregate, classloader, verbose):
        # Handles versions after 1.13 (specifically >= 18w02a)
        superclass = aggregate["classes"]["item.register"]
        aggregate["classes"]["item.superclass"] = superclass
        blockclass = aggregate["classes"]["block.superclass"]
        blocklist = aggregate["classes"]["block.list"]

        cf = classloader[superclass]

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        # Figure out what the builder class is
        ctor = cf.methods.find_one(name="<init>")
        builder_class = ctor.args[0].name
        builder_cf = classloader[builder_class]

        # Find the max stack size method
        max_stack_method = None
        for method in builder_cf.methods.find(args='I'):
            for ins in method.code.disassemble():
                if ins in ("ldc", "ldc_w"):
                    const = ins.operands[0]
                    if isinstance(const, String) and const == "Unable to have damage AND stack.":
                        max_stack_method = method
                        break
        if not max_stack_method:
            raise Exception("Couldn't find max stack size setter in " + builder_class)

        register_item_block_method = cf.methods.find_one(args='L' + blockclass + ';', returns="V")
        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.code.disassemble():
            if ins == "new":
                const = ins.operands[0]
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

            cf = classloader[name]
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

                if ins == "invokestatic":
                    if const.class_.name == superclass:
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
                        if "max_stack_size" not in current_item:
                            current_item["max_stack_size"] = 64
                        item_list[text_id] = current_item
                else:
                    if method_name == "<init>":
                        # Call to a constructor.  Check if the builder is in the args,
                        # and if so update the item with it
                        idx = 0
                        for arg in desc.args:
                            if arg.name == builder_class:
                                # Update from the builder
                                if "max_stack_size" in args[idx]:
                                    obj["max_stack_size"] = args[idx]["max_stack_size"]
                            elif arg.name == blockclass and "text_id" not in obj:
                                block = args[idx]
                                obj["text_id"] = block["text_id"]
                                if "name" in block:
                                    obj["name"] = block["name"]
                                if "display_name" in block:
                                    obj["display_name"] = block["display_name"]
                            idx += 1
                    elif method_name == max_stack_method.name.value and method_desc == max_stack_method.descriptor.value:
                        obj["max_stack_size"] = args[0]

                if desc.returns.name != "void":
                    if desc.returns.name == builder_class or is_item_class(desc.returns.name):
                        if ins == "invokestatic":
                            # Probably returning itself, but through a synthetic method
                            return args[0]
                        else:
                            # Probably returning itself
                            return obj
                    else:
                        return object()

            def on_get_field(self, ins, const, obj):
                if const.class_.name == blocklist:
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
        superclass = aggregate["classes"]["item.register"]
        aggregate["classes"]["item.superclass"] = superclass
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

        cf = classloader[superclass]

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
        int_setter = cf.methods.find_one(returns="L" + superclass + ";",
                args="I", f=lambda x: not x.access_flags.acc_static)

        if string_setter:
            # There will be 2, but the first one is the name setter
            name_setter = string_setter.name.value + string_setter.descriptor.value
        else:
            name_setter = None

        if int_setter:
            # There are multiple; the first one sets max stack size and another
            # sets max durability.  However, durability is called in the constructor,
            # so we can't use it easily
            stack_size_setter = int_setter.name.value + int_setter.descriptor.value
        else:
            stack_size_setter = None

        register_item_block_method = cf.methods.find_one(args='L' + blockclass + ';', returns="V")
        register_item_block_method_custom = cf.methods.find_one(args='L' + blockclass + ';L' + superclass + ';', returns="V")
        register_item_method = cf.methods.find_one(args='ILjava/lang/String;L' + superclass + ';', returns="V") \
                or cf.methods.find_one(args='Ljava/lang/String;L' + superclass + ';', returns="V")

        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.code.disassemble():
            if ins == "new":
                const = ins.operands[0]
                item_block_class = const.name.value
                break

        stack = []
        current_item = {
            "class": None,
            "calls": {}
        }
        tmp = []

        for ins in method.code.disassemble():
            if ins == "new":
                # The beginning of a new block definition
                const = ins.operands[0]
                class_name = const.name.value

                class_file = classloader[class_name]
                if class_file.super_.name == "java/lang/Object":
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
            elif ins in ("bipush", "sipush"):
                stack.append(ins.operands[0].value)
            elif ins in ("ldc", "ldc_w"):
                const = ins.operands[0]

                if isinstance(const, ConstantClass):
                    stack.append("%s.class" % const.name.value)
                elif isinstance(const, String):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
            elif ins in ("invokevirtual", "invokespecial"):
                # A method invocation
                const = ins.operands[0]
                method_name = const.name_and_type.name.value
                method_desc = const.name_and_type.descriptor.value
                current_item["calls"][method_name] = stack
                current_item["calls"][method_name + method_desc] = stack
                stack = []
            elif ins == "getstatic":
                const = ins.operands[0]
                #TODO: Is this the right way to represent a field on the stack?
                stack.append({"class": const.class_.name.value,
                        "name": const.name_and_type.name.value})
            elif ins == "invokestatic":
                const = ins.operands[0]
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

            if stack_size_setter in item["calls"]:
                final["max_stack_size"] = item["calls"][stack_size_setter][0]
            else:
                final["max_stack_size"] = 64

            if "name" in final:
                lang_key = "%s.name" % final["name"]
            else:
                # 17w43a (1.13) and above - no specific translation string, only the id
                lang_key = "minecraft.%s" % final["text_id"]
            if language and lang_key in language:
                final["display_name"] = language[lang_key]

            item_list[final["text_id"]] = final
