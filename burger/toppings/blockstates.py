#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile
from jawa.util.descriptor import method_descriptor, field_descriptor

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

# Planes
class Plane:
    def __init__(self, *args):
        self.values = args

HORIZONTAL = Plane('north', 'east', 'south', 'west')
VERTICAL = Plane('up', 'down')

class BlockStateTopping(Topping):
    """Gets tile entity (block entity) types."""

    PROVIDES = [
        "blocks.states"
    ]

    DEPENDS = [
        "blocks",
        "version.data",
        "identify.blockstatecontainer"
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
        print blockstatecontainer
        print base_method, vars(base_method)
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

            created_array = False
            properties = []
            for ins in method.code.disassemble():
                if ins.mnemonic == "anewarray":
                    created_array = True
                elif not created_array:
                    continue
                elif ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    prop = {
                        "field_name": const.name_and_type.name.value
                    }
                    desc = field_descriptor(const.name_and_type.descriptor.value)
                    _property_types.add(desc.name)
                    properties.append(prop)
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

        print property_types
        def find_field(cls, field_name):
            cf = ClassFile(StringIO(jar.read(cls + ".class")))
            if not cf.fields.find_one(field_name):
                return find_field(cf.super_.name.value, field_name)

            init = cf.methods.find_one("<clinit>")
            stack = []
            for ins in init.code.disassemble():
                if ins.mnemonic == "putstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    value = stack.pop()
                    if const.name_and_type.name.value == field_name:
                        return value
                elif ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    target = const.class_.name.value
                    type = field_descriptor(const.name_and_type.descriptor.value).name
                    name = const.name_and_type.name.value
                    cls2 = const.class_.name.value
                    if type in property_types:
                        stack.append(find_field(cls2, name))
                    elif type == plane:
                        # Assume 2 planes: HORIZONTAL (a) and VERTICAL (b)
                        assert name in ('a', 'b')
                        stack.append(HORIZONTAL if name == 'a' else VERTICAL)
                    else:
                        stack.append(find_field(target, name))
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
                        obj = None
                    else:
                        obj = stack.pop()

                    if desc.returns.name in property_types:
                        name = args[0]
                        prop = {
                            "name": name,
                            "class": desc.returns.name,
                            "type": property_types[desc.returns.name],
                            "args": args
                        }
                        stack.append(prop)
                    elif isinstance(obj, Plane):
                        stack.append(obj.values)
                    elif const.name_and_type.name.value == "<init>":
                        if obj["is_enum"]:
                            obj["enum_name"] = args[0]
                        else:
                            obj["args"] = args
                    elif desc.returns.name != "void":
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
                else:
                    print "Unhandled:", cls, ins

        for cls, properties in properties_by_class.iteritems():
            print cls
            # TODO: Optimize this - less class loading!
            for property in properties:
                field_name = property["field_name"]
                try:
                    print find_field(cls, field_name)
                except Exception as e:
                    print cls, property
                    print e

        raise Exception()
