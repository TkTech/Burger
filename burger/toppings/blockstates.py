#!/usr/bin/env python
# -*- coding: utf8 -*-

from .topping import Topping

from jawa.util.descriptor import field_descriptor
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class IntProperty:
    @staticmethod
    def create(method, stack):
        max = stack.pop()
        min = stack.pop()
        name = stack.pop()
        return IntProperty(name, min, max)

    def __init__(self, name, min, max):
        self.name = name
        self.min = min
        self.max = max

    @property
    def valid_values():
        return range(min, max + 1)

class BoolProperty:
    @staticmethod
    def create(method, stack):
        name = stack.pop()
        return BoolProperty(name)

    def __init__(self, name):
        self.name = name

    @property
    def valid_values():
        return [True, False]

class EnumProperty:
    @staticmethod
    def create(method, stack):
        name = stack.pop()
        return BoolProperty(name)

    

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

        base_method = block_cf.methods.find_one(returns="L" + blockstatecontainer + ";", f=lambda m: m.access_flags.acc_protected)
        print blockstatecontainer
        print base_method, vars(base_method)
        def matches(other_method):
            return (other_method.name.value == base_method.name.value and
                    other_method.descriptor.value == base_method.descriptor.value)

        _property_types = set()
        # Properties that are used by each block class
        properties_by_class = {}
        # Properties that are declared in each block class
        #properties_in_class = {}
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
        for cls, properties in properties_by_class.iteritems():
            cf = ClassFile(StringIO(jar.read(cls + ".class")))
            # TODO: Optimize this - less class loading!
            for property in properties:
                field_name = property["field_name"]
                work_cf = cf
                while not work_cf.fields.find_one(field_name):
                    work_cf = ClassFile(StringIO(jar.read(work_cf.super_.name.value + ".class")))
                init = work_cf.methods.find_one("<clinit>")
                for ins in init.code.disassemble:
                    

        raise Exception()
