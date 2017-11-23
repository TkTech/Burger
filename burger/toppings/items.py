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
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

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
        "version.protocol"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["item.superclass"]
        blockclass = aggregate["classes"]["block.superclass"]
        blocklist = aggregate["classes"]["block.list"]

        def add_block_info_to_item(field_info, item):
            """Adds data from the given field (should be in Blocks) to the given item"""
            assert field_info["class"] == blocklist

            block_name = aggregate["blocks"]["block_fields"][field_info["name"]]
            if block_name not in aggregate["blocks"]["block"]:
                if verbose:
                    print "No information available for item-block for %s/%s" % (field_info["name"], block_name)
                return
            block = aggregate["blocks"]["block"][block_name]

            if "numeric_id" in block:
                current_item["numeric_id"] = block["numeric_id"]
            current_item["text_id"] = block["text_id"]
            if "name" in block:
                current_item["name"] = block["name"]
            if "display_name" in block:
                current_item["display_name"] = block["display_name"]

        cf = ClassFile(StringIO(jar.read(superclass + ".class")))

        # Find the registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)
        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})
        item_fields = items.setdefault("item_fields", {})

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
            #print "INS",ins
            if ins.mnemonic == "new":
                # The beginning of a new block definition
                const = cf.constants.get(ins.operands[0].value)
                class_name = const.name.value

                class_file = ClassFile(StringIO(jar.read(class_name + ".class")))
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
                    if isinstance(stack[0], (str, unicode)):
                        current_item["text_id"] = stack[0]
                    else:
                        # Assuming this is a field set via getstatic
                        add_block_info_to_item(stack[0], current_item)
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
                    current_item["register_method"] = "block"
                    current_item["class"] = item_block_class
                    if len(stack) == 1:
                        # Assuming this is a field set via getstatic
                        add_block_info_to_item(stack[0], current_item)
                elif name_index == register_item_block_method_custom.name.index and descriptor_index == register_item_block_method_custom.descriptor.index:
                    current_item["register_method"] = "block_and_item"
                    # Other information was set at 'new'
                elif name_index == register_item_method.name.index and descriptor_index == register_item_method.descriptor.index:
                    current_item["register_method"] = "item"
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

        for item in tmp:
            if not "text_id" in item:
                print "Dropping nameless item:", item
                continue

            final = {}

            if "numeric_id" in item:
                final["numeric_id"] = item["numeric_id"]
            if "text_id" in item:
                final["text_id"] = item["text_id"]
            final["register_method"] = item["register_method"]
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

        # Go through the item list and add the field info.
        list = aggregate["classes"]["item.list"]
        lcf = ClassFile(StringIO(jar.read(list + ".class")))

        # Find the static block, and load the fields for each.
        method = lcf.methods.find_one(name="<clinit>")
        item_name = ""
        for ins in method.code.disassemble():
            if ins.mnemonic in ("ldc", "ldc_w"):
                const = lcf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantString):
                    item_name = const.string.value
            elif ins.mnemonic == "putstatic":
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                item_list[item_name]["field"] = field
                item_fields[field] = item_name

        items["info"] = {
            "count": len(item_list),
            "real_count": len(tmp)
        }
