#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile
from jawa.util.descriptor import method_descriptor, field_descriptor

import traceback

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class BlockStateTopping(Topping):
    """Gets tile entity (block entity) types."""

    PROVIDES = [
        "blocks.states"
    ]

    DEPENDS = [
        "blocks",
        "version.data",
        "identify.blockstatecontainer",
        "identify.sounds.list"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        if "blockstatecontainer" not in aggregate["classes"]:
            if verbose:
                print "blockstatecontainer not found; skipping blockstates"
            return

        # 1449 is 17w46a
        is_flattened = ("data" in aggregate["version"] and aggregate["version"]["data"] > 1449)

        blockstatecontainer = aggregate["classes"]["blockstatecontainer"]
        block_cf = ClassFile(StringIO(jar.read(aggregate["classes"]["block.superclass"] + ".class")))
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

            cf = ClassFile(StringIO(jar.read(name + ".class")))
            method = cf.methods.find_one(f=matches)

            if not method:
                properties = process_class(cf.super_.name.value)
                properties_by_class[name] = properties
                return properties

            properties = None
            stack = []
            for ins in method.code.disassemble():
                # This could _almost_ just be checking for getstatic, but
                # brewing stands use an array of properties as the field,
                # so we need some stupid extra logic.
                if ins.mnemonic == "new":
                    const = cf.constants.get(ins.operands[0].value)
                    type_name = const.name.value
                    assert type_name == blockstatecontainer
                    stack.append(object())
                elif ins.mnemonic.startswith("iconst"):
                    stack.append(int(ins.mnemonic[-1]))
                elif ins.mnemonic.endswith("ipush"):
                    stack.append(ins.operands[0].value)
                elif ins.mnemonic == "anewarray":
                    len = stack.pop()
                    val = [None] * len
                    if not properties:
                        properties = val
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
                    break

            properties_by_class[name] = properties
            return properties

        for block in aggregate["blocks"]["block"].itervalues():
            process_class(block["class"])

        assert len(_property_types) == 4
        property_types = {}
        for type in _property_types:
            cf = ClassFile(StringIO(jar.read(type + ".class")))
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
                    print "Unknown property type %s with signature %s" % (type, signature)

        fields_by_class = {}
        ignore_scary_lambda_marker = object()
        def find_field(cls, field_name):
            """
            cls: name of the class
            field_name: name of the field to find.  If None, returns all fields
            """
            if cls in fields_by_class:
                if fields_by_class[cls] == ignore_scary_lambda_marker:
                    return object()
                elif field_name is not None:
                    return fields_by_class[cls][field_name]
                else:
                    return fields_by_class[cls]
            elif cls == aggregate["classes"]["sounds.list"]:
                # Another scary case.  We don't want to parse all of the sound events.
                return object()

            cf = ClassFile(StringIO(jar.read(cls + ".class")))

            if cf.attributes.find_one("BootstrapMethods"):
                # AAAH LAMBDAS
                fields_by_class[cls] = ignore_scary_lambda_marker
                return object()

            fields_by_class[cls] = {}
            super_name = cf.super_.name.value
            if not super_name.startswith("java/lang"):
                # Add fields from superclass
                fields_by_class[cls].update(find_field(super_name, None))

            init = cf.methods.find_one("<clinit>")
            if not init:
                if field_name is not None:
                    return fields_by_class[cls][field_name]
                else:
                    return fields_by_class[cls]

            stack = []
            for ins in init.code.disassemble():
                if ins.mnemonic == "putstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    name = const.name_and_type.name.value
                    value = stack.pop()

                    if isinstance(value, dict):
                        value["declared_in"] = cls
                    fields_by_class[cls][name] = value
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
                    elif isinstance(const, ConstantString):
                        stack.append(const.string.value)
                    else:
                        stack.append(const.value)
                elif ins.mnemonic.startswith("iconst"):
                    stack.append(int(ins.mnemonic[-1]))
                elif ins.mnemonic.startswith("dconst"):
                    stack.append(float(ins.mnemonic[-1]))
                elif ins.mnemonic.endswith("ipush"):
                    stack.append(ins.operands[0].value)
                elif ins.mnemonic == "anewarray":
                    length = stack.pop()
                    stack.append([None] * length)
                elif ins.mnemonic == "aastore":
                    value = stack.pop()
                    index = stack.pop()
                    array = stack.pop()
                    array[index] = value
                elif ins.mnemonic == "dup":
                    stack.append(stack[-1])
                elif ins.mnemonic.startswith("invoke"):
                    const = cf.constants.get(ins.operands[0].value)
                    desc = method_descriptor(const.name_and_type.descriptor.value)
                    num_args = len(desc.args)
                    args = [stack.pop() for _ in xrange(num_args)]
                    args.reverse()

                    if ins.mnemonic == "invokestatic":
                        if const.class_.name.value.startswith("com/google/"):
                            # Call to e.g. Maps.newHashMap, beyond what we
                            # care about
                            break
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
                        else:
                            obj["args"] = args
                    elif desc.returns.name != "void":
                        if isinstance(obj, dict) and obj["class"] == plane:
                            # One special case, where EnumFacing.Plane is used
                            # to get a list of directions
                            assert obj["enum_name"] in ("HORIZONTAL", "VERTICAL")
                            if obj["enum_name"] == "HORIZONTAL":
                                stack.append(["NORTH", "EAST", "SOUTH", "WEST"])
                            else:
                                stack.append(["UP", "DOWN"])
                        else:
                            stack.append(object())
                elif ins.mnemonic == "new":
                    const = cf.constants.get(ins.operands[0].value)
                    type_name = const.name.value
                    tcf = ClassFile(StringIO(jar.read(type_name + ".class")))
                    obj = {
                        "class": type_name,
                        "is_enum": tcf.super_.name.value == "java/lang/Enum"
                    }
                    stack.append(obj)
                elif ins.mnemonic == "return":
                    break
                elif ins.mnemonic == "if_icmpge":
                    # Code in stairs that loops over state combinations for hitboxes
                    break

            if field_name is not None:
                return fields_by_class[cls][field_name]
            else:
                return fields_by_class[cls]

        # Property handlers.
        def base_handle_property(prop):
            field = prop["field"]
            args = field["args"]
            assert len(args) >= 1
            assert isinstance(args[0], basestring)
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
            assert isinstance(args[1], basestring)
            assert args[1].endswith(".class") # Should be a class
            class_name = args[1][:-len(".class")]

            ret["enum_class"] = class_name
            if len(args) == 2:
                values = [c["enum_name"] for c
                          in find_field(class_name, None).itervalues()
                          if isinstance(c, dict) and c["is_enum"]]
            elif isinstance(args[2], list):
                values = args[2]
            else:
                # Predicate (used for rails) or regular Collection (unused)
                if verbose:
                    print "Unhandled args for %s" % args
                values = []
            ret["values"] = values
            ret["num_values"] = len(values)
            return ret

        def handle_direction_property(prop):
            ret = base_handle_property(prop)

            args = prop["field"]["args"]
            assert len(args) == 2
            if isinstance(args[1], list):
                if isinstance(args[1][0], str):
                    # A Plane's facings
                    values = args[1]
                else:
                    # Fields
                    values = [c["enum_name"] for c in args[1]]
            else:
                # Predicate (used for hoppers) or regular Collection (unused)
                if verbose:
                    print "Unhandled args for %s" % args
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

        for cls, properties in properties_by_class.iteritems():
            for property in properties:
                field_name = property["field_name"]
                try:
                    field = find_field(cls, field_name)
                    if "array_index" in property:
                        field = field[property["array_index"]]
                    property["field"] = field

                    property["data"] = property_handlers[field["type"]](property)
                except:
                    if verbose:
                        print "Failed to handle property %s (declared %s.%s)" % (property, cls, field_name)
                        traceback.print_exc()
                    property["data"] = None

        for block in aggregate["blocks"]["block"].itervalues():
            proprties = properties_by_class[block["class"]]
            block["states"] = [prop["data"] for prop in proprties]
