#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2010-2011 Tyler Kennedy <tk@tkte.ch>

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
__all__ = [
    "OperandTypes",
    "BytecodeError",
    "StreamAssembler",
    "StreamDisassembler",
    "Operand"
]

import struct
try:
    from collections import namedtuple
except ImportError:
    from .compat import namedtuple


class BytecodeError(Exception):
    """
    Raised when any generic error occurs while asssembling or
    disassembling Java bytecode.
    """


class OperandTypes(object):
    """
    Represents the field parameters for opcodes.
    """
    PADDING = 0
    CONST_INDEX = 1
    LOCAL_INDEX = 2
    VALUE = 3
    BRANCH = 4

_op_table = {
    0x32: ["aaload", None, (2, 1)],
    0x53: ["aastore", None, (3, 0)],
    0x01: ["aconst_null", None, (0, 1)],
    0x19: ["aload", [(">B", 2)], (0, 1)],
    0x2A: ["aload_0", None, (0, 1)],
    0x2B: ["aload_1", None, (0, 1)],
    0x2C: ["aload_2", None, (0, 1)],
    0x2D: ["aload_3", None, (0, 1)],
    0xBD: ["anewarray", [(">H", 3)], (1, 1)],
    0xB0: ["areturn", None, (1, 0)],
    0xBE: ["arraylength", None, (1, 1)],
    0x3A: ["astore", [(">B", 2)], (1, 0)],
    0x4B: ["astore_0", None, (1, 0)],
    0x4C: ["astore_1", None, (1, 0)],
    0x4D: ["astore_2", None, (1, 0)],
    0x4E: ["astore_3", None, (1, 0)],
    0xBF: ["athrow", None],
    0x33: ["baload", None],
    0x54: ["bastore", None],
    0x10: ["bipush", [(">B", 3)]],
    0x34: ["caload", None],
    0x55: ["castore", None],
    0xC0: ["checkcast", [(">H", 1)]],
    0x90: ["d2f", None],
    0x8E: ["d2i", None],
    0x8F: ["d2l", None],
    0x63: ["dadd", None],
    0x31: ["daload", None],
    0x52: ["dastore", None],
    0x98: ["dcmpg", None],
    0x97: ["dcmpl", None],
    0x0E: ["dconst_0", None],
    0x0F: ["dconst_1", None],
    0x6F: ["ddiv", None],
    0x18: ["dload", [(">B", 2)]],
    0x26: ["dload_0", None],
    0x27: ["dload_1", None],
    0x28: ["dload_2", None],
    0x29: ["dload_3", None],
    0x6B: ["dmul", None],
    0x77: ["dneg", None],
    0x73: ["drem", None],
    0xAF: ["dreturn", None],
    0x39: ["dstore", [(">B", 2)]],
    0x47: ["dstore_0", None],
    0x48: ["dstore_1", None],
    0x49: ["dstore_2", None],
    0x4a: ["dstore_3", None],
    0x67: ["dsub", None],
    0x59: ["dup", None],
    0x5A: ["dup_x1", None],
    0x5B: ["dup_x2", None],
    0x5C: ["dup2", None],
    0x5D: ["dup2_x1", None],
    0x5E: ["dup2_x2", None],
    0x8D: ["f2d", None],
    0x8B: ["f2i", None],
    0x8C: ["f2l", None],
    0x62: ["fadd", None],
    0x30: ["faload", None],
    0x51: ["fastore", None],
    0x96: ["fcmpg", None],
    0x95: ["fcmpl", None],
    0x0B: ["fconst_0", None],
    0x0C: ["fconst_1", None],
    0x0D: ["fconst_2", None],
    0x6E: ["fdiv", None],
    0x17: ["fload", [(">B", 2)]],
    0x22: ["fload_0", None],
    0x23: ["fload_1", None],
    0x24: ["fload_2", None],
    0x25: ["fload_3", None],
    0x6A: ["fmul", None],
    0x76: ["fneg", None],
    0x72: ["frem", None],
    0xAE: ["freturn", None],
    0x38: ["fstore", [(">B", 2)]],
    0x43: ["fstore_0", None],
    0x44: ["fstore_1", None],
    0x45: ["fstore_2", None],
    0x46: ["fstore_3", None],
    0x66: ["fsub", None],
    0xB4: ["getfield", [(">H", 1)]],
    0xB2: ["getstatic", [(">H", 1)]],
    0xA7: ["goto", [(">h", 4)]],
    0xC8: ["goto_w", [(">i", 4)]],
    0x91: ["ib2", None],
    0x92: ["i2c", None],
    0x87: ["i2d", None],
    0x86: ["i2f", None],
    0x85: ["i2l", None],
    0x93: ["i2s", None],
    0x60: ["iadd", None],
    0x2E: ["iaload", None],
    0x7E: ["iand", None],
    0x4F: ["iastore", None],
    0x02: ["iconst_m1", None],
    0x03: ["iconst_0", None],
    0x04: ["iconst_1", None],
    0x05: ["iconst_2", None],
    0x06: ["iconst_3", None],
    0x07: ["iconst_4", None],
    0x08: ["iconst_5", None],
    0x6C: ["idiv", None],
    0xA5: ["if_acmpeq", [(">h", 4)]],
    0xA6: ["if_acmpne", [(">h", 4)]],
    0x9F: ["if_icmpeq", [(">h", 4)]],
    0xA0: ["if_icmpne", [(">h", 4)]],
    0xA1: ["if_icmplt", [(">h", 4)]],
    0xA2: ["if_icmpge", [(">h", 4)]],
    0xA3: ["if_icmpgt", [(">h", 4)]],
    0xA4: ["if_icmple", [(">h", 4)]],
    0x99: ["ifeq", [(">h", 4)]],
    0x9A: ["ifne", [(">h", 4)]],
    0x9B: ["iflt", [(">h", 4)]],
    0x9C: ["ifge", [(">h", 4)]],
    0x9D: ["ifgt", [(">h", 4)]],
    0x9E: ["ifle", [(">h", 4)]],
    0xC7: ["ifnonnull", [(">h", 4)]],
    0xC6: ["ifnull", [(">h", 4)]],
    0x84: ["iinc", [(">B", 2), (">b", 3)]],
    0x15: ["iload", [(">B", 2)]],
    0x1A: ["iload_0", None],
    0x1B: ["iload_1", None],
    0x1C: ["iload_2", None],
    0x1D: ["iload_3", None],
    0x68: ["imul", None],
    0x74: ["ineg", None],
    0xC1: ["instanceof", [(">H", 1)]],
    0xB9: ["invokeinterface", [(">H", 1), (">B", 3), (">B", 0)]],
    0xB7: ["invokespecial", [(">H", 1)]],
    0xB8: ["invokestatic", [(">H", 1)]],
    0xB6: ["invokevirtual", [(">H", 1)]],
    0x80: ["ior", None],
    0x70: ["irem", None],
    0xAC: ["ireturn", None],
    0x78: ["ishl", None],
    0x7A: ["ishr", None],
    0x36: ["istore", [(">B", 2)]],
    0x3B: ["istore_0", None],
    0x3C: ["istore_1", None],
    0x3D: ["istore_2", None],
    0x3E: ["istore_3", None],
    0x64: ["isub", None],
    0x7C: ["iushr", None],
    0x82: ["ixor", None],
    0xA8: ["jsr", [(">h", 4)]],
    0xC9: ["jsr_w", [(">i", 4)]],
    0x8A: ["l2d", None],
    0x89: ["l2f", None],
    0x88: ["l2i", None],
    0x61: ["ladd", None],
    0x2F: ["laload", None],
    0x7F: ["land", None],
    0x50: ["lastore", None],
    0x94: ["lcmp", None],
    0x09: ["lconst_0", None],
    0x0A: ["lconst_1", None],
    0x12: ["ldc", [(">B", 1)]],
    0x13: ["ldc_w", [(">H", 1)]],
    0x14: ["ldc2_w", [(">H", 1)]],
    0x6D: ["ldiv", None],
    0x16: ["lload", [(">b", 2)]],
    0x1E: ["lload_0", None],
    0x1F: ["lload_1", None],
    0x20: ["lload_2", None],
    0x21: ["lload_3", None],
    0x69: ["lmul", None],
    0x75: ["lneg", None],
    0xAB: ["lookupswitch", None],
    0x81: ["lor", None],
    0x71: ["lrem", None],
    0xAD: ["lreturn", None],
    0x79: ["lshl", None],
    0x7B: ["lshr", None],
    0x37: ["lstore", [(">b", 2)]],
    0x3F: ["lstore_0", None],
    0x40: ["lstore_1", None],
    0x41: ["lstore_2", None],
    0x42: ["lstore_3", None],
    0x65: ["lsub", None],
    0x7D: ["lushr", None],
    0x83: ["lxor", None],
    0xC2: ["monitorenter", None],
    0xC3: ["monitorexit", None],
    0xC5: ["multianewarray", [(">H", 1), (">B", 3)]],
    0xBB: ["new", [(">H", 1)]],
    0xBC: ["newarray", [(">B", 3)]],
    0x00: ["nop", None],
    0x57: ["pop", None],
    0x58: ["pop2", None],
    0xB5: ["putfield", [(">H", 1)]],
    0xB3: ["putstatic", [(">H", 1)]],
    0xA9: ["ret", [(">b", 2)]],
    0xB1: ["return", None],
    0x35: ["saload", None],
    0x56: ["sastore", None],
    0x11: ["sipush", [(">h", 3)]],
    0x5F: ["swap", None],
    0xAA: ["tableswitch", None],
    0xC4: ["wide", None],
    0xCA: ["breakpoint", None],
    0xFE: ["impdep1", None],
    0xFF: ["impdep2", None]
}

Instruction = namedtuple("Instruction", [
    "name",
    "opcode",
    "pos",
    "wide",
    "operands"
])

Operand = namedtuple("Operand", ["type", "value"])


def packed_instruction_size(instruction):
    """
    Returns the size in bytes of any known instruction given its
    `Instruction` representation.
    """
    ins = instruction
    if ins.wide:
        size = 6 if ins.opcode == 0x84 else 4
    else:
        size = 1
        operands = _op_table[ins.opcode][1]
        if operands:
            for operand in operands:
                size += struct.calcsize(operand[0])
    return size


class Disassembler(object):
    def __init__(self, source, starting_pos=0):
        self._cache = []
        self._usage = {}

        if hasattr(source, "read"):
            self._read = self._load_from_stream(source)
        else:
            self._read = self._load_from_str(source, starting_pos)

        self._pre_cache()

    def _load_from_stream(self, source):
        self._src = source
        self._pos = 0

        def _read(format_):
            size = struct.calcsize(format_)
            self._pos += size
            try:
                return struct.unpack(format_, self._src.read(size))
            except struct.error, e:
                raise IOError(str(e))

        return _read

    def _load_from_str(self, source, starting_pos=0):
        self._src = source
        self._pos = starting_pos

        def _read(format_):
            size = struct.calcsize(format_)
            try:
                ret = struct.unpack_from(format_, self._src, self._pos)
            except struct.error, e:
                raise IOError(str(e))
            self._pos += size
            return ret
        return _read

    def _pre_cache(self):
        while self._src:
            try:
                ins = self._read_ins()
            except IOError:
                return

            if not ins:
                return

            self._cache.append(ins)

    def _read_ins(self):
        read = self._read
        opcode = read(">B")[0]

        if opcode not in _op_table:
            raise BytecodeError("unknown opcode 0x%X" % opcode)

        instruction = _op_table[opcode]
        name = instruction[0]
        operands = instruction[1]

        final_operands = []
        final_wide = False

        if operands:
            final_operands = [Operand(x[1], read(x[0])[0]) for x in operands]
        # Lookupswitch
        elif opcode == 0xAB:
            # Read and discard the 4-byte alignment padding
            padding = 4 - (self._pos % 4)
            read("%sx" % padding)
            # The default branch offset, and the number of value/offset pairs
            default, npairs = read(">ii")
            final_operands.append(Operand(4, default))

            while npairs:
                final_operands.append(Operand(4, read(">ii")))
                npairs -= 1

        # Tableswitch
        elif opcode == 0xAA:
            padding = 4 - (self._pos % 4)
            read("%sx" % padding)
            default, low, high = read(">iii")
            count = high - low + 1

            final_operands.append(Operand(4, (default, low, high)))

            while count:
                final_operands.append(Operand(4, read(">i")[0]))
                count -= 1

        # Wide
        elif opcode == 0xC4:
            opcode = read(">B")[0]
            name = _op_table[opcode][0]
            final_operands.append(Operand(2, read(">H")[0]))
            # Special case for iinc
            if opcode == 0x84:
                final_operands.append(Operand(3, read(">H")[0]))

            final_wide = True

        ins = Instruction(name, opcode, self._pos, final_wide, final_operands)
        if name not in self._usage:
            self._usage[name] = 1
        else:
            self._usage[name] += 1

        return ins

    def __iter__(self):
        return self.forward()

    def __getitem__(self, index):
        return self._cache[index]

    def __len__(self):
        return len(self._cache)

    def forward(self):
        return self._cache.__iter__()

    def reverse(self):
        return reversed(self._cache)

    @property
    def usage(self):
        """
        Returns a pre-computed dictionary representing the number
        of times (the value) each instruction (the key) is present.
        """
        return self._usage.copy()
