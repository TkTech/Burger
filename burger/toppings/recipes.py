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
from solum import ClassFile, ConstantType
from solum.descriptor import method_descriptor

from .topping import Topping


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

        cf = jar.open_class(superclass)

        # Find the loader function, which takes nothing, returns nothing,
        # and is private.
        method = cf.methods.find_one(
            returns="void",
            args=(),
            f=lambda x: x.is_private
        )

        # Find the set function, so we can figure out what class defines
        # a recipe.
        setters = cf.methods.find(
            returns="void",
            f=lambda x: "java.lang.Object[]" in x.args
        )
        target_class = setters[0].args[0]
        setter_names = [x.name for x in setters]

        def find_recipes(jar, cf, method, target_class, setter_names):
            # Temporary state variables
            tmp_recipes = []
            started_item = False
            next_push_is_val = False
            block_substitute = None
            block_subs = {}
            rows = []
            make_count = 0
            recipe_target = None
            pushes_are_counts = False
            positions = True

            # Iterate over the methods instructions from the
            # bottom-up so we can catch the invoke/new range.
            for ins in method.instructions.reverse():
                # Find the call that stores the generated recipe.
                if ins.name == "invokevirtual" and not started_item:
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    # Parse the string method descriptor
                    desc = const["name_and_type"]["descriptor"]["value"]
                    args, returns = method_descriptor(desc)

                    # We've found the recipe storage method
                    if "java.lang.Object[]" in args and returns == "void":
                        started_item = True
                        pushes_are_counts = False
                        next_push_is_val = False
                        rows = []
                        make_count = 0
                        recipe_target = None
                        method_name = const["name_and_type"]["name"]["value"]
                        positions = method_name == setter_names[0]
                        if positions:
                            block_subs = {}
                        else:
                            block_subs = []
                    elif superclass in args:
                        _class = const["class"]["name"]["value"]
                        sub_cf = jar.open_class(_class)
                        tmp_recipes += find_recipes(
                            jar, sub_cf,
                            sub_cf.methods.find_one(args=args),
                            target_class, setter_names
                        )
                # We've found the start of the recipe declaration (or the end
                # as it is in our case).
                elif ins.name == "new" and started_item:
                    started_item = False
                    if positions:
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
                elif (ins.name == "getstatic" and started_item
                        and not pushes_are_counts):
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    cl_name = const["class"]["name"]["value"]
                    cl_field = const["name_and_type"]["name"]["value"]

                    block_substitute = (cl_name, cl_field)
                    if not positions:
                        block_subs.append(block_substitute)
                elif ins.name == "getstatic" and pushes_are_counts:
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    cl_name = const["class"]["name"]["value"]
                    cl_field = const["name_and_type"]["name"]["value"]

                    recipe_target = (cl_name, cl_field)
                # Block string substitute value
                elif ins.name == "bipush" and next_push_is_val:
                    next_push_is_val = False
                    block_subs[chr(ins.operands[0][1])] = block_substitute
                # Number of items that the recipe makes
                elif ins.name == "bipush" and pushes_are_counts:
                    make_count = ins.operands[0][1]
                elif ins.name.startswith("iconst_") and pushes_are_counts:
                    make_count = int(ins.name[-1])
                # Recipe row
                elif ins.name == "ldc" and started_item:
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    if const['tag'] == ConstantType.STRING:
                        rows.append(const['string']['value'])
                # The Character.valueOf() call
                elif ins.name == "invokestatic":
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    # Parse the string method descriptor
                    desc = const["name_and_type"]["descriptor"]["value"]
                    args, returns = method_descriptor(desc)

                    if "char" in args and returns == "java.lang.Character":
                        # The next integer push will be the character value.
                        next_push_is_val = True
                elif ins.name == "invokespecial" and started_item:
                    const_i = ins.operands[0][1]
                    const = cf.constants[const_i]

                    name = const["name_and_type"]["name"]["value"]
                    if name == "<init>":
                        pushes_are_counts = True
            return tmp_recipes

        tmp_recipes = find_recipes(jar, cf, method, target_class, setter_names)

        # Re-arrange the block class so the key is the class
        # name and field name.
        block_class = aggregate["classes"]["block.superclass"]
        block_map = {}
        for id_, block in aggregate["blocks"]["block"].iteritems():
            block_map["%s:%s" % (block_class, block["field"])] = block

        item_class = aggregate["classes"]["item.superclass"]
        item_map = {}
        for id_, item in aggregate["items"]["item"].iteritems():
            item_map["%s:%s" % (item_class, item["field"])] = item

        def getName(cls_fld):
            if cls_fld is None:
                return None
            field = ":".join(cls_fld)
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
            if isinstance(target, dict):
                key = target["id"]
            elif target is None:
                key = "NA"
            else:
                final["field"] = target
                key = ":".join(final["field"])

            if shape:
                rmap = []
                for row in recipe["rows"]:
                    tmp = []
                    for col in row:
                        if col == ' ':
                            tmp.append(0)
                        elif col in recipe["substitutes"]:
                            if isinstance(recipe["substitutes"][col], dict):
                                tmp.append(recipe["substitutes"][col]["id"])
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
