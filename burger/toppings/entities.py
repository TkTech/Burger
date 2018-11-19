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

import six

from .topping import Topping
from burger.util import class_from_invokedynamic

from jawa.constants import *

class EntityTopping(Topping):
    """Gets most entity types."""

    PROVIDES = [
        "entities.entity"
    ]

    DEPENDS = [
        "identify.entity.list",
        "version.entity_format",
        "language"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        # Decide which type of entity logic should be used.

        handlers = {
            "1.10": EntityTopping._entities_1point10,
            "1.11": EntityTopping._entities_1point11,
            "1.13": EntityTopping._entities_1point13
        }
        entity_format = aggregate["version"]["entity_format"]
        if entity_format in handlers:
            handlers[entity_format](aggregate, classloader, verbose)
        else:
            if verbose:
                print("Unknown entity format %s" % entity_format)
            return

        entities = aggregate["entities"]

        for e in six.itervalues(entities["entity"]):
            cf = classloader[e["class"]]
            size = EntityTopping.size(cf)
            if size:
                e["width"], e["height"], texture = size
                if texture:
                    e["texture"] = texture

        entities["info"] = {
            "entity_count": len(entities["entity"])
        }

    @staticmethod
    def _entities_1point13(aggregate, classloader, verbose):
        if verbose:
            print("Using 1.13 entity format")

        superclass = aggregate["classes"]["entity.list"]
        cf = classloader[superclass]

        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})

        method = cf.methods.find_one(name="<clinit>")

        stack = []
        numeric_id = 0
        for ins in method.code.disassemble():
            if ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if isinstance(const, ConstantClass):
                    stack.append(const.name.value)
                elif isinstance(const, String):
                    stack.append(const.string.value)
            elif ins == "invokedynamic":
                stack.append(class_from_invokedynamic(ins, cf))
            elif ins == "putstatic":
                if len(stack) in (2, 3):
                    if len(stack) == 3:
                        # In 18w07a, they added a parameter for the entity class,
                        # in addition to the invokedynamic.  Make sure both are the same.
                        assert stack[1] == stack[2]

                    name = stack[0]

                    entity[name] = {
                        "id": numeric_id,
                        "name": name,
                        "class": stack[1]
                    }
                    if "minecraft." + name in aggregate["language"]["entity"]:
                        entity[name]["display_name"] = aggregate["language"]["entity"]["minecraft." + name]

                    numeric_id += 1
                stack = []

    @staticmethod
    def _entities_1point11(aggregate, classloader, verbose):
        # 1.11 logic
        if verbose:
            print("Using 1.11 entity format")

        superclass = aggregate["classes"]["entity.list"]
        cf = classloader[superclass]

        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})

        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        stack = []
        minecart_info = {}
        for ins in method.code.disassemble():
            if ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if isinstance(const, ConstantClass):
                    stack.append(const.name.value)
                elif isinstance(const, String):
                    stack.append(const.string.value)
                else:
                    stack.append(const.value)
            elif ins in ("bipush", "sipush"):
                stack.append(ins.operands[0].value)
            elif ins == "getstatic":
                # Minecarts use an enum for their data - assume that this is that enum
                const = ins.operands[0]
                if not "types_by_field" in minecart_info:
                    EntityTopping._load_minecart_enum(classloader, const.class_.name.value, minecart_info)
                # This technically happens when invokevirtual is called, but do it like this for simplicity
                minecart_name = minecart_info["types_by_field"][const.name_and_type.name.value]
                stack.append(minecart_info["types"][minecart_name]["entitytype"])
            elif ins == "invokestatic":
                if len(stack) == 4:
                    # Initial registration
                    name = stack[1]
                    old_name = stack[3]

                    entity[name] = {
                        "id": stack[0],
                        "name": name,
                        "class": stack[2],
                        "old_name": old_name
                    }

                    if old_name + ".name" in aggregate["language"]["entity"]:
                        entity[name]["display_name"] = aggregate["language"]["entity"][old_name + ".name"]
                elif len(stack) == 3:
                    # Spawn egg registration
                    name = stack[0]
                    if name in entity:
                        entity[name]["egg_primary"] = stack[1]
                        entity[name]["egg_secondary"] = stack[2]
                    else:
                        print("Missing entity during egg registration: %s" % name)
                stack = []

    @staticmethod
    def _entities_1point10(aggregate, classloader, verbose):
        # 1.10 logic
        if verbose:
            print("Using 1.10 entity format")

        superclass = aggregate["classes"]["entity.list"]
        cf = classloader[superclass]

        method = cf.methods.find_one(name="<clinit>")
        mode = "starting"

        superclass = aggregate["classes"]["entity.list"]
        cf = classloader[superclass]

        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})
        alias = None

        stack = []
        tmp = {}
        minecart_info = {}

        for ins in method.code.disassemble():
            if mode == "starting":
                # We don't care about the logger setup stuff at the beginning;
                # wait until an entity definition starts.
                if ins in ("ldc", "ldc_w"):
                    mode = "entities"
            # elif is not used here because we need to handle modes changing
            if mode != "starting":
                if ins in ("ldc", "ldc_w"):
                    const = ins.operands[0]
                    if isinstance(const, ConstantClass):
                        stack.append(const.name.value)
                    elif isinstance(const, String):
                        stack.append(const.string.value)
                    else:
                        stack.append(const.value)
                elif ins in ("bipush", "sipush"):
                    stack.append(ins.operands[0].value)
                elif ins == "new":
                    # Entity aliases (for lack of a better term) start with 'new's.
                    # Switch modes (this operation will be processed there)
                    mode = "aliases"
                    const = ins.operands[0]
                    stack.append(const.name.value)
                elif ins == "getstatic":
                    # Minecarts use an enum for their data - assume that this is that enum
                    const = ins.operands[0]
                    if not "types_by_field" in minecart_info:
                        EntityTopping._load_minecart_enum(classloader, const.class_.name.value, minecart_info)
                    # This technically happens when invokevirtual is called, but do it like this for simplicity
                    minecart_name = minecart_info["types_by_field"][const.name_and_type.name.value]
                    stack.append(minecart_info["types"][minecart_name]["entitytype"])
                elif ins == "invokestatic":  # invokestatic
                    if mode == "entities":
                        tmp["class"] = stack[0]
                        tmp["name"] = stack[1]
                        tmp["id"] = stack[2]
                        if (len(stack) >= 5):
                            tmp["egg_primary"] = stack[3]
                            tmp["egg_secondary"] = stack[4]
                        if tmp["name"] + ".name" in aggregate["language"]["entity"]:
                            tmp["display_name"] = aggregate["language"]["entity"][tmp["name"] + ".name"]
                        entity[tmp["name"]] = tmp
                    elif mode == "aliases":
                        tmp["entity"] = stack[0]
                        tmp["name"] = stack[1]
                        if (len(stack) >= 5):
                            tmp["egg_primary"] = stack[2]
                            tmp["egg_secondary"] = stack[3]
                        tmp["class"] = stack[-1] # last item, made by new.
                        if alias is None:
                            alias = entities.setdefault("alias", {})
                        alias[tmp["name"]] = tmp

                    tmp = {}
                    stack = []

    @staticmethod
    def _load_minecart_enum(classloader, classname, minecart_info):
        """Stores data about the minecart enum in aggregate"""
        minecart_info["class"] = classname

        minecart_types = minecart_info.setdefault("types", {})
        minecart_types_by_field = minecart_info.setdefault("types_by_field", {})

        minecart_cf = classloader[classname]
        init_method = minecart_cf.methods.find_one(name="<clinit>")

        already_has_minecart_name = False
        for ins in init_method.code.disassemble():
            if ins == "new":
                const = ins.operands[0]
                minecart_class = const.name.value
            elif ins == "ldc":
                const = ins.operands[0]
                if isinstance(const, String):
                    if already_has_minecart_name:
                        minecart_type = const.string.value
                    else:
                        already_has_minecart_name = True
                        minecart_name = const.string.value
            elif ins == "putstatic":
                const = ins.operands[0]
                if const.name_and_type.descriptor.value != "L" + classname + ";":
                    # Other parts of the enum initializer (values array) that we don't care about
                    continue

                minecart_field = const.name_and_type.name.value

                minecart_types[minecart_name] = {
                    "class": minecart_class,
                    "field": minecart_field,
                    "name": minecart_name,
                    "entitytype": minecart_type
                }
                minecart_types_by_field[minecart_field] = minecart_name

                already_has_minecart_name = False

    @staticmethod
    def size(cf):
        method = cf.methods.find_one(name="<init>")
        if method is None:
            return

        stage = 0
        tmp = []
        texture = None
        for ins in method.code.disassemble():
            if ins == "aload" and ins.operands[0].value == 0 and stage == 0:
                stage = 1
            elif ins in ("ldc", "ldc_w"):
                const = ins.operands[0]
                if isinstance(const, Float) and stage in (1, 2):
                    tmp.append(round(const.value, 2))
                    stage += 1
                else:
                    stage = 0
                    tmp = []
                    if isinstance(const, String):
                        texture = const.string.value
            elif ins == "invokevirtual" and stage == 3:
                return tmp + [texture]
                break
            else:
                stage = 0
                tmp = []
