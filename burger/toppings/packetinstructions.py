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
from solum import ClassFile

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
            cf = ClassFile(jar["%s.class" % packet["class"]], str_as_buffer=True)
            packet.update(PacketInstructionsTopping.debunk(cf))

    @staticmethod
    def find_next(operations, position, operation_search):
        """Finds the next operation of the type operation_search starting at the given position"""        
        for operation in PacketInstructionsTopping.ordered_operations(operations):
            if operation.position > position and operation.operation == operation_search:
                return operation

    @staticmethod
    def find_name(cf, instruction):
        """Finds the name of a method called in the suplied instruction"""
        return PacketInstructionsTopping.find_constant(cf, instruction.operands[0][1], "name_index")

    @staticmethod
    def find_descriptor(cf, instruction):
        """Finds tyoes used in the suplied instruction"""
        return PacketInstructionsTopping.find_constant(cf, instruction.operands[0][1], "descriptor_index")

    @staticmethod
    def find_constant(cf, index, index_key):
        """Walks the constant tree to a name or descriptor"""
        const = PacketInstructionsTopping.constant(cf, index)
        if const["tag"] == 1:
            return const["value"]
        elif const["tag"] == 5:
            return PacketInstructionsTopping.find_constant(cf, const["value"], index_key)
        elif const["tag"] == 9 or const["tag"] == 10:
            return PacketInstructionsTopping.find_constant(cf, const["name_and_type_index"], index_key)
        elif const["tag"] == 12:
            return PacketInstructionsTopping.find_constant(cf, const[index_key], index_key)
                
    @staticmethod
    def constant(cf, index):
        """Gets a contant by index"""
        return cf.constants.storage[index]

    @staticmethod
    def target(instruction):
        """Finds the target of a goto or if instruction"""
        return instruction.operands[0][1] - 2 + instruction.pos
    
    @staticmethod
    def ordered_operations(operations):
        """Orders the operatoin by their actual position"""
        return sorted(operations, key=lambda op: op.position)

    @staticmethod
    def debunk(cf):
        """Does the actual decompiling"""

        # Find the writing method
        method = cf.methods.find_one(args=('java.io.DataOutputStream',))

        # Decode the instructions
        operations = []

        for instruction in method.instructions:
            if instruction.name == "invokevirtual":
                type = PacketInstructionsTopping.find_name(cf, instruction)
                if PacketInstructionsTopping.TYPES.has_key(type):
                    operations.append(Operation(instruction.pos, "write").set("type", PacketInstructionsTopping.TYPES[type]))
                elif type == "write":
                    descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
                    operations.append(Operation(instruction.pos, "write").set("type", "byte[]" if descriptor.find("[B") >= 0 else "byte"))
            elif instruction.name == "invokestatic":
                descriptor = PacketInstructionsTopping.find_descriptor(cf, instruction)
                if descriptor.find("Ljava/lang/String") >= 0 and descriptor.find("Ljava/io/DataOutputStream") >= 0:
                    operations.append(Operation(instruction.pos, "write").set("type", "string16"))            
            elif instruction.name.startswith("if"):
                operations.append(Operation(instruction.pos,"if"))
                operations.append(Operation(PacketInstructionsTopping.target(instruction),"endif"))
            elif instruction.name == "goto":
                target_op = PacketInstructionsTopping.target(instruction)
                endif = PacketInstructionsTopping.find_next(operations, instruction.pos, "endif")
                if target_op > instruction.pos:
                    endif.operation = "else"
                    operations.append(Operation(target_op, "endif"))
                else:
                    endif.operation = "endloop"
                    PacketInstructionsTopping.find_next(operations, target_op, "if").operation = "loop"

        # Construct output structure
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
            if operation.operation in ["endif", "endloop", "else"]:
                stack.pop()
                head = stack[-1]
            if operation.operation in ["if", "loop", "else"]:
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
