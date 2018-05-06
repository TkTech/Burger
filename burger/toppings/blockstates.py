#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.constants import *
from jawa.util.descriptor import method_descriptor, field_descriptor
from jawa.transforms.simple_swap import simple_swap

import traceback
import six
import six.moves

# EnumFacing.Plane.  Needed because this is also a predicate, which is used
# to get certain facings
class Plane:
    def __init__(self, directions):
        self.directions = directions
HORIZONTAL = Plane(["NORTH", "EAST", "SOUTH", "WEST"])
VERTICAL = Plane(["UP", "DOWN"])
PLANES = { "HORIZONTAL": HORIZONTAL, "VERTICAL": VERTICAL }

# Classes that represent predicates in various versions
PREDICATE_CLASSES = ("com/google/common/base/Predicate", "java/util/function/Predicate")

class BlockStateTopping(Topping):
    """Gets tile entity (block entity) types."""

    PROVIDES = [
        "blocks.states"
    ]

    DEPENDS = [
        "blocks",
        "version.is_flattened",
        "identify.blockstatecontainer",
        "identify.sounds.list",
        "identify.enumfacing.plane"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        if "blockstatecontainer" not in aggregate["classes"]:
            if verbose:
                print("blockstatecontainer not found; skipping blockstates")
            return

        is_flattened = aggregate["version"]["is_flattened"]

        blockstatecontainer = aggregate["classes"]["blockstatecontainer"]
        block_cf = classloader.load(aggregate["classes"]["block.superclass"] + ".class")
        plane = aggregate["classes"]["enumfacing.plane"]

        base_method = block_cf.methods.find_one(returns="L" + blockstatecontainer + ";", f=lambda m: m.access_flags.acc_protected)
        def matches(other_method):
            return (other_method.name.value == base_method.name.value and
                    other_method.descriptor.value == base_method.descriptor.value)

        _property_types = set()
        # Properties that are used by each block class
        properties_by_class = {}
        def process_class(name):
            """
            Gets the properties for the given block class, checking the parent
            class if none are defined.  Returns the properties, and also adds
            them to properties_by_class
            """
            if name in properties_by_class:
                # Caching - avoid reading the same class multiple times
                return properties_by_class[name]

            cf = classloader.load(name + ".class")
            method = cf.methods.find_one(f=matches)

            if not method:
                properties = process_class(cf.super_.name.value)
                properties_by_class[name] = properties
                return properties

            properties = None
            if_pos = None
            stack = []
            for ins in method.code.disassemble(transforms=[simple_swap]):
                # This could _almost_ just be checking for getstatic, but
                # brewing stands use an array of properties as the field,
                # so we need some stupid extra logic.
                if ins.mnemonic == "new":
                    const = cf.constants.get(ins.operands[0].value)
                    type_name = const.name.value
                    assert type_name == blockstatecontainer
                    stack.append(object())
                elif ins.mnemonic in ("sipush", "bipush"):
                    stack.append(ins.operands[0].value)
                elif ins.mnemonic in ("anewarray", "newarray"):
                    length = stack.pop()
                    val = [None] * length
                    stack.append(val)
                elif ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    prop = {
                        "field_name": const.name_and_type.name.value
                    }
                    desc = field_descriptor(const.name_and_type.descriptor.value)
                    _property_types.add(desc.name)
                    stack.append(prop)
                elif ins.mnemonic == "aaload":
                    index = stack.pop()
                    array = stack.pop()
                    prop = array.copy()
                    prop["array_index"] = index
                    stack.append(prop)
                elif ins.mnemonic == "aastore":
                    value = stack.pop()
                    index = stack.pop()
                    array = stack.pop()
                    array[index] = value
                elif ins.mnemonic == "dup":
                    stack.append(stack[-1])
                elif ins.mnemonic == "invokespecial":
                    const = cf.constants.get(ins.operands[0].value)
                    assert const.name_and_type.name.value == "<init>"
                    desc = method_descriptor(const.name_and_type.descriptor.value)
                    assert len(desc.args) == 2

                    # Normally this constructor call would return nothing, but
                    # in this case we'd rather remove the object it's called on
                    # and keep the properties array (its parameter)
                    arg = stack.pop()
                    stack.pop() # Block
                    stack.pop() # Invocation target
                    stack.append(arg)
                elif ins.mnemonic == "invokevirtual":
                    # Two possibilities (both only present pre-flattening):
                    # 1. It's isDouble() for a slab.  Two different sets of
                    #    properties in that case.
                    # 2. It's getTypeProperty() for flowers.  Only one
                    #    set of properties, but other hacking is needed.
                    # We can differentiate these cases based off of the return
                    # type.
                    const = cf.constants.get(ins.operands[0].value)
                    desc = method_descriptor(const.name_and_type.descriptor.value)

                    stack.pop()

                    if desc.returns.name == "boolean":
                        properties = [None, None]
                    else:
                        # Assume that the return type is the base interface
                        # for properties
                        stack.append(None)
                elif ins.mnemonic == "ifeq":
                    assert if_pos is None
                    if_pos = ins.pos + ins.operands[0].value
                elif ins.mnemonic == "areturn":
                    if if_pos == None:
                        assert properties == None
                        properties = stack.pop()
                    else:
                        assert isinstance(properties, list)
                        index = 0 if ins.pos < if_pos else 1
                        assert properties[index] == None
                        properties[index] = stack.pop()
                elif ins.mnemonic == "aload":
                    assert ins.operands[0].value == 0 # Should be aload_0 (this)
                    stack.append(object())
                elif verbose:
                    print("%s createBlockState contains unimplemented ins %s" % (name, ins))

            properties_by_class[name] = properties
            return properties

        for block in six.itervalues(aggregate["blocks"]["block"]):
            cls = block["class"]
            try:
                process_class(cls)
            except:
                if verbose:
                    print("Failed to process properties for %s (for %s)" % (cls, block["text_id"]))
                    traceback.print_exc()
                properties_by_class[cls] = []

        assert len(_property_types) == 4
        property_types = {}
        for type in _property_types:
            cf = classloader.load(type + ".class")
            if cf.super_.name.value in _property_types:
                property_types[type] = "direction"
            else:
                attribute = cf.attributes.find_one(name='Signature')
                signature = attribute.signature.value
                # Somewhat ugly behavior until an actual parser is added for these
                if "Enum" in signature:
                    property_types[type] = "enum"
                elif "Integer" in signature:
                    property_types[type] = "int"
                elif "Boolean" in signature:
                    property_types[type] = "bool"
                elif verbose:
                    print("Unknown property type %s with signature %s" % (type, signature))

        is_enum_cache = {}
        def is_enum(cls):
            """
            Checks if the given class is an enum.
            This needs to be recursive due to inner classes for enums.
            """
            if cls in is_enum_cache:
                return is_enum_cache[cls]

            cf = classloader.load(cls + ".class")
            super = cf.super_.name.value
            if super == "java/lang/Enum":
                is_enum_cache[cls] = True
            elif super == "java/lang/Object":
                is_enum_cache[cls] = False
            else:
                is_enum_cache[cls] = is_enum(super)

            return is_enum_cache[cls]

        fields_by_class = {}

        def find_field(cls, field_name):
            """
            cls: name of the class
            field_name: name of the field to find.  If None, returns all fields
            """
            if cls in fields_by_class:
                if field_name is not None:
                    if field_name not in fields_by_class[cls] and verbose:
                        print("Requested field %s.%s but that wasn't found last time" % (cls, field_name))
                    return fields_by_class[cls][field_name]
                else:
                    return fields_by_class[cls]
            elif cls == aggregate["classes"]["sounds.list"]:
                # Another scary case.  We don't want to parse all of the sound events.
                return object()

            cf = classloader.load(cls + ".class")

            fields_by_class[cls] = {}
            super_name = cf.super_.name.value
            if not super_name.startswith("java/lang"):
                # Add fields from superclass
                fields_by_class[cls].update(find_field(super_name, None))

            init = cf.methods.find_one(name="<clinit>")
            if not init:
                if field_name is not None:
                    return fields_by_class[cls][field_name]
                else:
                    return fields_by_class[cls]

            stack = []
            locals = {}
            # After certain calls, we're no longer storing properties.
            # But, we still want to assign values for remaining fields;
            # go through and put None in, only looking at putstatic.
            ignore_remaining = False

            for ins in init.code.disassemble(transforms=[simple_swap]):
                if ins.mnemonic == "putstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    name = const.name_and_type.name.value
                    if ignore_remaining:
                        value = None
                    else:
                        value = stack.pop()

                    if isinstance(value, dict):
                        if "declared_in" not in value:
                            # If there's already a declared_in, this is a field
                            # loaded with getstatic, and we don't want to change
                            # the true location of it
                            value["declared_in"] = cls
                        if value["class"] == plane:
                            # Convert to an instance of Plane
                            # Now is the easiest time to do this, and for
                            # Plane itself it doesn't matter since it's never
                            # used on the stack
                            assert "enum_name" in value
                            assert value["enum_name"] in PLANES
                            value = PLANES[value["enum_name"]]
                    fields_by_class[cls][name] = value
                elif ignore_remaining:
                    continue
                elif ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    target = const.class_.name.value
                    type = field_descriptor(const.name_and_type.descriptor.value).name
                    name = const.name_and_type.name.value
                    if not target.startswith("java/"):
                        stack.append(find_field(target, name))
                    else:
                        stack.append(object())
                elif ins.mnemonic in ("ldc", "ldc_w", "ldc2_w"):
                    const = cf.constants.get(ins.operands[0].value)

                    if isinstance(const, ConstantClass):
                        stack.append("%s.class" % const.name.value)
                    elif isinstance(const, String):
                        stack.append(const.string.value)
                    else:
                        stack.append(const.value)
                elif ins.mnemonic.startswith("dconst"):
                    stack.append(float(ins.mnemonic[-1]))
                elif ins.mnemonic in ("bipush", "sipush"):
                    stack.append(ins.operands[0].value)
                elif ins.mnemonic == "aconst_null":
                    stack.append(None)
                elif ins.mnemonic in ("anewarray", "newarray"):
                    length = stack.pop()
                    stack.append([None] * length)
                elif ins.mnemonic in ("aaload", "iaload"):
                    index = stack.pop()
                    array = stack.pop()
                    prop = array[index].copy()
                    prop["array_index"] = index
                    stack.append(prop)
                elif ins.mnemonic in ("aastore", "iastore"):
                    value = stack.pop()
                    index = stack.pop()
                    array = stack.pop()
                    array[index] = value
                elif ins.mnemonic == "arraylength":
                    array = stack.pop()
                    stack.append(len(array))
                elif ins.mnemonic == "dup":
                    stack.append(stack[-1])
                elif ins.mnemonic == "invokedynamic":
                    # Try to get the class that's being created
                    const = cf.constants.get(ins.operands[0].value)
                    desc = method_descriptor(const.name_and_type.descriptor.value)
                    stack.append({"dynamic_class": desc.returns.name, "class": cls})
                elif ins.mnemonic.startswith("invoke"):
                    const = cf.constants.get(ins.operands[0].value)
                    desc = method_descriptor(const.name_and_type.descriptor.value)
                    num_args = len(desc.args)
                    args = [stack.pop() for _ in six.moves.range(num_args)]
                    args.reverse()

                    if ins.mnemonic == "invokestatic":
                        if const.class_.name.value.startswith("com/google/"):
                            # Call to e.g. Maps.newHashMap, beyond what we
                            # care about
                            ignore_remaining = True
                            continue
                        obj = None
                    else:
                        obj = stack.pop()

                    if desc.returns.name in property_types:
                        prop = {
                            "class": desc.returns.name,
                            "type": property_types[desc.returns.name],
                            "args": args
                        }
                        stack.append(prop)
                    elif const.name_and_type.name.value == "<init>":
                        if obj["is_enum"]:
                            obj["enum_name"] = args[0]
                            obj["enum_ordinal"] = args[1]
                        else:
                            obj["args"] = args
                    elif const.name_and_type.name.value == "values":
                        # Enum values
                        fields = find_field(const.class_.name.value, None)
                        stack.append([fld for fld in fields
                                      if isinstance(fld, dict) and fld["is_enum"]])
                    elif desc.returns.name != "void":
                        if isinstance(obj, Plane):
                            # One special case, where EnumFacing.Plane is used
                            # to get a list of directions
                            stack.append(obj.directions)
                        elif (isinstance(obj, dict) and obj["is_enum"] and
                                desc.returns.name == "int"):
                            # Assume it's the enum ordinal, even if it really
                            # isn't
                            stack.append(obj["enum_ordinal"])
                        else:
                            o = object()
                            stack.append(o)
                elif ins.mnemonic in ("istore", "lstore", "fstore", "dstore", "astore"):
                    # Store other than array store
                    locals[ins.operands[0].value] = stack.pop()
                elif ins.mnemonic in ("iload", "lload", "fload", "dload", "aload"):
                    # Load other than array load
                    stack.append(locals[ins.operands[0].value])
                elif ins.mnemonic == "new":
                    const = cf.constants.get(ins.operands[0].value)
                    type_name = const.name.value
                    obj = {
                        "class": type_name,
                        "is_enum": is_enum(type_name)
                    }
                    stack.append(obj)
                elif ins.mnemonic == "checkcast":
                    # We don't have type information, so no checking or casting
                    pass
                elif ins.mnemonic == "return":
                    break
                elif ins.mnemonic == "if_icmpge":
                    # Code in stairs that loops over state combinations for hitboxes
                    break
                elif verbose:
                    print("%s initializer contains unimplemented ins %s" % (cls, ins))

            if field_name is not None:
                return fields_by_class[cls][field_name]
            else:
                return fields_by_class[cls]

        # Property handlers.
        def base_handle_property(prop):
            field = prop["field"]
            args = field["args"]
            assert len(args) >= 1
            assert isinstance(args[0], six.string_types)
            ret = {
                "type": field["type"],
                "name": args[0],
                "field_name": prop["field_name"]
            }
            if "array_index" in prop:
                ret["array_index"] = prop["array_index"]
            else:
                # Unfortunately we don't have a declared_in field for arrays at this time
                ret["declared_in"] = field["declared_in"]
            return ret

        def handle_boolean_property(prop):
            ret = base_handle_property(prop)

            assert len(prop["field"]["args"]) == 1
            ret["num_values"] = 2
            return ret

        def handle_int_property(prop):
            ret = base_handle_property(prop)

            args = prop["field"]["args"]
            assert len(args) == 3
            assert isinstance(args[1], int)
            assert isinstance(args[2], int)

            ret["num_values"] = args[2] - args[1] + 1
            ret["min"] = args[1]
            ret["max"] = args[2]
            return ret

        def handle_enum_property(prop):
            ret = base_handle_property(prop)

            args = prop["field"]["args"]
            assert len(args) in (2, 3)
            assert isinstance(args[1], six.string_types)
            assert args[1].endswith(".class") # Should be a class
            class_name = args[1][:-len(".class")]

            ret["enum_class"] = class_name
            if len(args) == 2:
                values = [c["enum_name"] for c
                          in six.itervalues(find_field(class_name, None))
                          if isinstance(c, dict) and c["is_enum"]]
            elif isinstance(args[2], list):
                values = [c["enum_name"] for c in args[2]]
            elif isinstance(args[2], dict):
                # Possibly a predicate (used for powered and activator rails)
                if "dynamic_class" in args[2]:
                    predicate_type = args[2]["dynamic_class"]
                    predicate_class = args[2]["dynamic_class"]
                else:
                    cf = classloader.load(args[2]["class"] + ".class")
                    if len(cf.interfaces) == 1:
                        predicate_type = cf.interfaces[0].name.value
                        predicate_class = args[2]["class"]

                if predicate_type in PREDICATE_CLASSES:
                    ret["predicate"] = predicate_class
                    # Will be trimmed later
                    values = [c["enum_name"] for c
                          in six.itervalues(find_field(class_name, None))
                          if isinstance(c, dict) and c["is_enum"]]
                elif verbose:
                    print("Unhandled args for %s" % prop)
                    values = []
            else:
                # Regular Collection (unused)
                if verbose:
                    print("Unhandled args for %s" % prop)
                values = []
            ret["values"] = values
            ret["num_values"] = len(values)
            return ret

        def handle_direction_property(prop):
            ret = base_handle_property(prop)

            args = prop["field"]["args"]
            assert len(args) in (1, 2)
            if len(args) == 1:
                # No restrictions
                values = ["DOWN", "UP", "NORTH", "SOUTH", "EAST", "WEST"]
            elif isinstance(args[1], list):
                if isinstance(args[1][0], str):
                    # A Plane's facings
                    values = args[1]
                else:
                    # Fields
                    values = [c["enum_name"] for c in args[1]]
            elif isinstance(args[1], Plane):
                # Plane used as a predicate
                values = args[1].directions
            elif isinstance(args[1], dict):
                # Possibly a predicate (used for hoppers)
                if "dynamic_class" in args[1]:
                    predicate_type = args[1]["dynamic_class"]
                    predicate_class = args[1]["dynamic_class"]
                else:
                    cf = classloader.load(args[1]["class"] + ".class")
                    if len(cf.interfaces) == 1:
                        predicate_type = cf.interfaces[0].name.value
                        predicate_class = args[1]["class"]

                if predicate_type in PREDICATE_CLASSES:
                    ret["predicate"] = predicate_class
                    # Will be filled in later
                    values = ["DOWN", "UP", "NORTH", "SOUTH", "EAST", "WEST"]
                elif verbose:
                    print("Unhandled args for %s" % prop)
                    values = []
            else:
                # Regular Collection (unused)
                if verbose:
                    print("Unhandled args for %s" % prop)
                values = []
            ret["values"] = values
            ret["num_values"] = len(values)
            return ret

        property_handlers = {
            'bool': handle_boolean_property,
            'int': handle_int_property,
            'enum': handle_enum_property,
            'direction': handle_direction_property
        }

        def process_property(property):
            field_name = property["field_name"]
            try:
                field = find_field(cls, field_name)
                if "array_index" in property:
                    field = field[property["array_index"]]
                property["field"] = field

                property["data"] = property_handlers[field["type"]](property)
            except:
                if verbose:
                    print("Failed to handle property %s (declared %s.%s)" % (property, cls, field_name))
                    traceback.print_exc()
                property["data"] = None

        for cls, properties in six.iteritems(properties_by_class):
            for property in properties:
                if isinstance(property, dict):
                    process_property(property)
                elif isinstance(property, list):
                    # Slabs
                    for real_property in property:
                        process_property(real_property)
                elif property == None:
                    # Manual handling
                    pass
                elif verbose:
                    print("Skipping odd property %s (declared in %s)" % (property, cls))

        state_id = 0
        for block_id in aggregate["blocks"]["ordered_blocks"]:
            block = aggregate["blocks"]["block"][block_id]
            block["num_states"] = 1
            properties = properties_by_class[block["class"]]
            if len(properties) != 0 and isinstance(properties[0], list) and "slab" in block_id:
                # Convert the double-list of properties for slabs to just 1
                if "double" in block["text_id"]:
                    properties = properties[1]
                else:
                    properties = properties[1]
            block["states"] = []
            for prop in properties:
                if prop == None:
                    # Manually handle a few properties
                    if block_id == "yellow_flower":
                        prop = { "data": {
                            "type": "enum",
                            "name": "type",
                            # no field_name
                            # no enum_class
                            "values": ["DANDELION"],
                            "num_values": 1
                        }}
                    elif block_id == "red_flower":
                        prop = { "data": {
                            "type": "enum",
                            "name": "type",
                            # no field_name
                            # no enum_class
                            "values": ["POPPY", "BLUE_ORCHID", "ALLIUM", "HOUSTONIA", "RED_TULIP", "ORANGE_TULIP", "WHITE_TULIP", "PINK_TULIP", "OXEYE_DAISY"],
                            "num_values": 9
                        }}
                    else:
                        if verbose:
                            print("Skipping missing prop for %s" % block_id)
                        continue

                if not isinstance(prop, dict) or not isinstance(prop["data"], dict):
                    if verbose:
                        print("Skipping bad prop %s for %s" % (prop, block_id))
                    continue
                if "predicate" in prop["data"]:
                    data = prop["data"].copy()
                    # Fun times... guess what the predicate does,
                    # based off of the block
                    if block_id == "hopper":
                        predicate = lambda v: v != "UP"
                    elif block_id in ("powered_rail", "activator_rail", "golden_rail", "detector_rail"):
                        predicate = lambda v: v not in ("NORTH_EAST", "NORTH_WEST", "SOUTH_EAST", "SOUTH_WEST")
                    elif prop["field"]["declared_in"] == aggregate["blocks"]["block"]["torch"]["class"]:
                        # Pre-flattening
                        predicate = lambda v: v != "DOWN"
                    elif block_id == "leaves" or block_id == "log":
                        predicate = lambda v: v in ("OAK", "BIRCH", "SPRUCE", "JUNGLE")
                    elif block_id == "leaves2" or block_id == "log2":
                        predicate = lambda v: v in ("DARK_OAK", "ACACIA")
                    else:
                        if verbose:
                            print("Unhandled predicate for prop %s for %s" % (prop, block_id))
                        predicate = lambda v: False

                    data["values"] = [v for v in data["values"] if predicate(v)]
                    data["num_values"] = len(data["values"])
                else:
                    data = prop["data"]

                block["states"].append(data)
                block["num_states"] *= data["num_values"]

            if not is_flattened:
                # Each block is allocated 16 states for metadata pre-flattening
                block["num_states"] = 16
            block["min_state_id"] = state_id
            state_id += block["num_states"]
            block["max_state_id"] = state_id - 1