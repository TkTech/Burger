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
import six
import six.moves

from types import LambdaType

from jawa.util.descriptor import method_descriptor, parse_descriptor
from jawa.constants import *
from jawa.transforms.simple_swap import simple_swap

from .topping import Topping

class PacketInstructionsTopping(Topping):
    """Provides the instructions used to construct network packets."""

    PROVIDES = [
        "packets.instructions"
    ]

    DEPENDS = [
        "packets.classes",
        "identify.packet.packetbuffer",
        "identify.nbtcompound",
        "identify.itemstack",
        "identify.chatcomponent",
        "identify.metadata",
        "identify.resourcelocation"
    ]

    TYPES = {
        "writeBoolean": "boolean",
        "writeByte": "byte",
        "writeBytes": "byte[]",
        "writeChar": "char",
        "writeDouble": "double",
        "writeFloat": "float",
        "writeInt": "int",
        "writeLong": "long",
        "writeShort": "short"
    }

    CACHE = {}

    # Simple instructions are registered below
    OPCODES = {}

    @classmethod
    def register_ins(cls, opcodes, stack_count, template, extra_method=None, category=1):
        """
        Registers an instruction handler.  This should be used for instructions
        that pop some one or more things from the stack and then push a new
        value onto it.

        opcodes: A single opcode or a list of opcodes for that handler
        stack_count: The number of things to pop from the stack
        template: A format string; uses stack and operands (and extra if given)
        extra_method: Used to get a bit of additional information.  Param is ins
        category: JVM category for the resulting StackOperand
        """
        if isinstance(opcodes, six.string_types):
            opcodes = [opcodes]
        data = {
            "stack_count": stack_count,
            "template": template,
            "extra_method": extra_method,
            "category": category
        }
        for opcode in opcodes:
            cls.OPCODES[opcode] = data

    # Prefix types used in instructions
    INSTRUCTION_TYPES = {
        'a': 'Object',
        'b': 'boolean',
        'c': 'char',
        'd': 'double',
        'f': 'float',
        'i': 'int',
        'l': 'long',
        's': 'short'
    }

    CLEANUP_PATTERN = [
        (re.compile("^\((.*[^(])\)$"), "\\1"),
        (re.compile("(^|[() ])this\."), "\\1")
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        """Finds all packets and decompiles them"""
        for key, packet in six.iteritems(aggregate["packets"]["packet"]):
            operations = None
            try:
                operations = _PIT.operations(classloader, packet["class"], aggregate["classes"])
                packet.update(_PIT.format(operations))
            except Exception as e:
                if verbose:
                    print("Error: Failed to parse instructions of packet %s (%s): %s" % (key, packet["class"], e))
                    traceback.print_exc()
                    if operations:
                        import json
                        print(json.dumps(operations, default=lambda o:o.__dict__, indent=4))
                    print()

    @staticmethod
    def operations(classloader, classname, classes, args=None,
                   methodname=None, arg_names=("this", "packetbuffer")):
        """Gets the instructions of the specified method"""

        # Find the writing method
        cf = classloader.load(classname)

        if methodname is None and args is None:
            methods = list(cf.methods.find(returns="V", args="L" + classes["packet.packetbuffer"] + ";"))

            if len(methods) == 2:
                method = methods[1]
            else:
                if cf.super_.name.value != "java/lang/Object":
                    return _PIT.operations(classloader, cf.super_.name.value + ".class", classes)
                else:
                    raise Exception("Failed to find method in class or superclass")
        elif methodname is None:
            method = cf.methods.find_one(args=args)
        else:
            method = cf.methods.find_one(name=methodname, args=args)

        if method.access_flags.acc_abstract:
            # Abstract method call -- just log that, since we can't view it
            return [Operation(instruction.pos, "interfacecall",
                              type="abstract", target=operands[0].c, name=name,
                              method=name + desc, field=obj, args=_PIT.join(arguments))]

        # Decode the instructions
        operations = []
        stack = []
        skip_until = -1
        shortif_pos = None
        shortif_cond = None

        for instruction in method.code.disassemble(transforms=[simple_swap]):
            if skip_until != -1:
                if instruction.pos == skip_until:
                    skip_until = -1
                else:
                    continue

            mnemonic = instruction.mnemonic
            operands = [InstructionField(operand, instruction, cf.constants)
                        for operand in instruction.operands]

            # Shortcut if
            if instruction.pos == shortif_pos:
                # Check to make sure that this actually is a ternary if
                assert len(operations) >= 3
                assert operations[-1].operation == "endif"
                assert operations[-2].operation == "else"
                assert operations[-3].operation == "if"
                # Now get rid of the unneeded if's
                operations.pop()
                operations.pop()
                operations.pop()
                category = stack[-1].category
                stack.append(StackOperand("((%(cond)s) ? %(sec)s : %(first)s)" % {
                    "cond": shortif_cond,
                    "first": stack.pop(),
                    "sec": stack.pop()
                }, category))
                shortif_cond = None
                shortif_pos = None

            # Method calls
            if mnemonic in ("invokevirtual", "invokespecial", "invokestatic", "invokeinterface"):
                name = operands[0].name
                desc = operands[0].descriptor

                descriptor = method_descriptor(desc)
                num_arguments = len(descriptor.args)

                if num_arguments > 0:
                    arguments = stack[-len(descriptor.args):]
                else:
                    arguments = []
                for i in six.moves.range(num_arguments):
                    stack.pop()

                is_static = (mnemonic == "invokestatic")
                obj = operands[0].classname if is_static else stack.pop()

                if name in _PIT.TYPES:
                    # Builtin netty buffer methods
                    assert num_arguments == 1
                    operations.append(Operation(instruction.pos, "write",
                                                type=_PIT.TYPES[name],
                                                field=arguments[0]))
                    stack.append(obj)
                elif len(name) == 1 and isinstance(obj, StackOperand) and obj.value == "packetbuffer":
                    # Checking len(name) == 1 is used to see if it's a Minecraft
                    # method (due to obfuscation).  Netty methods have real
                    # (and thus longer) names.
                    assert num_arguments == 1
                    arg_type = descriptor.args[0].name
                    field = arguments[0]

                    if descriptor.args[0].dimensions == 1:
                        # Array methods, which prefix a length
                        operations.append(Operation(instruction.pos, "write",
                                                    type="varint",
                                                    field="%s.length" % field))
                        if arg_type == "byte":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="byte[]",
                                                        field=field))
                        elif arg_type == "int":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="varint[]",
                                                        field=field))
                        elif arg_type == "long":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="long[]",
                                                        field=field))
                        else:
                            raise Exception("Unexpected array type: " + arg_type)
                    else:
                        assert descriptor.args[0].dimensions == 0
                        if arg_type == "java/lang/String":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="string",
                                                        field=field))
                        elif arg_type == "java/util/UUID":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="uuid",
                                                        field=field))
                        elif arg_type == "java/util/Date":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="long",
                                                        field="%s.getTime()" % field))
                        elif arg_type == "int":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="varint",
                                                        field=field))
                        elif arg_type == "long":
                            operations.append(Operation(instruction.pos, "write",
                                                        type="varlong",
                                                        field=field))
                        elif arg_type == "java/lang/Enum":
                            # If we were using the read method instead of the write method, then we could get the class for this enum...
                            operations.append(Operation(instruction.pos, "write",
                                                        type="enum",
                                                        field=field))
                        elif arg_type == classes["nbtcompound"]:
                            operations.append(Operation(instruction.pos, "write",
                                                        type="nbtcompound",
                                                        field=field))
                        elif arg_type == classes["itemstack"]:
                            operations.append(Operation(instruction.pos, "write",
                                                        type="itemstack",
                                                        field=field))
                        elif arg_type == classes["chatcomponent"]:
                            operations.append(Operation(instruction.pos, "write",
                                                        type="chatcomponent",
                                                        field=field))
                        elif arg_type == classes["identifier"]:
                            operations.append(Operation(instruction.pos, "write",
                                                        type="identifier",
                                                        field=field))
                        elif arg_type == classes["position"]:
                            operations.append(Operation(instruction.pos,
                                                        "write", type="position",
                                                        field=field))
                        else:
                            raise Exception("Unexpected type: " + arg_type)
                    # Return the buffer back to the stack.
                    assert descriptor.returns.name == classes["packet.packetbuffer"]
                    stack.append(obj)
                elif name == "<init>":
                    # Constructor call.  Should have the instance right
                    # on the stack as well (due to constructors returning void).
                    # Add the arguments to that object.
                    assert stack[-1] is obj
                    obj.value += "(" + _PIT.join(arguments) + ")";
                else:

                    if descriptor.returns.name != "void":
                        stack.append(StackOperand(
                            "%s.%s(%s)" % (
                                obj, name, _PIT.join(arguments)
                            ),
                            2 if descriptor.returns.name in ("long", "double") else 1)
                        )

                    else:
                        for arg in descriptor.args:
                            if arg.name == classes["packet.packetbuffer"]:
                                if operands[0].c == classes["metadata"]:
                                    # Special case - metadata is a complex type but
                                    # well documented; we don't want to include its
                                    # exact writing but just want to instead say
                                    # 'metadata'.

                                    # There are two cases - one is calling an
                                    # instance method of metadata that writes
                                    # out the instance, and the other is a
                                    # static method that takes a list and then
                                    # writes that list.
                                    operations.append(Operation(instruction.pos,
                                                    "write", type="metadata",
                                                    field=obj if not is_static else arguments[0]))
                                    break
                                if mnemonic != "invokeinterface":
                                    # If calling a sub method that takes a packetbuffer
                                    # as a parameter, it's possible that it's a sub
                                    # method that writes to the buffer, so we need to
                                    # check it.
                                    operations += _PIT.sub_operations(
                                        classloader, cf, classes, instruction, operands[0],
                                        [obj] + arguments if not is_static else arguments
                                    )
                                else:
                                    # However, for interface method calls, we can't
                                    # check its code -- so just note that it's a call
                                    operations.append(Operation(instruction.pos,
                                                        "interfacecall",
                                                        type="interface",
                                                        target=operands[0].c,
                                                        name=name,
                                                        method=name + desc,
                                                        field=obj,
                                                        args=_PIT.join(arguments)))
                                break

            # Conditional statements and loops
            elif mnemonic.startswith("if"):
                if "icmp" in mnemonic or "acmp" in mnemonic:
                    value2 = stack.pop()
                    value1 = stack.pop()
                elif "null" in mnemonic:
                    value1 = stack.pop()
                    value2 = "null"
                else:
                    value1 = stack.pop()
                    value2 = 0

                # All conditions are reversed: if the condition in the mnemonic
                # passes, then we'd jump; thus, to execute the following code,
                # the condition must _not_ pass
                if mnemonic in ("ifeq", "if_icmpeq", "if_acmpeq", "ifnull"):
                    comparison = "!="
                elif mnemonic in ("ifne", "if_icmpne", "if_acmpne", "ifnonnull"):
                    comparison = "=="
                elif mnemonic in ("iflt", "if_icmplt"):
                    comparison = ">="
                elif mnemonic in ("ifge", "if_icmpge"):
                    comparison = "<"
                elif mnemonic in ("ifgt", "if_icmpgt"):
                    comparison = "<="
                elif mnemonic in ("ifle", "if_icmple"):
                    comparison = ">"
                else:
                    raise Exception("Unknown if mnemonic %s (0x%x)" % (mnemonic, instruction.opcode))

                if comparison == "!=" and value2 == 0:
                    # if (something != 0) -> if (something)
                    condition = value1
                else:
                    condition = "%s %s %s" % (value1, comparison, value2)

                operations.append(Operation(instruction.pos, "if",
                                            condition=condition))
                operations.append(Operation(operands[0].target, "endif"))
                if shortif_pos is not None:
                    # Clearly not a ternary-if if we have another nested if
                    # (assuming that it's not a nested ternary, which we
                    # already don't handle for other reasons)
                    # If we don't do this, then the following code can have
                    # problems:
                    # if (a) {
                    #     if (b) {
                    #         // ...
                    #     }
                    # } else if (c) {
                    #     // ...
                    # }
                    # as there would be a goto instruction to skip the
                    # `else if (c)` portion that would be parsed as a shortif
                    shortif_pos = None
                shortif_cond = condition

            elif mnemonic == "tableswitch":
                operations.append(Operation(instruction.pos, "switch",
                                            field=stack.pop()))

                default = operands[0].target
                low = operands[1].value
                high = operands[2].value
                for opr in six.moves.range(3, len(operands)):
                    target = operands[opr].target
                    operations.append(Operation(target, "case",
                                                value=low + opr - 3))
                # TODO: Default might not be the right place for endswitch,
                # though it seems like default isn't used in any other way
                # in the normal code.
                operations.append(Operation(default, "endswitch"))

            elif mnemonic == "lookupswitch":
                raise Exception("lookupswitch is not supported")
                # operations.append(Operation(instruction.pos, "switch",
                #                             field=stack.pop()))
                # for opr in six.moves.range(1, len(operands)):
                #     target = operands[opr].find_target(1)
                #     operations.append(Operation(target, "case",
                #                                 value=operands[opr].value[0]))
                # operations.append(Operation(operands[0].target, "endswitch"))

            elif mnemonic == "goto":
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

            elif mnemonic == "iinc":
                operations.append(Operation(instruction.pos, "increment",
                                            field="var%s" % operands[0],
                                            amount=operands[1]))

            # Other manually handled instructions
            elif mnemonic == "multianewarray":
                operand = ""
                for i in six.moves.range(operands[1].value):
                    operand = "[%s]%s" % (stack.pop(), operand)
                stack.append(StackOperand(
                    "new %s%s" % (operands[0].type, operand)))
            elif mnemonic == "pop":
                stack.pop()
            elif mnemonic == "pop2":
                if stack.pop().category != 2:
                    stack.pop()
            elif mnemonic == "swap":
                stack[-2], stack[-1] = stack[-1], stack[-2]
            elif mnemonic == "dup":
                stack.append(stack[-1])
            elif mnemonic == "dup_x1":
                stack.insert(-2, stack[-1])
            elif mnemonic == "dup_x2":
                stack.insert(-2 if stack[-2].category == 2 else -3, stack[-1])
            elif mnemonic == "dup2":
                if stack[-1].category == 2:
                    stack.append(stack[-1])
                else:
                    stack += stack[-2:]
            elif mnemonic == "dup2_x1":
                if stack[-1].category == 2:
                    stack.insert(-2, stack[-1])
                else:
                    stack.insert(-3, stack[-2])
                    stack.insert(-3, stack[-1])
            elif mnemonic == "dup2_x2":
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
            elif mnemonic == "return":
                # Don't attempt to lookup the instruction in the handler
                pass

            elif instruction.mnemonic in ("istore", "lstore", "fstore", "dstore", "astore"):
                # Keep track of what is being stored, for clarity
                type = _PIT.INSTRUCTION_TYPES[instruction.mnemonic[0]]
                arg = operands.pop().value

                var = arg_names[arg] if arg < len(arg_names) else "var%s" % arg
                operations.append(Operation(instruction.pos, "store",
                                            type=type,
                                            var=var,
                                            value=stack.pop()))

            elif instruction.mnemonic in ("iastore", "lastore", "fastore", "dastore", "aastore", "bastore", "castore", "sastore"):
                type = _PIT.INSTRUCTION_TYPES[instruction.mnemonic[0]]

                # Array store
                value = stack.pop()
                index = stack.pop()
                array = stack.pop()
                operations.append(Operation(instruction.pos, "arraystore",
                                        type=type,
                                        index=index,
                                        var=array,
                                        value=value))

            # Default handlers
            else:
                if mnemonic not in _PIT.OPCODES:
                    raise Exception("Unhandled instruction opcode %s (0x%x)" % (mnemonic, instruction.opcode))

                handler = _PIT.OPCODES[mnemonic]

                ins_stack = []
                assert len(stack) >= handler["stack_count"]

                for _ in six.moves.range(handler["stack_count"]):
                    ins_stack.insert(0, stack.pop())

                ctx = {
                    "operands": operands,
                    "stack": ins_stack,
                    "ins": instruction,
                    "arg_names": arg_names
                }

                if handler["extra_method"]:
                    ctx["extra"] = handler["extra_method"](ctx)

                category = handler["category"]
                try:
                    formatted = handler["template"].format(**ctx)
                except Exception as ex:
                    raise Exception("Failed to format info for %s (0x%x) with template %s and ctx %s: %s" %
                        (mnemonic, instruction.opcode, handler["template"], ctx, ex))

                stack.append(StackOperand(formatted, handler["category"]))

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
    def sub_operations(classloader, cf, classes, instruction,
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
            operations = _PIT.operations(classloader, invoked_class, classes,
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

        block_start = ("if", "loop", "switch", "else")
        block_end = ("endif", "endloop", "endswitch", "else")

        for operation in _PIT.ordered_operations(operations):
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
        assert instruction.mnemonic != "lookupswitch"
        # Note: this will fail if operand is not actually an instance of
        # Operand, which is the case for lookupswitch, hence the earlier assert
        self.value = operand.value
        assert isinstance(operand.value, int)
        self.constants = constants
        self.instruction = instruction
        self.handlers = {
            "name": self.find_name,
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

    def find_class(self):
        """Finds the internal name of a class, uses slashes for packages."""
        const = self.constants[self.value]
        if isinstance(const, ConstantClass):
            return const.name.value
        else:
            return const.class_.name.value

    def find_name(self):
        """Finds the name of a method called in the suplied instruction"""
        # At least, allegedly.  In practice this seems to actually be used for
        # a zillion other things, and usually not the name, for the ldc instruction
        const = self.constants[self.value]
        if isinstance(const, ConstantClass):
            return const.name.value
        elif isinstance(const, String):
            return '"' + const.string.value + '"'
        elif isinstance(const, (Integer, Float, Long, Double, UTF8)):
            return str(const.value)
        else:
            return self.constants[self.value].name_and_type.name.value

    def find_classname(self):
        """Finds the name of a class as intended for display"""
        name = self.find_class().replace("/", ".")
        if name.startswith("["):
            # Fix arrays, which might be in the form of [Lcom/example/Foo;
            desc = parse_descriptor(name)[0]
            name = desc.name + "[]" * desc.dimensions
        if name.startswith("java.lang.") or name.startswith("java.util."):
            name = name[10:]
        return name

    def find_descriptor(self):
        """Finds types used in an instruction"""
        return self.constants[self.value].name_and_type.descriptor.value

    def find_target(self):
        """Finds the target of a goto or if instruction"""
        return self.value + self.instruction.pos

    def find_type(self):
        """Finds a type used by an instruction"""
        # This may be broken, as current code does not use it
        descriptor = self.constants[self.value].name_and_type.descriptor.value
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


class StackOperand:
    """
    Represents an operand on the runtime operand stack
    value is the actual value
    category is the JVM category/type, see
    https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-2.html#jvms-2.11.1-320
    """
    def __init__(self, value, category=1):
        self.value = value
        self.category = category

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return "%s [%s]" % (self.value, self.category)

_PIT = PacketInstructionsTopping

# Register instructions now
def arg_name(arg_index=lambda ctx: ctx["operands"][0].value):
    """
    Returns a lambda that gets the name of the argument at the given index.
    The index defaults to the first operand's value.
    """
    return lambda ctx: (ctx["arg_names"][arg_index(ctx)]
                            if arg_index(ctx) < len(ctx["arg_names"])
                            else "var%s" % arg_index(ctx))

_PIT.register_ins("aconst_null", 0, "null")
_PIT.register_ins("iconst_m1", 0, "-1")
_PIT.register_ins(["iconst_" + str(i) for i in six.moves.range(6)], 0, "{extra}", lambda ctx: int(ctx["ins"].mnemonic[-1]))
_PIT.register_ins(["lconst_0", "lconst_1"], 0, "{extra}", lambda ctx: int(ctx["ins"].mnemonic[-1], 2))
_PIT.register_ins(["fconst_0", "fconst_1", "fconst_2"], 0, "{extra}.0f", lambda ctx: int(ctx["ins"].mnemonic[-1]))
_PIT.register_ins(["dconst_0", "dconst_1"], 0, "{extra}.0", lambda ctx: int(ctx["ins"].mnemonic[-1], 2))
_PIT.register_ins("bipush", 0, "0x{operands[0].value:x}")
_PIT.register_ins("sipush", 0, "0x{operands[0].value:x}")
_PIT.register_ins(["ldc", "ldc_w"], 0, "{operands[0].name}")
_PIT.register_ins("ldc2_w", 0, "{operands[0].name}", category=2)
_PIT.register_ins("iload", 0, "{extra}", arg_name())
_PIT.register_ins("lload", 0, "{extra}", arg_name(), 2)
_PIT.register_ins("fload", 0, "{extra}", arg_name())
_PIT.register_ins("dload", 0, "{extra}", arg_name(), 2)
_PIT.register_ins("aload", 0, "{extra}", arg_name())
_PIT.register_ins(["iload_" + str(i) for i in six.moves.range(4)], 0, "{extra}", arg_name(lambda ctx: int(ctx["ins"].mnemonic[-1])))
_PIT.register_ins(["lload_" + str(i) for i in six.moves.range(4)], 0, "{extra}", arg_name(lambda ctx: int(ctx["ins"].mnemonic[-1])), 2)
_PIT.register_ins(["fload_" + str(i) for i in six.moves.range(4)], 0, "{extra}", arg_name(lambda ctx: int(ctx["ins"].mnemonic[-1])))
_PIT.register_ins(["dload_" + str(i) for i in six.moves.range(4)], 0, "{extra}", arg_name(lambda ctx: int(ctx["ins"].mnemonic[-1])), 2)
_PIT.register_ins(["aload_" + str(i) for i in six.moves.range(4)], 0, "{extra}", arg_name(lambda ctx: int(ctx["ins"].mnemonic[-1])))
_PIT.register_ins("iaload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("laload", 2, "{stack[0]}[{stack[1]}]", category=2)
_PIT.register_ins("faload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("daload", 2, "{stack[0]}[{stack[1]}]", category=2)
_PIT.register_ins("aaload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("baload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("caload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("saload", 2, "{stack[0]}[{stack[1]}]")
_PIT.register_ins("iadd", 2, "({stack[0]} + {stack[1]})")
_PIT.register_ins("ladd", 2, "({stack[0]} + {stack[1]})", category=2)
_PIT.register_ins("fadd", 2, "({stack[0]} + {stack[1]})")
_PIT.register_ins("dadd", 2, "({stack[0]} + {stack[1]})", category=2)
_PIT.register_ins("isub", 2, "({stack[0]} - {stack[1]})")
_PIT.register_ins("lsub", 2, "({stack[0]} - {stack[1]})", category=2)
_PIT.register_ins("fsub", 2, "({stack[0]} - {stack[1]})")
_PIT.register_ins("dsub", 2, "({stack[0]} - {stack[1]})", category=2)
_PIT.register_ins("imul", 2, "({stack[0]} * {stack[1]})")
_PIT.register_ins("lmul", 2, "({stack[0]} * {stack[1]})", category=2)
_PIT.register_ins("fmul", 2, "({stack[0]} * {stack[1]})")
_PIT.register_ins("dmul", 2, "({stack[0]} * {stack[1]})", category=2)
_PIT.register_ins("idiv", 2, "({stack[0]} / {stack[1]})")
_PIT.register_ins("ldiv", 2, "({stack[0]} / {stack[1]})", category=2)
_PIT.register_ins("fdiv", 2, "({stack[0]} / {stack[1]})")
_PIT.register_ins("ddiv", 2, "({stack[0]} / {stack[1]})", category=2)
_PIT.register_ins("irem", 2, "({stack[0]} % {stack[1]})")
_PIT.register_ins("lrem", 2, "({stack[0]} % {stack[1]})", category=2)
_PIT.register_ins("frem", 2, "({stack[0]} % {stack[1]})")
_PIT.register_ins("drem", 2, "({stack[0]} % {stack[1]})", category=2)
_PIT.register_ins("ineg", 1, "(-{stack[0]})")
_PIT.register_ins("lneg", 1, "(-{stack[0]})", category=2)
_PIT.register_ins("fneg", 1, "(-{stack[0]})")
_PIT.register_ins("dneg", 1, "(-{stack[0]})", category=2)
_PIT.register_ins("ishl", 2, "({stack[0]} << {stack[1]})")
_PIT.register_ins("lshl", 2, "({stack[0]} << {stack[1]})", category=2)
_PIT.register_ins("ishr", 2, "({stack[0]} >>> {stack[1]})")
_PIT.register_ins("lshr", 2, "({stack[0]} >>> {stack[1]})", category=2)
_PIT.register_ins("iushr", 2, "({stack[0]} >> {stack[1]})")
_PIT.register_ins("lushr", 2, "({stack[0]} >> {stack[1]})", category=2)
_PIT.register_ins("iand", 2, "({stack[0]} & {stack[1]})")
_PIT.register_ins("land", 2, "({stack[0]} & {stack[1]})", category=2)
_PIT.register_ins("ior", 2, "({stack[0]} | {stack[1]})")
_PIT.register_ins("lor", 2, "({stack[0]} | {stack[1]})", category=2)
_PIT.register_ins("ixor", 2, "({stack[0]} ^ {stack[1]})")
_PIT.register_ins("lxor", 2, "({stack[0]} ^ {stack[1]})", category=2)
_PIT.register_ins(["i2l", "f2l", "d2l"], 1, "((long){stack[0]})", category=2)
_PIT.register_ins(["i2f", "l2f", "d2f"], 1, "((float){stack[0]})")
_PIT.register_ins(["i2d", "l2d", "f2d"], 1, "((double){stack[0]})", category=2)
_PIT.register_ins(["l2i", "f2i", "d2i"], 1, "((int){stack[0]})")
_PIT.register_ins("i2b", 1, "((byte){stack[0]})")
_PIT.register_ins("i2c", 1, "((char){stack[0]})")
_PIT.register_ins("i2s", 1, "((short){stack[0]})")
_PIT.register_ins("lcmp", 2, "compare({stack[0]}, {stack[1]})", category=2)
_PIT.register_ins("fcmpg", 2, "compare({stack[0]}, {stack[1]} /*, NaN -> 1 */)")
_PIT.register_ins("fcmpl", 2, "compare({stack[0]}, {stack[1]} /*, NaN -> -1 */)")
_PIT.register_ins("dcmpg", 2, "compare({stack[0]}, {stack[1]} /*, NaN -> 1 */)", category=2)
_PIT.register_ins("dcmpl", 2, "compare({stack[0]}, {stack[1]} /*, NaN -> -1 */)", category=2)
_PIT.register_ins("getstatic", 0, "{operands[0].classname}.{operands[0].name}") # Doesn't handle category
_PIT.register_ins("getfield", 1, "{stack[0]}.{operands[0].name}") # Doesn't handle category
_PIT.register_ins("new", 0, "new {operands[0].classname}")
_PIT.register_ins("newarray", 1, "new {operands[0].atype}[{stack[0]}]")
_PIT.register_ins("anewarray", 1, "new {operands[0].classname}[{stack[0]}]")
_PIT.register_ins("arraylength", 1, "{stack[0]}.length")
_PIT.register_ins("athrow", 1, "throw {stack[0]}") # this is a bit weird, but throw does put the exception back on the stack, kinda
_PIT.register_ins("checkcast", 1, "(({operands[0].classname}){stack[0]})")
_PIT.register_ins("instanceof", 1, "({stack[0]} instanceof {operands[0].classname})")
