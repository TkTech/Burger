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

try:
    import json
except ImportError:
    import simplejson as json

import six
import copy

class RecipesTopping(Topping):
    """Provides a list of most possible crafting recipes."""

    PROVIDES = [
        "recipes"
    ]

    DEPENDS = [
        "identify.recipe.superclass",
        "identify.block.list",
        "identify.item.list",
        "blocks",
        "items",
        "tags"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "assets/minecraft/recipes/stick.json" in classloader.path_map:
            recipe_list = RecipesTopping.find_from_json(aggregate, classloader, "assets/minecraft/recipes/", verbose)
        elif "data/minecraft/recipes/stick.json" in classloader.path_map:
            recipe_list = RecipesTopping.find_from_json(aggregate, classloader, "data/minecraft/recipes/", verbose)
        else:
            recipe_list = RecipesTopping.find_from_jar(aggregate, classloader, verbose)

        recipes = aggregate.setdefault("recipes", {})

        for recipe in recipe_list:
            makes = recipe['makes']['name']

            recipes_for_item = recipes.setdefault(makes, [])
            recipes_for_item.append(recipe)

    @staticmethod
    def find_from_json(aggregate, classloader, prefix, verbose):
        if verbose:
            print("Extracting recipes from JSON")

        recipes = []

        def parse_item(blob, allow_lists=True):
            """
            Converts a JSON item into a burger item.
            If the blob is a list, then a list is returned (if allowed).
            """
            # If the key involves a list, then convert to a list and parse them all.
            if isinstance(blob, list):
                if allow_lists:
                    return [parse_item(entry) for entry in blob]
                else:
                    raise Exception("A list of items is not allowed in this context")
            elif "tag" in blob:
                if allow_lists:
                    res = []
                    tag = blob["tag"]
                    if tag.startswith("minecraft:"):
                        tag = tag[len("minecraft:"):]
                    for id in aggregate["tags"]["items/" + tag]["values"]:
                        res.append(parse_item({"item": id}))
                    return res
                else:
                    raise Exception("A tag is not allowed in this context")
            # There's some wierd stuff regarding 0 or 32767 here; I'm not worrying about it though
            # Probably 0 is the default for results, and 32767 means "any" for ingredients
            assert "item" in blob
            result = {
                "type": "item"
            }

            id = blob["item"]
            if id.startswith("minecraft:"):
                id = id[len("minecraft:"):] # TODO: In the future, we don't want to strip namespaces

            if verbose and id not in aggregate["items"]["item"]:
                print("A recipe references item %s but that doesn't exist" % id)

            result["name"] = id

            if "data" in blob:
                result["metadata"] = blob["data"]
            if "count" in blob:
                result["count"] = blob["count"]

            return result

        for name in classloader.path_map.keys():
            if name.startswith(prefix) and name.endswith(".json"):
                recipe_id = "minecraft:" + name[len(prefix):-len(".json")]
                try:
                    with classloader.open(name) as fin:
                        data = json.load(fin)

                    assert "type" in data
                    recipe_type = data["type"]
                    if recipe_type.startswith("minecraft:"):
                        recipe_type = recipe_type[len("minecraft:"):]

                    if recipe_type not in ("crafting_shaped", "crafting_shapeless"):
                        # We only care about regular recipes, not furnace/loom/whatever ones.
                        continue

                    recipe = {}
                    recipe["id"] = recipe_id # new for 1.12, but used ingame

                    if "group" in data:
                        recipe["group"] = data["group"]


                    assert "result" in data
                    recipe["makes"] = parse_item(data["result"], False)
                    if "count" not in recipe["makes"]:
                        recipe["makes"]["count"] = 1 # default, TODO should we keep specifying this?

                    matching_recipes = [recipe]

                    if recipe_type == "crafting_shapeless":
                        recipe["type"] = 'shapeless'

                        assert "ingredients" in data

                        recipe["ingredients"] = []
                        for ingredient in data["ingredients"]:
                            item = parse_item(ingredient)
                            if isinstance(item, list):
                                tmp = []
                                for recipe_choice in matching_recipes:
                                    for real_item in item:
                                        recipe_choice_work = copy.deepcopy(recipe_choice)
                                        recipe_choice_work["ingredients"].append(real_item)
                                        tmp.append(recipe_choice_work)
                                matching_recipes = tmp
                            else:
                                for recipe_choice in matching_recipes:
                                    recipe_choice["ingredients"].append(item)
                    elif recipe_type == "crafting_shaped":
                        recipe["type"] = 'shape'

                        assert "pattern" in data
                        assert "key" in data

                        pattern = data["pattern"]
                        recipe["raw"] = {
                            "rows": pattern,
                            "subs": {}
                        }
                        for (id, value) in six.iteritems(data["key"]):
                            item = parse_item(value)
                            if isinstance(item, list):
                                tmp = []
                                for recipe_choice in matching_recipes:
                                    for real_item in item:
                                        recipe_choice_work = copy.deepcopy(recipe_choice)
                                        recipe_choice_work["raw"]["subs"][id] = real_item
                                        tmp.append(recipe_choice_work)
                                matching_recipes = tmp
                            else:
                                for recipe_choice in matching_recipes:
                                    recipe_choice["raw"]["subs"][id] = item

                        for recipe_choice in matching_recipes:
                            shape = []
                            for row in recipe_choice["raw"]["rows"]:
                                shape_row = []
                                for char in row:
                                    if not char.isspace():
                                        shape_row.append(recipe_choice["raw"]["subs"][char])
                                    else:
                                        shape_row.append(None)
                                shape.append(shape_row)
                            recipe_choice["shape"] = shape

                    recipes.extend(matching_recipes)
                except Exception as e:
                    print("Failed to parse %s: %s" % (recipe_id, e))
                    raise

        return recipes

    @staticmethod
    def find_from_jar(aggregate, classloader, verbose):
        superclass = aggregate["classes"]["recipe.superclass"]

        if verbose:
            print("Extracting recipes from %s" % superclass)

        cf = classloader[superclass]

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
        setter_names = [x.name.value for x in setters]

        def get_material(clazz, field):
            """Converts a class name and field into a block or item."""
            if clazz == aggregate["classes"]["block.list"]:
                if field in aggregate["blocks"]["block_fields"]:
                    name = aggregate["blocks"]["block_fields"][field]
                    return {
                        'type': 'block',
                        'name': name
                    }
                else:
                    raise Exception("Unknown block with field " + field)
            elif clazz == aggregate["classes"]["item.list"]:
                if field in aggregate["items"]["item_fields"]:
                    name = aggregate["items"]["item_fields"][field]
                    return {
                        'type': 'item',
                        'name': name
                    }
                else:
                    raise Exception("Unknown item with field " + field)
            else:
                raise Exception("Unknown list class " + clazz)

        def read_itemstack(itr):
            """Reads an itemstack from the given iterator of instructions"""
            stack = []
            while True:
                ins = itr.next()
                if ins in ("bipush", "sipush"):
                    stack.append(ins.operands[0].value)
                elif ins == "getstatic":
                    const = ins.operands[0]
                    clazz = const.class_.name.value
                    name = const.name_and_type.name.value
                    stack.append((clazz, name))
                elif ins == "invokevirtual":
                    # TODO: This is a _total_ hack...
                    # We assume that this is an enum, used to get the data value
                    # for the given block.  We also assume that the return value
                    # matches the enum constant's position... and do math from that.
                    name = stack.pop()[1]
                    # As I said... ugly.  There's probably a way better way of doing this.
                    dv = int(name, 36) - int('a', 36)
                    stack.append(dv)
                elif ins == "iadd":
                    # For whatever reason, there are a few cases where 4 is both
                    # added and subtracted to the enum constant value.
                    # So we need to handle that :/
                    i2 = stack.pop()
                    i1 = stack.pop()
                    stack.append(i1 + i2);
                elif ins == "isub":
                    i2 = stack.pop()
                    i1 = stack.pop()
                    stack.append(i1 - i2);
                elif ins == "invokespecial":
                    const = ins.operands[0]
                    if const.name_and_type.name == "<init>":
                        break

            item = get_material(*stack[0])
            if len(stack) == 3:
                item['count'] = stack[1]
                item['metadata'] = stack[2]
            elif len(stack) == 2:
                item['count'] = stack[1]
            return item

        def find_recipes(classloader, cf, method, target_class, setter_names):
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
                    const = ins.operands[0]
                    if const.name.value != itemstack:
                        # Or it could be another type; irrelevant
                        continue
                    # The crafted item, first parameter
                    crafted_item = read_itemstack(itr)

                    ins = itr.next()
                    # Size of the parameter array
                    if ins in ("bipush", "sipush"):
                        param_count = ins.operands[0].value
                    else:
                        raise Exception('Unexpected instruction: expected int constant, got ' + str(ins))

                    num_astore = 0
                    data = None
                    array = []
                    while num_astore < param_count:
                        ins = itr.next()
                        # Read through the array; some strangeness of types,
                        # though.  Also, note that the array index is pushed,
                        # but we overwrite it with the second value and just
                        # add in order instead.
                        #
                        # The weirdness here is because characters and strings are
                        # mixed; for example jukebox looks like this:
                        # new Object[] {"###", "#X#", "###", '#', Blocks.PLANKS, 'X', Items.DIAMOND}
                        if ins == "aastore":
                            num_astore += 1
                            array.append(data)
                            data = None
                        elif ins in ("ldc", "ldc_w"):
                            const = ins.operands[0]
                            # Separate into a list of characters, to disambiguate (see below)
                            data = list(const.string.value)
                        if ins in ("bipush", "sipush"):
                            data = ins.operands[0].value
                        elif ins == "invokestatic":
                            const = ins.operands[0]
                            if const.class_.name == "java/lang/Character" and const.name_and_type.name == "valueOf":
                                data = chr(data)
                            else:
                                raise Exception("Unknown method invocation: " + repr(const))
                        elif ins == "getstatic":
                            const = ins.operands[0]
                            clazz = const.class_.name.value
                            field = const.name_and_type.name.value
                            data = get_material(clazz, field)
                        elif ins == "new":
                            data = read_itemstack(itr)

                    ins = itr.next()
                    assert ins == "invokevirtual"
                    const = ins.operands[0]

                    recipe_data = {}
                    if const.name_and_type.name == setter_names[0]:
                        # Shaped
                        recipe_data['type'] = 'shape'
                        recipe_data['makes'] = crafted_item
                        rows = []
                        subs = {}
                        # Keys are a list while values are a single character;
                        # we make the keys a list merely as a way to disambiguate
                        # and rejoin it later (hacky :/)
                        try:
                            itr2 = iter(array)
                            while True:
                                obj = itr2.next()
                                if isinstance(obj, list):
                                    # Pattern
                                    rows.append("".join(obj))
                                elif isinstance(obj, six.string_types):
                                    # Character
                                    item = itr2.next()
                                    subs[obj] = item
                        except StopIteration:
                            pass
                        recipe_data['raw'] = {
                            'rows': rows,
                            'subs': subs
                        }

                        shape = []
                        for row in rows:
                            shape_row = []
                            for char in row:
                                if not char.isspace():
                                    shape_row.append(subs[char])
                                else:
                                    shape_row.append(None)
                            shape.append(shape_row)

                        recipe_data['shape'] = shape
                    else:
                        # Shapeless
                        recipe_data['type'] = 'shapeless'
                        recipe_data['makes'] = crafted_item
                        recipe_data['ingredients'] = array

                    recipes.append(recipe_data)
            except StopIteration:
                pass
            return recipes

        return find_recipes(classloader, cf, method, target_class, setter_names)
