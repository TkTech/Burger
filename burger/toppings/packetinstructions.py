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
from solum import ClassFile, JarFile
from solum.descriptor import method_descriptor
from solum.classfile.constants import ConstantType
from .topping import Topping

class PacketInstructionsTopping(Topping):
    """Provides the instructions used to construct a packet"""
    
    PROVIDES = [
        "packets.instructions",
        "packets.sizes"
    ]

    DEPENDS = [
        "packets.classes"
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

    CONDITIONS = {
        "eq": "!=",
        "ne": "==",
        "lt": "<=",
        "le": "<",
        "gt": ">=",
        "ge": ">"
    }

    MATH = {
        "add": "+",
        "and": "&",
        "div": "/",
        "mul": "*",
        "or": "|",
        "rem": "%",
        "shl": "<<",
        "shr": ">>",
        "sub": "-",
        "ushr": ">>",
        "xor": "^"
    }

    CACHE = {}

    @staticmethod
    def act(aggregate, jar, verbose=False):
        """Finds all packets and decompiles them"""
        for packet in aggregate["packets"]["packet"].values():
            packet.update(PacketInstructionsTopping.format(PacketInstructionsTopping.operations(jar, packet["class"])))

    @staticmethod
    def find_next(operations, position, operation_search):
        """Finds the next operation of the type operation_search starting at the given position"""        
        for operation in PacketInstructionsTopping.ordered_operations(operations):
            if operation.position > position and operation.operation == operation_search:
                return operation

    @staticmethod
    def find_class(cf, instruction):
        """Finds the class defining the method called in instruction"""
        return PacketInstructionsTopping.find_constant(cf, instruction.operands[0][1], {ConstantType.FIELD_REF: "class_index", ConstantType.METHOD_REF: "class_index"})

    @staticmethod
    def find_name(cf, instruction):
        """Finds the name of a method called in the suplied instruction"""
        return PacketInstructionsTopping.find_constant(cf, instruction.operands[0][1], {ConstantType.NAME_AND_TYPE: "name_index"})

    @staticmethod
    def find_descriptor(cf, instruction):
        """Finds types used in an instruction"""
        return PacketInstructionsTopping.find_constant(cf, instruction.operands[0][1], {ConstantType.NAME_AND_TYPE: "descriptor_index"})

    @staticmethod
    def find_constant(cf, index, custom_follow={}):
        """Walks the constant tree to a name or descriptor"""
        const = PacketInstructionsTopping.constant(cf, index)
        tag = const["tag"]
        follow = {
            ConstantType.LONG: "value",
            ConstantType.CLASS: "name_index",
            ConstantType.FIELD_REF: "name_and_type_index",
            ConstantType.METHOD_REF: "name_and_type_index",
            ConstantType.INTERFACE_METHOD_REF: "name_and_type_index"
            }
        follow.update(custom_follow)
        if tag == ConstantType.UTF8:
            return const["value"]
        elif follow.has_key(tag):
            return PacketInstructionsTopping.find_constant(cf, const[follow[tag]], follow)
                
    @staticmethod
    def constant(cf, index):
        """Gets a constant by index"""
        return cf.constants[index]

    @staticmethod
    def target(instruction, index=0):
        """Finds the target of a goto or if instruction"""
        operands = instruction.operands
        
        if type(index) != list:
            index = [index, 1]
        else:
            index = [index[0], 1] + index[1:]
            
        for i in index:
            operands = operands[i]
            
        return operands + instruction.pos
    
    @staticmethod
    def ordered_operations(operations):
        """Orders the operatoin by their actual position"""
        return sorted(operations, key=lambda op: op.position)

    @staticmethod
    def operations(jar, classname, args=('java.io.DataOutputStream',), methodname=None, arg_names=["", "stream"]):
        """Gets the instructions of the specified method"""

        # Find the writing method
        cf = jar.open_class(classname)

        if methodname == None:
            method = cf.methods.find_one(args=args)
        else:
            method = cf.methods.find_one(name=methodname, args=args)

        # Decode the instructions
        operations = []
        operands = []
        
        for instruction in method.instructions:
            # Method calls
            if instruction.name in ["invokevirtual", "invokestatic", "invokespecial", "invokeinterface"]:
                name = PacketInstructionsTopping.find_name(cf, instruction)
                descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
                if PacketInstructionsTopping.TYPES.has_key(name):
                    operations.append(Operation(instruction.pos, "write").set("type", PacketInstructionsTopping.TYPES[name]).set("field", operands.pop()))
                elif name == "write":
                    if descriptor.find("[BII") >= 0:
                        operands.pop()
                        operands.pop()
                    operations.append(Operation(instruction.pos, "write").set("type", "byte[]" if descriptor.find("[B") >= 0 else "byte").set("field", operands.pop()))
                elif descriptor == "(Ljava/lang/String;Ljava/io/DataOutputStream;)V":
                    operands.pop()
                    operations.append(Operation(instruction.pos, "write").set("type", "string16").set("field", operands.pop()))
                else:
                    descriptor = method_descriptor(descriptor)
                   
                    name = PacketInstructionsTopping.find_name(cf, instruction)
                    num_arguments = len(descriptor[0])
                    if num_arguments > 0:
                        arguments = operands[-len(descriptor[0]):]
                    else:
                        arguments = []
                    for i in range(num_arguments):
                        operands.pop()
                    obj = "static" if instruction.name == "invokestatic" else operands.pop()
                    if descriptor[1] != "void":
                        operands.append("%s%s%s(%s)" % (obj, "." if obj != "" else "", name, ",".join(arguments)))

                    if "java.io.DataOutputStream" in descriptor[0]:
                        operations += PacketInstructionsTopping.sub_operations(jar, cf, instruction, [obj] + arguments if obj != "static" else arguments)
                
            # Conditional statements and loops
            elif instruction.name.startswith("if"):
                if instruction.name == "ifnonnull":
                    condition = "%s == null" % operands.pop()
                elif instruction.name == "ifnull":
                    condition = "%s != null" % operands.pop()
                else:
                    if instruction.name[4:7] == "cmp":
                        comperation = instruction.name[7:]
                        fields = [operands.pop(), operands.pop()]
                    else:
                        comperation = instruction.name[2:]
                        fields = [operands.pop(), 0]
                    condition = "%s %s %s" % (fields[0], PacketInstructionsTopping.CONDITIONS[comperation], fields[1])
                operations.append(Operation(instruction.pos,"if").set("condition", condition))
                operations.append(Operation(PacketInstructionsTopping.target(instruction),"endif"))
            elif instruction.name == "tableswitch":
                operations.append(Operation(instruction.pos, "switch").set("field", operands.pop()))
                low = instruction.operands[0][1][1]
                for opr in range(1, len(instruction.operands)):
                    target = PacketInstructionsTopping.target(instruction, opr)
                    operations.append(Operation(target, "case").set("value", low + opr -  1))
                operations.append(Operation(PacketInstructionsTopping.target(instruction, [0,0]), "endswitch"))
            elif instruction.name == "goto":
                target = PacketInstructionsTopping.target(instruction)
                endif = PacketInstructionsTopping.find_next(operations, instruction.pos, "endif")
                case = PacketInstructionsTopping.find_next(operations, instruction.pos, "case")
                if case != None and target > case.position:
                    operations.append(Operation(instruction.pos, "break"))  
                elif target > instruction.pos:
                    endif.operation = "else"
                    operations.append(Operation(target, "endif"))
                else:
                    endif.operation = "endloop"
                    PacketInstructionsTopping.find_next(operations, target, "if").operation = "loop"

            # Operations
            elif PacketInstructionsTopping.MATH.has_key(instruction.name[1:]):
                operands.append("({1} {2} {0})".format(operands.pop(), operands.pop(), PacketInstructionsTopping.MATH[instruction.name[1:]]))
            elif instruction.name[1:] == "inc":
                operations.append(Operation(instruction.pos, "increment").set("field", "var%d" % instruction.operands[0][1]).set("amount", instruction.operands[1][1]))
            elif instruction.name[1:] == "neg":
                operands.append("-%s" % operands.pop())
                    
            # Operands
            elif instruction.name == "getfield":
                operand = operands.pop()
                operands.append("%s%s%s" % (operand, "." if operand != "" else "", PacketInstructionsTopping.find_name(cf, instruction)))
            elif instruction.name[1:].startswith("load_"):
                index = instruction.name[6:]
                operands.append(arg_names[int(index)] if len(arg_names) > int(index) else "var" + index)
            elif instruction.name.startswith("iconst_"):
                value = instruction.name[7:]
                if value == "m1":
                    value = -1
                operands.append(str(int(value)))
            elif instruction.name[1:] == "aload":
                operands.append("{1}[{0}]".format(operands.pop(), operands.pop()))
            elif instruction.name[1:] == "load":
                operands.append("unknown")
            elif instruction.name == "arraylength":
                operands.append("%s.length" % operands.pop())
            elif instruction.name == "bipush":
                operands.append(hex(instruction.operands[0][1]))
            elif instruction.name[1:] == "ipush":
                operands.append(instruction.operands[0][1])

        return operations

    @staticmethod
    def sub_operations(jar, cf, instruction, arg_names=[""]):
        """Gets the instrcutions of a different class"""
        invoked_class = PacketInstructionsTopping.find_class(cf, instruction)
        name = PacketInstructionsTopping.find_name(cf, instruction)
        descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
        args = method_descriptor(descriptor)[0]
        cache_key = "%s/%s/%s/%s" % (invoked_class, name, descriptor, ",".join(arg_names))

        if PacketInstructionsTopping.CACHE.has_key(cache_key):
            return PacketInstructionsTopping.CACHE[cache_key]
        
        operations = PacketInstructionsTopping.operations(jar, invoked_class, args, name, arg_names)
        position = 0
        for operation in PacketInstructionsTopping.ordered_operations(operations):
            position += 0.01
            operation.position = instruction.pos + (position)

        PacketInstructionsTopping.CACHE[cache_key] = operations

        return operations

    @staticmethod
    def format(operations):
        """Constructs output structure"""
        head = []
        stack = [head]
        aggregate = {"instructions": head}
        size = 0

        block_start = ["if", "loop", "switch", "else"]
        block_end = ["endif", "endloop", "endswitch", "else"]

        for operation in PacketInstructionsTopping.ordered_operations(operations):
            if operation.operation == "write":
                if size != None:
                    if len(stack) == 1 and PacketInstructionsTopping.SIZES.has_key(operation.type):
                        size += PacketInstructionsTopping.SIZES[operation.type]
                    else:
                        size = None
            
            obj = operation.__dict__.copy()
            obj.pop("position")
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

        if size != None:
            aggregate["size"] = size

        return aggregate

    
class Operation:
    def __init__(self, position, operation):
        self.position = position
        self.operation = operation

    def set(self, key, value):
        self.__dict__[key] = value
        return self
