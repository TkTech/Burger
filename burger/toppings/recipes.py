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

from jawa.util.descriptor import method_descriptor
from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class RecipesTopping(Topping):
    """Provides a list of most possible crafting recipes."""

    PROVIDES = [
        "recipes"
    ]

    DEPENDS = [
        "identify.recipe.superclass",
        "blocks",
        "items"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        superclass = aggregate["classes"]["recipe.superclass"]
        recipes = aggregate.setdefault("recipes", {})

        cf = ClassFile(StringIO(jar.read(superclass + ".class")))

        # Find the constructor
        method = cf.methods.find_one(
            name="<init>"
        )

        # Find the set function, so we can figure out what class defines
        # a recipe.
        # This method's second parameter is an array of objects.
        setters = list(cf.methods.find(
            f = lambda m: len(m.args) == 2 and m.args[1].dimensions == 1 and m.args[1].name == "java/lang/Object"
        ))

        itemstack = aggregate["classes"]["itemstack"]

        target_class = setters[0].args[0]
        setter_names = [x.name for x in setters]

        def read_itemstack(itr):
            """Reads an itemstack from the given iterator of instructions"""
            item = {}
            stack = []
            while True:
                ins = itr.next()
                if ins.mnemonic.startswith("iconst_"):
                    stack.append(int(ins.mnemonic[-1]))
                elif ins.mnemonic == "bipush":
                    stack.append(ins.operands[0].value)
                elif ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    clazz = const.class_.name.value
                    name = const.name_and_type.name.value
                    stack.append((clazz, name))
                elif ins.mnemonic == "invokevirtual":
                    # TODO: This is a _total_ hack...
                    # We assume that this is an enum, used to get the data value
                    # for the given block.  We also assume that the return value
                    # matches the enum constant's position... and do math from that.
                    name = stack.pop()[1]
                    # As I said... ugly.  There's probably a way better way of doing this.
                    dv = int(name, 36) - int('a', 36)
                    stack.append(dv)
                elif ins.mnemonic == "iadd":
                    # For whatever reason, there are a few cases where 4 is both
                    # added and subtracted to the enum constant value.
                    # So we need to handle that :/
                    i2 = stack.pop()
                    i1 = stack.pop()
                    stack.append(i1 + i2);
                elif ins.mnemonic == "isub":
                    i2 = stack.pop()
                    i1 = stack.pop()
                    stack.append(i1 - i2);
                elif ins.mnemonic == "invokespecial":
                    const = cf.constants.get(ins.operands[0].value)
                    if const.name_and_type.name.value == "<init>":
                        break
            if len(stack) == 3:
                item['amount'] = stack[0]
                item['count'] = stack[1]
                item['metadata'] = stack[2]
            elif len(stack) == 2:
                item['amount'] = stack[0]
                item['count'] = stack[1]
            elif len(stack) == 1:
                item['amount'] = stack[0]
                item['count'] = 1
            else:
                print ins, stack
            return item

        def find_recipes(jar, cf, method, target_class, setter_names):
            # Go through all instructions.
            itr = iter(method.code.disassemble())
            recipes = []
            try:
                while True:
                    ins = itr.next()
                    if ins.mnemonic != "new":
                        # Wait until an item starts
                        continue
                    # Start of another recipe - the ending item.
                    const = cf.constants.get(ins.operands[0].value)
                    if const.name.value != itemstack:
                        # Or it could be another type; irrelevant
                        continue
                    # The crafted item, first parameter
                    crafted_item = read_itemstack(itr)

                    ins = itr.next()
                    # Size of the parameter array
                    if ins.mnemonic.startswith("iconst_"):
                        param_count = int(ins.mnemonic[-1])
                    elif ins.mnemonic == "bipush":
                        param_count = ins.operands[0].value
                    else:
                        raise Exception('Unexpected instruction: expected int constant, got ' + str(ins))

                    num_astore = 0
                    while num_astore < param_count:
                        ins = itr.next()
                        if ins.mnemonic == "astore":
                            num_astore += 1
                        else:
                            print ins
            except StopIteration:
                pass
            return recipes

        tmp_recipes = find_recipes(jar, cf, method, target_class, setter_names)

        # Re-arrange the block class so the key is the class
        # name and field name.
        block_class = aggregate["classes"]["block.list"]
        block_map = {}
        for id_, block in aggregate["blocks"]["block"].iteritems():
            block_map["%s:%s" % (block_class, block["field"])] = block

        item_class = aggregate["classes"]["item.list"]
        item_map = {}
        for id_, item in aggregate["items"]["item"].iteritems():
            if "field" in item:
                item_map["%s:%s" % (item_class, item["field"])] = item

        def getName(cls_fld):
            if cls_fld is None:
                return None
            field = ":".join(cls_fld[:2])
            if field in block_map:
                return block_map[field]
            elif field in item_map:
                return item_map[field]
            else:
                return cls_fld

        for recipe in tmp_recipes:
            final = {
                "amount": recipe["makes"],
                "type": recipe["type"]
            }

            shape = recipe["type"] == "shape"

            # Filter invalid recipes
            if shape and len(recipe["rows"]) == 0:
                continue
            elif recipe["recipe_target"] == None:
                continue
            elif not shape and len(recipe["ingredients"]) == 0:
                continue

            if shape:
                final["raw"] = {
                    "rows": recipe["rows"],
                    "subs": recipe["substitutes"]
                }

            # Try to get the substitutes name
            if shape:
                subs = recipe["substitutes"]
                for sub in subs:
                    subs[sub] = getName(subs[sub])
            else:
                final["ingredients"] = []
                for ingredient in recipe["ingredients"]:
                    final["ingredients"].append(getName(ingredient))

            # Try to get the created item/block name.
            target = getName(recipe["recipe_target"])
            final["makes"] = target
            final["metadata"] = recipe["recipe_target"][2]
            if isinstance(target, dict):
                key = target["text_id"]
            elif target is None:
                key = "NA"
            else:
                final["field"] = target
                key = ":".join(str(i) for i in target)

            if shape:
                rmap = []
                for row in recipe["rows"]:
                    tmp = []
                    for col in row:
                        if col == ' ':
                            tmp.append(0)
                        elif col in recipe["substitutes"]:
                            if isinstance(recipe["substitutes"][col], dict):
                                tmp.append(recipe["substitutes"][col]["text_id"])
                            else:
                                tmp.append(":".join(
                                    recipe["substitutes"][col])
                                )
                        else:
                            tmp.append(None)
                    rmap.append(tmp)

                final["shape"] = rmap
            if key not in recipes:
                recipes[key] = []
            recipes[key].append(final)
