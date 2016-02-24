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

import re
import sys
import traceback

from types import LambdaType

from jawa.util.descriptor import method_descriptor
from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from .topping import Topping

class PacketInstructionsTopping(Topping):
    """Provides the instructions used to construct network packets."""

    PROVIDES = [
        "packets.instructions",
        "packets.sizes"
    ]

    DEPENDS = [
        "packets.classes",
        "identify.packet.packetbuffer"
    ]

    TYPES = {
        "writeBoolean": "boolean",
        "writeByte": "byte",
        "writeBytes": "byte[]",
        "writeChar": "char",
        "writeChars": "string16",
        "writeDouble": "double",
        "writeFloat": "float",
        "writeInt": "int",
        "writeLong": "long",
        "writeShort": "short",
        "writeUTF": "string8"
    }

    SIZES = {
        "boolean": 1,
        "byte": 1,
        "char": 1,
        "double": 8,
        "float": 4,
        "int": 4,
        "long": 8,
        "short": 2
    }

    CONDITIONS = [
        "!=",
        "==",
        ">=",
        "<",
        "<=",
        ">"
    ]

    MATH = {
        0x60: "+",
        0x7e: "&",
        0x6e: "/",
        0x68: "*",
        0x80: "|",
        0x70: "%",
        0x78: "<<",
        0x7a: ">>",
        0x64: "-",
        0x82: "^"
    }

    CACHE = {}

    OPCODES = {
        0x30: (2, "{0}[{1}]"),                      # Taload
        0x4f: (3),                                  # Tastore
        0x94: (2, "compare({0}, {1})"),             # Tcmp<op>
        0xac: (1),                                  # Treturn
        0x36: (1),                                  # Tstore
        0x43: (1),                                  # Tstore_<n>
        0x01: (0, "null"),                          # aconst_null
        0x25: (0, "{1}"),                           # aload
        0x2a: (0, "{1}", lambda op: op - 0x2a),     # aload_<n>
        0xbd: (1, "new {1.class}[{0}]"),            # anewarray
        0xbe: (1, "{0}.length"),                    # arraylength
        0xbf: (1),                                  # athrow
        0x10: (0, "0x{0.value:x}"),                 # bipush
        0xc0: (1, "(({1.classname}){0})"),          # checkcast
        0x90: (1, "((double){0})", 2),              # d2f
        0x8e: (1, "((int){0})"),                    # d2i
        0x8f: (1, "((long){0}", 2),                 # d2l
        0x31: (2, "{0}[{1}]", 2),                   # daload
        0x0e: (0, "{0}.0", lambda op: op - 14),     # dconst_<d>
        0x18: (0, "{1}", 2),                        # dload
        0x26: (0, "{1}", lambda op: op - 0x26, 2),  # dload_<n>
        0x8d: (1, "((double){0})", 2),              # f2d
        0x8b: (1, "((int){0})"),                    # f2i
        0x8c: (1, "((long){0})", 2),                # f2l
        0x0b: (0, "{0}", lambda op: op - 11),       # fconst_<f>
        0x17: (0, "{1}"),                           # fload
        0x22: (0, "{1}", lambda op: op - 0x22),     # fload_<n>
        0xb4: (1, "{0}.{1.name}"),                  # getfield
        0xb2: (0, "{0.class}.{0.name}"),            # getstatic
        0x91: (1, "((byte){0})"),                   # i2b
        0x92: (1, "((chat){0})"),                   # i2c
        0x87: (1, "((double){0})", 2),              # i2d
        0x86: (1, "((float){0})"),                  # i2f
        0x85: (1, "((long){0})", 2),                # i2l
        0x93: (1, "((short){0})"),                  # i2s
        0x2e: (2, "{0}[{1}]"),                      # iaload
        0x02: (0, "{0}", lambda op: op - 3),        # iconst_<i>
        0x15: (0, "{1}"),                           # iload
        0x1a: (0, "{1}", lambda op: op - 0x1a),     # iload_<n>
        0xc1: (1, "({0} instanceof {1.class})"),    # instanceof
        0x8a: (1, "((double){0})", 2),              # l2d
        0x89: (1, "((float){0})"),                  # l2f
        0x88: (1, "((int){0})"),                    # l2i
        0x2f: (2, "{0}[{1}]", 2),                   # laload
        0x09: (0, "{0}", lambda op: op - 9),        # lconst_<l>
        0x12: (0, "{0.name}"),                      # ldc
        0x14: (0, "{0.name}", 2),                   # ldc2_w
        0x16: (0, "{1}", 2),                        # lload
        0x1e: (0, "{1}", lambda op: op - 0x1e, 2),  # lload_<n>
        0xc2: (0),                                  # monitorenter
        0xbb: (0, "new {0.class}"),                 # new
        0xbc: (1, "new {1.atype}[{0}]"),            # newarray
        0x00: (0),                                  # nop
        0x57: (1),                                  # pop
        0xb5: (2),                                  # putfield
        0xb3: (1),                                  # putstatic
        0xa9: (0),                                  # ret
        0xb1: (0),                                  # return
        0x35: (2, "{0}[{1}]", 2),                   # saload
        0x11: (0, "{0}"),                           # sipush
        0xc4: (0),                                  # wide

    }

    CLEANUP_PATTERN = [
        (re.compile("^\((.*)\)$"), "\\1"),
        (re.compile("(^|[() ])this\."), "\\1")
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        """Finds all packets and decompiles them"""
        for packet in aggregate["packets"]["packet"].values():
            try:
                packet.update(_PIT.format(
                    _PIT.operations(jar, packet["class"], aggregate["classes"]["packet.packetbuffer"])
                ))
            except Exception as e:
                if verbose:
                    print "Error: Failed to parse instructions",
                    print "of packet %s (%s): %s" % (packet["id"],
                                                     packet["class"], e)
                    traceback.print_exc()

    @staticmethod
    def operations(jar, classname, packetbuffer, args=None,
                   methodname=None, arg_names=("this", "stream")):
        """Gets the instructions of the specified method"""

        arg_names=("this", "packetbuffer")

        # Find the writing method
        cf = ClassFile(StringIO(jar.read(classname)))

        if methodname is None and args is None:
            methods = list(cf.methods.find(f=lambda x: len(x.args) == 1 and x.args[0].name == packetbuffer))

            if len(methods) == 2:
                method = methods[1]
            else:
                if cf.super_:
                    return _PIT.operations(jar, cf.super_.name + ".class", packetbuffer)
                else:
                    raise Exception("Failed to find method in class or superclass")
        elif methodname is None:
            method = cf.methods.find_one(args=args)
        else:
            method = cf.methods.find_one(name=methodname, args=args)


        # Decode the instructions
        operations = []
        stack = []
        skip_until = -1
        shortif_pos = -1
        shortif_cond = ''

        for instruction in method.code.disassemble():
            if skip_until != -1:
                if instruction.pos == skip_until:
                    skip_until = -1
                else:
                    continue

            opcode = instruction.opcode
            operands = [InstructionField(operand, instruction, cf.constants)
                        for operand in instruction.operands]

            # Shortcut if
            if instruction.pos == shortif_pos:
                category = stack[-1].category
                stack.append(Operand("((%(cond)s) ? %(sec)s : %(first)s)" % {
                    "cond": shortif_cond,
                    "first": stack.pop(),
                    "sec": stack.pop()
                }, category))

            # Method calls
            if opcode >= 0xb6 and opcode <= 0xb9:
                name = operands[0].name
                desc = operands[0].descriptor

                descriptor = method_descriptor(desc)
                num_arguments = len(descriptor.args)

                if name in _PIT.TYPES:
                    operations.append(Operation(instruction.pos, "write",
                                                type=_PIT.TYPES[name],
                                                field=stack.pop()))
                elif name == "write":
                    if desc.find("[BII") >= 0:
                        stack.pop()
                        stack.pop()
                    operations.append(Operation(
                        instruction.pos, "write",
                        type="byte[]" if desc.find("[B") >= 0 else "byte",
                        field=stack.pop()))
                    stack.pop()
                elif num_arguments == 1 and descriptor.args[0].name == "java/lang/String":
                    operations.append(Operation(instruction.pos, "write",
                                                type="string16",
                                                field=stack.pop()))
                elif num_arguments == 1 and descriptor.args[0].name == "java/util/UUID":
                    operations.append(Operation(instruction.pos, "write",
                                                type="uuid",
                                                field=stack.pop()))
                elif num_arguments == 1 and descriptor.args[0].name == "java/lang/Enum":
                    # If we were using the read method instead of the write method, then we could get the class for this enum...
                    operations.append(Operation(instruction.pos, "write",
                                                type="enum",
                                                field=stack.pop()))
                else:
                    print instruction, name, desc, descriptor, cf
                    if num_arguments > 0:
                        arguments = stack[-len(descriptor.args):]
                    else:
                        arguments = []
                    for i in range(num_arguments):
                        stack.pop()
                    obj = "static" if opcode == 0xb8 else stack.pop()
                    if descriptor.returns.name != "void":
                        stack.append(Operand(
                            "%s.%s(%s)" % (
                                obj, name, _PIT.join(arguments)
                            ),
                            2 if descriptor.returns.name in ("long", "double") else 1)
                        )

                    for arg in descriptor.args:
                        if arg.name == packetbuffer:
                        #if ("java.io.DataOutputStream" in descriptor[0] or
                        #        "java.io.DataOutput" in descriptor[0]):
                            operations += _PIT.sub_operations(
                                jar, cf, packetbuffer, instruction, operands[0],
                                [obj] + arguments if obj != "static" else arguments
                            )
                            break

            # Conditional statements and loops
            elif opcode in [0xc7, 0xc6] or opcode >= 0x99 and opcode <= 0xa6:
                if opcode == 0xc7:
                    condition = "%s == null" % stack.pop()
                elif opcode == 0xc6:
                    condition = "%s != null" % stack.pop()
                else:
                    if opcode <= 0x9e:                  # if
                        comperation = opcode - 0x99
                        fields = [0, stack.pop()]
                    elif opcode <= 0xa4:                # if_icmp
                        comperation = opcode - 0x9f
                        fields = [stack.pop(), stack.pop()]
                    else:                               # if_acmp
                        comperation = opcode - 0xa5
                        fields = [operands.pop(), operands.pop()]
                    if comperation == 0 and fields[0] == 0:
                        condition = fields[1]
                    else:
                        condition = "%s %s %s" % (
                            fields[1], _PIT.CONDITIONS[comperation], fields[0]
                        )
                operations.append(Operation(instruction.pos, "if",
                                            condition=condition))
                operations.append(Operation(operands[0].target, "endif"))
                shortif_cond = condition

            elif opcode == 0xaa:                        # tableswitch
                # TODO: I don't know quite how this works, and it seems to be broken.
                # I need to look up this operation.
                operations.append(Operation(instruction.pos, "switch",
                                            field=stack.pop()))

                low = operands[0].value[1]
                for opr in range(1, len(operands)):
                    target = operands[opr].target
                    operations.append(Operation(target, "case",
                                                value=low + opr - 1))
                operations.append(Operation(operands[0].target, "endswitch"))

            elif opcode == 0xab:                        # lookupswitch
                operations.append(Operation(instruction.pos, "switch",
                                            field=stack.pop()))
                for opr in range(1, len(operands)):
                    target = operands[opr].find_target(1)
                    operations.append(Operation(target, "case",
                                                value=operands[opr].value[0]))
                operations.append(Operation(operands[0].target, "endswitch"))

            elif opcode == 0xa7:                        # goto
                target = operands[0].target
                endif = _PIT.find_next(operations, instruction.pos, "endif")
                case = _PIT.find_next(operations, instruction.pos, "case")
                if case is not None and target > case.position:
                    operations.append(Operation(instruction.pos, "break"))
                elif endif is not None:
                    if target > instruction.pos:
                        endif.operation = "else"
                        operations.append(Operation(target, "endif"))
                        if len(stack) != 0:
                            shortif_pos = target
                    else:
                        endif.operation = "endloop"
                        _PIT.find_next(
                            operations, target, "if"
                        ).operation = "loop"
                elif target > instruction.pos:
                    skip_until = target

            # Math
            elif opcode >= 0x74 and opcode <= 0x77:
                category = stack[-1].category
                stack.append(Operand("(- %s)" % (stack.pop), category))
            elif opcode >= 0x60 and opcode <= 0x7f:     # Tneg
                lookup_opcode = opcode
                while not lookup_opcode in _PIT.MATH:
                    lookup_opcode -= 1
                category = stack[-1].category
                value2 = stack.pop()
                stack.append(Operand(
                    "(%s %s %s)" % (
                        stack.pop(), _PIT.MATH[lookup_opcode], value2
                    ), category
                ))
            elif opcode == 0x84:                        # iinc
                operations.append(Operation(instruction.pos, "increment",
                                            field="var%s" % operands[0],
                                            amount=operands[1]))

            # Other manually handled opcodes
            elif opcode == 0xc5:                        # multianewarray
                operand = ""
                for i in range(operands[1].value):
                    operand = "[%s]%s" % (stack.pop(), operand)
                stack.append(Operand(
                    "new %s%s" % (operands[0].type, operand)))
            elif opcode == 0x58:                        # pop2
                if stack.pop().category != 2:
                    stack.pop()
            elif opcode == 0x5f:                        # swap
                stack += [stack.pop(), stack.pop()]
            elif opcode == 0x59:                        # dup
                stack.append(stack[-1])
            elif opcode == 0x5a:                        # dup_x1
                stack.insert(-2, stack[-1])
            elif opcode == 0x5b:                        # dup_x2
                stack.insert(-2 if stack[-2].category == 2 else -3, stack[-1])
            elif opcode == 0x5c:                        # dup2
                if stack[-1].category == 2:
                    stack.append(stack[-1])
                else:
                    stack += stack[-2:]
            elif opcode == 0x5d:                        # dup2_x1
                if stack[-1].category == 2:
                    stack.insert(-2, stack[-1])
                else:
                    stack.insert(-3, stack[-2])
                    stack.insert(-3, stack[-1])
            elif opcode == 0x5e:                        # dup2_x2
                if stack[-1].category == 2:
                    stack.insert(
                        -2 if stack[-2].category == 2 else -3, stack[-1]
                    )
                else:
                    stack.insert(
                        -3 if stack[-3].category == 2 else -4, stack[-2]
                    )
                    stack.insert(
                        -3 if stack[-3].category == 2 else -4, stack[-1]
                    )

            # Unhandled opcodes
            elif opcode in [0xc8, 0xa8, 0xc9]:
                raise Exception("unhandled opcode 0x%x" % opcode)

            # Default handlers
            else:
                lookup_opcode = opcode
                while not lookup_opcode in _PIT.OPCODES:
                    lookup_opcode -= 1

                handler = _PIT.OPCODES[lookup_opcode]
                index = 0

                if isinstance(handler, int):
                    handler = [handler]

                assert len(stack) >= handler[index]

                for i in range(handler[index]):
                    operands.insert(0, stack.pop())

                index += 1

                if len(handler) > index:
                    format = handler[index]
                    index += 1

                    if (len(handler) > index and
                            isinstance(handler[index], LambdaType)):
                        value = handler[index](opcode)
                        operands.append(value)
                        operands.append(arg_names[value]
                                        if value < len(arg_names)
                                        else "var%s" % value)
                        index += 1
                    elif len(operands) >= 1:
                        value = operands[0].value
                        operands.append(arg_names[value]
                                        if value < len(arg_names)
                                        else "var%s" % value)

                    if (len(handler) > index and
                            isinstance(handler[index], int)):
                        category = handler[index]
                    else:
                        category = 1

                    stack.append(Operand(
                        StringFormatter.format(format, *operands),
                        category)
                    )

        return operations

    @staticmethod
    def join(arguments, seperator=", "):
        """Converts a list of object into a comma seperated list"""
        buffer = ""
        for arg in arguments:
            buffer += "%s%s" % (arg, seperator)
        return buffer[:-len(seperator)]

    @staticmethod
    def find_next(operations, position, operation_search):
        """Finds an operation"""
        for operation in _PIT.ordered_operations(operations):
            if (operation.position > position and
                    operation.operation == operation_search):
                return operation

    @staticmethod
    def ordered_operations(operations):
        """Orders the operation by their actual position"""
        return sorted(operations, key=lambda op: op.position)

    @staticmethod
    def sub_operations(jar, cf, packetbuffer, instruction,
                       operand, arg_names=[""]):
        """Gets the instructions of a different class"""
        invoked_class = operand.c + ".class"
        name = operand.name
        descriptor = operand.descriptor
        args = method_descriptor(descriptor).args_descriptor
        cache_key = "%s/%s/%s/%s" % (invoked_class, name,
                                     descriptor, _PIT.join(arg_names, ","))

        if cache_key in _PIT.CACHE:
            cache = _PIT.CACHE[cache_key]
            operations = [op.clone() for op in cache]
        else:
            operations = _PIT.operations(jar, invoked_class, packetbuffer,
                                         args, name, arg_names)

        position = 0
        for operation in _PIT.ordered_operations(operations):
            position += 0.01
            operation.position = instruction.pos + (position)

        _PIT.CACHE[cache_key] = operations

        return operations

    @staticmethod
    def format(operations):
        """Constructs output structure"""

        head = []
        stack = [head]
        aggregate = {"instructions": head}
        size = 0

        block_start = ("if", "loop", "switch", "else")
        block_end = ("endif", "endloop", "endswitch", "else")

        for operation in _PIT.ordered_operations(operations):
            if operation.operation == "write":
                if size is not None:
                    if len(stack) == 1 and operation.type in _PIT.SIZES:
                        size += _PIT.SIZES[operation.type]
                    else:
                        size = None

            obj = operation.__dict__.copy()
            obj.pop("position")
            for field in ("field", "condition"):
                if field in obj:
                    obj[field] = _PIT.clean_field(obj[field])

            if operation.operation in block_end + block_start:
                if operation.operation in block_end:
                    if len(head) == 0:
                        stack[-2].pop()
                    stack.pop()
                    head = stack[-1]
                if operation.operation in block_start:
                    new_head = []
                    stack.append(new_head)
                    obj["instructions"] = new_head
                    head.append(obj)
                    head = new_head
            else:
                head.append(obj)

        if size is not None:
            aggregate["size"] = size

        return aggregate

    @staticmethod
    def clean_field(field):
        for pattern in _PIT.CLEANUP_PATTERN:
            field = re.sub(pattern[0], pattern[1], field)
        return field


class Operation:
    """Represents a performed operation"""
    def __init__(self, position, operation, **args):
        self.position = position
        self.operation = operation

        for arg in args:
            self.set(arg, args[arg])

    def __repr__(self):
        return str(self.__dict__)

    def set(self, key, value):
        self.__dict__[key] = str(value)
        return self

    def clone(self):
        clone = Operation(self.position, self.operation)
        for name in self.__dict__:
            clone.set(name, self.__dict__[name])
        return clone


class InstructionField:
    """Represents a operand in a instruction"""
    def __init__(self, operand, instruction, constants):
        self.value = operand[1]
        self.optype = operand[0]
        self.constants = constants
        self.instruction = instruction
        self.handlers = {
            "name": self.find_name,
            "class": self.find_class,
            "c": self.find_class,
            "classname": self.find_classname,
            "descriptor": self.find_descriptor,
            "target": self.find_target,
            "atype": self.find_atype,
            "type": self.find_type
        }

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return self.__str__()

    def __getattr__(self, name):
        if name in self.handlers:
            return self.handlers[name]()
        else:
            raise AttributeError

    def __getitem__(self, key):
        return self.value[key]

    def find_class(self):
        """Finds the class defining the method called in instruction"""
        return self.find_constant({ConstantFieldRef.TAG: lambda c: c.class_.index,
                                   ConstantMethodRef.TAG: lambda c: c.class_.index})

    def find_name(self):
        """Finds the name of a method called in the suplied instruction"""
        return self.find_constant({ConstantNameAndType.TAG: lambda c: c.name.index})

    def find_classname(self):
        """Finds the name of a class used for casting"""
        return self.find_name().split("/")[-1]

    def find_descriptor(self):
        """Finds types used in an instruction"""
        return self.find_constant({
            ConstantNameAndType.TAG: lambda c: c.descriptor.index
        })

    def find_constant(self, custom_follow={}, index=None):
        """Walks the constant tree to a name or descriptor"""
        # TODO: Is this really a logical way of doing it?
        # It seems messy...
        if index is None:
            index = self.value
        const = self.constants[index]
        tag = const.TAG
        follow = {
            #ConstantLong.TAG: lambda c: c.value,
            ConstantClass.TAG: lambda c: c.name.index,
            ConstantFieldRef.TAG: lambda c: c.name_and_type.index,
            ConstantMethodRef.TAG: lambda c: c.name_and_type.index,
            ConstantInterfaceMethodRef.TAG: lambda c: c.name_and_type.index,
            ConstantString.TAG: lambda c: c.string.index
        }
        format = "\"%s\"" if isinstance(const, ConstantString) else "%s"
        follow.update(custom_follow)
        if tag in follow:
            return format % self.find_constant(follow, follow[tag](const))
        elif isinstance(const, (ConstantInteger, ConstantFloat, ConstantLong, ConstantDouble, ConstantUTF8)):
            return format % const.value
        raise Exception("Can't find the value of constant " + str(const))

    def find_target(self, index=0):
        """Finds the target of a goto or if instruction"""
        if isinstance(self.value, tuple):
            value = self.value[index]
        else:
            value = self.value

        return value + self.instruction.pos

    def find_type(self):
        """Finds a type used by an instruction"""
        descriptor = self.find_constant()
        descriptor = field_descriptor(descriptor)
        return descriptor[:descriptor.find("[")]

    def find_atype(self):
        """Finds the type used by the `newarray` instruction"""
        return [
            "boolean",
            "char",
            "float",
            "double",
            "byte",
            "short",
            "int",
            "long"
        ][self.value - 4]


class Operand:
    """Represents an operand on the runtime operand stack"""
    def __init__(self, value, category=1):
        self.value = value
        self.category = category

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return "%s [%s]" % (self.value, self.category)


class StringFormatter:
    """
    Provides a subset of the features of string.format.

    This class provides a fallback for python versions before 2.6 to use a
    subset of the string.format functionality. This functionality is limited
    to the following format:

    {id[.field][:x]}

    """

    NATIVE = sys.version_info >= (2, 6)

    PATTERN = re.compile("{(\d+)(\.(\w+))?(:(\w))?}")

    @staticmethod
    def format(string, *args):
        if StringFormatter.NATIVE:
            return string.format(*args)
        else:
            return StringFormatter(string, args).parse()

    def __init__(self, string, values):
        self.string = string
        self.values = values

    def parse(self):
        return re.sub(self.PATTERN, self.match, self.string)

    def match(self, match):
        value = self.values[int(match.group(1))]
        if match.group(3) is not None:
            value = getattr(value, match.group(3))
        if match.group(5) == "x":
            value = hex(value)[2:]

        return str(value)


_PIT = PacketInstructionsTopping
