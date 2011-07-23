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
from solum.bytecode import packed_instruction_size
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
            ConstantType.METHOD_REF: "name_and_type_index"
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
    def operations(jar, classname, args=('java.io.DataOutputStream',), methodname=None):
        """Gets the instructions of the specified method"""

        # Find the writing method
        cf = jar.open_class(classname)

        if methodname == None:
            method = cf.methods.find_one(args=args)
        else:
            method = cf.methods.find_one(name=methodname, args=args)

        # Decode the instructions
        operations = []

        for instruction in method.instructions:
            if instruction.name == "invokevirtual":
                type = PacketInstructionsTopping.find_name(cf, instruction)
                if PacketInstructionsTopping.TYPES.has_key(type):
                    operations.append(Operation(instruction.pos, "write").set("type", PacketInstructionsTopping.TYPES[type]))
                else:
                    descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
                    if type == "write":
                        operations.append(Operation(instruction.pos, "write").set("type", "byte[]" if descriptor.find("[B") >= 0 else "byte"))
                    elif descriptor.find("Ljava/io/DataOutputStream") >= 0:
                        operations += PacketInstructionsTopping.sub_operations(jar, cf, instruction)
            elif instruction.name == "invokestatic":
                descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
                if descriptor == "(Ljava/lang/String;Ljava/io/DataOutputStream;)V":
                    operations.append(Operation(instruction.pos, "write").set("type", "string16"))
                elif descriptor.find("Ljava/io/DataOutputStream") >= 0:
                    operations += PacketInstructionsTopping.sub_operations(jar, cf, instruction)
            elif instruction.name == "invokespecial":
                operations += PacketInstructionsTopping.sub_operations(jar, cf, instruction)
            elif instruction.name.startswith("if"):
                operations.append(Operation(instruction.pos,"if"))
                operations.append(Operation(PacketInstructionsTopping.target(instruction),"endif"))
            elif instruction.name == "tableswitch":
                operations.append(Operation(instruction.pos, "switch"))
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

        return operations

    @staticmethod
    def sub_operations(jar, cf, instruction):
        """Gets the instrcutions of a different class"""
        invoked_class = PacketInstructionsTopping.find_class(cf, instruction)
        name = PacketInstructionsTopping.find_name(cf, instruction)
        args = method_descriptor(PacketInstructionsTopping.find_descriptor(cf, instruction))[0]
        operations = PacketInstructionsTopping.operations(jar, invoked_class, args, name)
        position = 0
        for operation in PacketInstructionsTopping.ordered_operations(operations):
            position += 0.01
            operation.position = instruction.pos + (position)

        return operations

    @staticmethod
    def format(operations):
        """Constructs output structure"""
        head = []
        stack = [head]
        aggregate = {"instructions": head}
        size = 0

        for operation in PacketInstructionsTopping.ordered_operations(operations):
            if operation.operation == "write":
                head.append({"operation": "write", "type": operation.type})
                if size != None:
                    if len(stack) == 1 and PacketInstructionsTopping.SIZES.has_key(operation.type):
                        size += PacketInstructionsTopping.SIZES[operation.type]
                    else:
                        size = None
            elif operation.operation == "case":
                head.append({"operation": "case", "value": operation.value})
            elif operation.operation in ["break"]:
                head.append({"operation": operation.operation})
            else:
                if operation.operation in ["endif", "endloop", "endswitch", "else"]:
                    if len(head) == 0:
                        stack[-2].pop()
                    stack.pop()
                    head = stack[-1]
                if operation.operation in ["if", "loop", "switch", "else"]:
                    new_head = []
                    stack.append(new_head)
                    head.append({"operation": operation.operation, "instructions":new_head})
                    head = new_head

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
