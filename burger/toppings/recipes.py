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

        target_class = setters[0].args[0]
        setter_names = [x.name for x in setters]
        def find_recipes(jar, cf, method, target_class, setter_names):
            # Temporary state variables
            tmp_recipes = []
            started_item = False
            next_push_is_val = False
            with_metadata = False
            block_substitute = None
            block_subs = {}
            rows = []
            make_count = 0
            metadata = 0
            recipe_target = None
            pushes_are_counts = False
            shaped_recipe = True
            # Iterate over the methods instructions from the
            # bottom-up so we can catch the invoke/new range.
            for ins in reversed(list(method.code.disassemble())):
                # Find the call that stores the generated recipe.
                if ins.mnemonic == "invokevirtual" and not started_item:
                    const = cf.constants.get(ins.operands[0].value)

                    # Parse the string method descriptor
                    desc = method_descriptor(const.name_and_type.descriptor.value)

                    # We've found the recipe storage method
                    if "[Ljava/lang/Object;" in desc.args_descriptor:
                        started_item = True
                        pushes_are_counts = False
                        next_push_is_val = False
                        with_metadata = False
                        rows = []
                        make_count = 0
                        metadata = 0
                        recipe_target = None
                        method_name = const.name_and_type.name.value
                        shaped_recipe = (method_name == setter_names[0].value)
                        if shaped_recipe:
                            block_subs = {}
                        else:
                            block_subs = []
                    elif superclass in desc.args_descriptor:
                        _class = const.class_.name.value
                        sub_cf = ClassFile(StringIO(jar.read(_class + ".class")))
                        tmp_recipes += find_recipes(
                            jar, sub_cf,
                            # This might not be right: There may be another method...
                            # I may also want to use the name and return type?
                            sub_cf.methods.find_one(args=desc.args_descriptor),
                            target_class, setter_names
                        )
                # We've found the start of the recipe declaration (or the end
                # as it is in our case).
                elif ins.mnemonic == "new" and started_item:
                    started_item = False
                    if shaped_recipe:
                        tmp_recipes.append({
                            "type": "shape",
                            "substitutes": block_subs,
                            "rows": rows,
                            "makes": make_count,
                            "recipe_target": recipe_target
                        })
                    else:
                        tmp_recipes.append({
                            "type": "shapeless",
                            "ingredients": block_subs,
                            "makes": make_count,
                            "recipe_target": recipe_target
                        })
                # The item/block to be substituted
                elif (ins.mnemonic == "getstatic" and started_item
                        and not pushes_are_counts):
                    const = cf.constants.get(ins.operands[0].value)

                    cl_name = const.class_.name.value
                    cl_field = const.name_and_type.name.value

                    block_substitute = (cl_name, cl_field)
                    if not shaped_recipe:
                        block_subs.append(block_substitute)
                elif ins.mnemonic == "getstatic" and pushes_are_counts:
                    const = cf.constants.get(ins.operands[0].value)

                    cl_name = const.class_.name.value
                    cl_field = const.name_and_type.name.value

                    recipe_target = (cl_name, cl_field, metadata)
                # Block string substitute value
                elif ins.mnemonic == "bipush" and next_push_is_val:
                    next_push_is_val = False
                    block_subs[chr(ins.operands[0].value)] = block_substitute
                # Number of items that the recipe makes
                elif ins.mnemonic == "bipush" and pushes_are_counts:
                    make_count = ins.operands[0].value
                    if with_metadata:
                        metadata = make_count
                        with_metadata = False
                elif ins.mnemonic.startswith("iconst_") and pushes_are_counts:
                    make_count = int(ins.mnemonic[-1])
                    if with_metadata:
                        metadata = make_count
                        with_metadata = False
                # Recipe row
                elif ins.mnemonic == "ldc" and started_item:
                    const = cf.constants.get(ins.operands[0].value)

                    if isinstance(const, ConstantString):
                        rows.append(const.string.value)
                # The Character.valueOf() call
                elif ins.mnemonic == "invokestatic":
                    const = cf.constants.get(ins.operands[0].value)

                    # Parse the string method descriptor
                    desc = method_descriptor(const.name_and_type.descriptor.value)

                    if len(desc.args) == 1 and desc.args[0].name == "char" and desc.returns.name == "java/lang/Character":
                        # The next integer push will be the character value.
                        next_push_is_val = True
                elif ins.mnemonic == "invokespecial" and started_item:
                    const = cf.constants.get(ins.operands[0].value)

                    name = const.name_and_type.name.value
                    if name == "<init>":
                        pushes_are_counts = True
                        if ("II" in
                                const.name_and_type.descriptor.value):
                            with_metadata = True
            return tmp_recipes

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
