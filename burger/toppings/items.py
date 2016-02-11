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
            block = aggregate["blocks"]["block"][block_name]
            
            current_item["numeric_id"] = block["numeric_id"]
            current_item["text_id"] = block["text_id"]
            if "name" in block:
                current_item["name"] = block["name"]
            if "display_name" in block:
                current_item["display_name"] = block["display_name"]
        
        cf = jar.open_class(superclass)

        # Find the static constructor
        method = cf.methods.find_one(args=(), returns="void", flags=9)
        items = aggregate.setdefault("items", {})
        item_list = items.setdefault("item", {})

        if "item" in aggregate["language"]:
            language = aggregate["language"]["item"]
        else:
            language = None

        string_setters = cf.methods.find(returns=superclass,
                args=("java.lang.String",),
                f=lambda x: not x.is_static)
        # There will be 2, but the first one is the name setter
        name_setter = string_setters[0].name + cf.constants[string_setters[0].descriptor_index]["value"]
        
        register_item_block_method = cf.methods.find_one(args=(blockclass, ), returns="void")
        register_item_block_method_custom = cf.methods.find_one(args=(blockclass, superclass), returns="void")
        register_item_method = cf.methods.find_one(args=('int', 'java.lang.String', superclass), returns="void")

        item_block_class = None
        # Find the class used that represents an item that is a block
        for ins in register_item_block_method.instructions:
            if ins.name == "new":
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                item_block_class = const["name"]["value"]
                break

        stack = []
        current_item = {
            "class": None,
            "calls": {}
        }
        tmp = []
        
        for ins in method.instructions:
            #print "INS",ins
            if ins.name == "new":
                # The beginning of a new block definition
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                class_name = const["name"]["value"]
                
                class_file = jar.open_class(class_name)
                if class_file.superclass == "java/lang/Object":
                    # A function created for an item shouldn't be counted - we
                    # only want items, not Functions.
                    # I would check directly against the interface but I can't
                    # seem to get that to work.
                    if class_file.this != superclass:
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
                    # Assuming this is a field set via getstatic
                    add_block_info_to_item(stack[0], current_item)
                else:
                    print stack
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
                current_item["calls"][method_name] = stack
                current_item["calls"][method_name + method_desc] = stack
                stack = []
            elif ins.name == "getstatic":
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                #TODO: Is this the right way to represent a field on the stack?
                stack.append({"class": const["class"]["name"]["value"],
                        "name": const["name_and_type"]["name"]["value"]})
            elif ins.name == "invokestatic":
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                name_index = const["name_and_type"]["name"]["pos"]
                descriptor_index = const["name_and_type"]["descriptor"]["pos"]
                if name_index == register_item_block_method.name_index and descriptor_index == register_item_block_method.descriptor_index:
                    current_item["register_method"] = "block"
                    current_item["class"] = item_block_class
                    if len(stack) == 1:
                        # Assuming this is a field set via getstatic
                        add_block_info_to_item(stack[0], current_item)
                elif name_index == register_item_block_method_custom.name_index and descriptor_index == register_item_block_method_custom.descriptor_index:
                    current_item["register_method"] = "block_and_item"
                    # Other information was set at 'new'
                elif name_index == register_item_method.name_index and descriptor_index == register_item_method.descriptor_index:
                    current_item["register_method"] = "item"
                    if len(stack) == 2:
                        # Some blocks are constructed as a method variable rather
                        # than directly in the registration method; thus the
                        # paremters are set here.
                        current_item["numeric_id"] = stack[0]
                        current_item["text_id"] = stack[1]

                stack = []
                tmp.append(current_item)
                current_item = {
                    "class": None,
                    "calls": {}
                }

        for item in tmp:
            final = {}

            if "name" in item:
                final["name"] = item["name"]
            if "display_name" in item:
                final["display_name"] = item["display_name"]

            if name_setter in item["calls"]:
                final["name"] = item["calls"][name_setter][0]

                lang_key = "%s.name" % final["name"]
                if language and lang_key in language:
                    final["display_name"] = language[lang_key]

            if "numeric_id" in item:
                final["numeric_id"] = item["numeric_id"]
            if "text_id" in item:
                final["text_id"] = item["text_id"]
            final["register_method"] = item["register_method"]
            final["class"] = item["class"]

            if "text_id" in final:
                item_list[final["text_id"]] = final
            else:
                print 'ditched item', item

        items["info"] = {
            "count": len(item_list),
            "real_count": len(tmp)
        }
