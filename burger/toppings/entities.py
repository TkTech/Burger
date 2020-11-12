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
from burger.util import WalkerCallback, class_from_invokedynamic, walk_method

from jawa.constants import *
from jawa.util.descriptor import method_descriptor

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

        entities["info"] = {
            "entity_count": len(entities["entity"])
        }

        EntityTopping.abstract_entities(classloader, entities["entity"], verbose)
        EntityTopping.compute_sizes(classloader, aggregate, entities["entity"])

    @staticmethod
    def _entities_1point13(aggregate, classloader, verbose):
        if verbose:
            print("Using 1.13 entity format")

        listclass = aggregate["classes"]["entity.list"]
        cf = classloader[listclass]

        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})

        # Find the inner builder class
        inner_classes = cf.attributes.find_one(name="InnerClasses").inner_classes
        builderclass = None
        funcclass = None # 19w08a+ - a functional interface for creating new entities
        for entry in inner_classes:
            if entry.outer_class_info_index == 0:
                # Ignore anonymous classes
                continue

            outer = cf.constants.get(entry.outer_class_info_index)
            if outer.name == listclass:
                inner = cf.constants.get(entry.inner_class_info_index)
                inner_cf = classloader[inner.name.value]
                if inner_cf.access_flags.acc_interface:
                    if funcclass:
                        raise Exception("Unexpected multiple inner interfaces")
                    funcclass = inner.name.value
                else:
                    if builderclass:
                        raise Exception("Unexpected multiple inner classes")
                    builderclass = inner.name.value

        if not builderclass:
            raise Exception("Failed to find inner class for builder in " + str(inner_classes))
        # Note that funcclass might not be found since it didn't always exist

        method = cf.methods.find_one(name="<clinit>")

        # Example of what's being parsed:
        # public static final EntityType<EntityAreaEffectCloud> AREA_EFFECT_CLOUD = register("area_effect_cloud", EntityType.Builder.create(EntityAreaEffectCloud::new, EntityCategory.MISC).setSize(6.0F, 0.5F)); // 19w05a+
        # public static final EntityType<EntityAreaEffectCloud> AREA_EFFECT_CLOUD = register("area_effect_cloud", EntityType.Builder.create(EntityAreaEffectCloud.class, EntityAreaEffectCloud::new).setSize(6.0F, 0.5F)); // 19w03a+
        # and in older versions:
        # public static final EntityType<EntityAreaEffectCloud> AREA_EFFECT_CLOUD = register("area_effect_cloud", EntityType.Builder.create(EntityAreaEffectCloud.class, EntityAreaEffectCloud::new)); // 18w06a-19w02a
        # and in even older versions:
        # public static final EntityType<EntityAreaEffectCloud> AREA_EFFECT_CLOUD = register("area_effect_cloud", EntityType.Builder.create(EntityAreaEffectCloud::new)); // through 18w05a

        class EntityContext(WalkerCallback):
            def __init__(self):
                self.cur_id = 0

            def on_invokedynamic(self, ins, const, args):
                # MC uses EntityZombie::new, similar; return the created class
                return class_from_invokedynamic(ins, cf)

            def on_invoke(self, ins, const, obj, args):
                if const.class_.name == listclass:
                    assert len(args) == 2
                    # Call to register
                    name = args[0]
                    new_entity = args[1]
                    new_entity["name"] = name
                    new_entity["id"] = self.cur_id
                    if "minecraft." + name in aggregate["language"]["entity"]:
                        new_entity["display_name"] = aggregate["language"]["entity"]["minecraft." + name]
                    self.cur_id += 1

                    entity[name] = new_entity
                    return new_entity
                elif const.class_.name == builderclass:
                    if ins.mnemonic != "invokestatic":
                        if len(args) == 2 and const.name_and_type.descriptor.value.startswith("(FF)"):
                            # Entity size in 19w03a and newer
                            obj["width"] = args[0]
                            obj["height"] = args[1]

                        # There are other properties on the builder (related to whether the entity can be created)
                        # We don't care about these
                        return obj

                    method_desc = const.name_and_type.descriptor.value
                    desc = method_descriptor(method_desc)

                    if len(args) == 2:
                        if desc.args[0].name == "java/lang/Class" and desc.args[1].name == "java/util/function/Function":
                            # Builder.create(Class, Function), 18w06a+
                            # In 18w06a, they added a parameter for the entity class; check consistency
                            assert args[0] == args[1] + ".class"
                            cls = args[1]
                        elif desc.args[0].name == "java/util/function/Function" or desc.args[0].name == funcclass:
                            # Builder.create(Function, EntityCategory), 19w05a+
                            cls = args[0]
                        else:
                            if verbose:
                                print("Unknown entity type builder creation method", method_desc)
                            cls = None
                    elif len(args) == 1:
                        # There is also a format that creates an entity that cannot be serialized.
                        # This might be just with a single argument (its class), in 18w06a+.
                        # Otherwise, in 18w05a and below, it's just the function to build.
                        if desc.args[0].name == "java/lang/Function":
                            # Builder.create(Function), 18w05a-
                            # Just the function, which was converted into a class name earlier
                            cls = args[0]
                        elif desc.args[0].name == "java/lang/Class":
                            # Builder.create(Class), 18w06a+
                            # The type that represents something that cannot be serialized
                            cls = None
                        else:
                            # Assume Builder.create(EntityCategory) in 19w05a+,
                            # though it could be hit for other unknown signatures
                            cls = None
                    else:
                        # Assume Builder.create(), though this could be hit for other unknown signatures
                        # In 18w05a and below, nonserializable entities
                        cls = None

                    return { "class": cls } if cls else { "serializable": "false" }

            def on_put_field(self, ins, const, obj, value):
                if isinstance(value, dict):
                    # Keep track of the field in the entity list too.
                    value["field"] = const.name_and_type.name.value
                    # Also, if this isn't a serializable entity, get the class from the generic signature of the field
                    if "class" not in value:
                        field = cf.fields.find_one(name=const.name_and_type.name.value)
                        sig = field.attributes.find_one(name="Signature").signature.value # Something like `Laev<Laep;>;`
                        value["class"] = sig[sig.index("<") + 2 : sig.index(">") - 1] # Awful way of getting the actual type

            def on_new(self, ins, const):
                # Done once, for the registry, but we don't care
                return object()

            def on_get_field(self, ins, const, obj):
                # 19w05a+: used to set entity types.
                return object()

        walk_method(cf, method, EntityContext(), verbose)

    @staticmethod
    def _entities_1point11(aggregate, classloader, verbose):
        # 1.11 logic
        if verbose:
            print("Using 1.11 entity format")

        listclass = aggregate["classes"]["entity.list"]
        cf = classloader[listclass]

        entities = aggregate.setdefault("entities", {})
        entity = entities.setdefault("entity", {})

        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        minecart_info = {}
        class EntityContext(WalkerCallback):
            def on_get_field(self, ins, const, obj):
                # Minecarts use an enum for their data - assume that this is that enum
                const = ins.operands[0]
                if not "types_by_field" in minecart_info:
                    EntityTopping._load_minecart_enum(classloader, const.class_.name.value, minecart_info)
                minecart_name = minecart_info["types_by_field"][const.name_and_type.name.value]
                return minecart_info["types"][minecart_name]

            def on_invoke(self, ins, const, obj, args):
                if const.class_.name == listclass:
                    if len(args) == 4:
                        # Initial registration
                        name = args[1]
                        old_name = args[3]
                        entity[name] = {
                            "id": args[0],
                            "name": name,
                            "class": args[2][:-len(".class")],
                            "old_name": old_name
                        }

                        if old_name + ".name" in aggregate["language"]["entity"]:
                            entity[name]["display_name"] = aggregate["language"]["entity"][old_name + ".name"]
                    elif len(args) == 3:
                        # Spawn egg registration
                        name = args[0]
                        if name in entity:
                            entity[name]["egg_primary"] = args[1]
                            entity[name]["egg_secondary"] = args[2]
                        elif verbose:
                            print("Missing entity during egg registration: %s" % name)
                elif const.class_.name == minecart_info["class"]:
                    # Assume that obj is the minecart info, and the method being called is the one that gets the name
                    return obj["entitytype"]

            def on_new(self, ins, const):
                raise Exception("unexpected new: %s" % ins)

            def on_put_field(self, ins, const, obj, value):
                raise Exception("unexpected putfield: %s" % ins)

        walk_method(cf, method, EntityContext(), verbose)

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
    def compute_sizes(classloader, aggregate, entities):
        # Class -> size
        size_cache = {}

        # NOTE: Use aggregate["entities"] instead of the given entities list because
        # this method is re-used in the objects topping
        base_entity_cf = classloader[aggregate["entities"]["entity"]["~abstract_entity"]["class"]]

        # Note that there are additional methods matching this, used to set camera angle and such
        set_size = base_entity_cf.methods.find_one(args="FF", returns="V", f=lambda m: m.access_flags.acc_protected)

        set_size_name = set_size.name.value
        set_size_desc = set_size.descriptor.value

        def compute_size(class_name):
            if class_name == "java/lang/Object":
                return None

            if class_name in size_cache:
                return size_cache[class_name]

            cf = classloader[class_name]
            constructor = cf.methods.find_one(name="<init>")

            tmp = []
            for ins in constructor.code.disassemble():
                if ins in ("ldc", "ldc_w"):
                    const = ins.operands[0]
                    if isinstance(const, Float):
                        tmp.append(const.value)
                elif ins == "invokevirtual":
                    const = ins.operands[0]
                    if const.name_and_type.name == set_size_name and const.name_and_type.descriptor == set_size_desc:
                        if len(tmp) == 2:
                            result = tmp
                        else:
                            # There was a call to the method, but we couldn't parse it fully
                            result = None
                        break
                    tmp = []
                else:
                    # We want only the simplest parse, so even things like multiplication should cause this to be reset
                    tmp = []
            else:
                # No result, so use the superclass
                result = compute_size(cf.super_.name.value)

            size_cache[class_name] = result
            return result

        for entity in six.itervalues(entities):
            if "width" not in entity:
                size = compute_size(entity["class"])
                if size is not None:
                    entity["width"] = size[0]
                    entity["height"] = size[1]

    @staticmethod
    def abstract_entities(classloader, entities, verbose):
        entity_classes = {e["class"]: e["name"] for e in six.itervalues(entities)}

        # Add some abstract classes, to help with metadata, and for reference only;
        # these are not spawnable
        def abstract_entity(abstract_name, *subclass_names):
            for name in subclass_names:
                if name in entities:
                    cf = classloader[entities[name]["class"]]
                    parent = cf.super_.name.value
                    if parent not in entity_classes:
                        entities["~abstract_" + abstract_name] = { "class": parent, "name": "~abstract_" + abstract_name }
                    elif verbose:
                        print("Unexpected non-abstract class for parent of %s: %s" % (name, entity_classes[parent]))
                    break
            else:
                if verbose:
                    print("Failed to find abstract entity %s as a superclass of %s" % (abstract_name, subclass_names))

        abstract_entity("entity", "item", "Item")
        abstract_entity("minecart", "minecart", "MinecartRideable")
        abstract_entity("living", "armor_stand", "ArmorStand") # EntityLivingBase
        abstract_entity("insentient", "ender_dragon", "EnderDragon") # EntityLiving
        abstract_entity("monster", "enderman", "Enderman") # EntityMob
        abstract_entity("tameable", "wolf", "Wolf") # EntityTameable
        abstract_entity("animal", "sheep", "Sheep") # EntityAnimal
        abstract_entity("ageable", "~abstract_animal") # EntityAgeable
        abstract_entity("creature", "~abstract_ageable") # EntityCreature
