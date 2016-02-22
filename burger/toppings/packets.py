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

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class PacketsTopping(Topping):
    """Provides minimal information on all network packets."""

    PROVIDES = [
        "packets.ids",
        "packets.classes",
        "packets.directions"
    ]

    DEPENDS = [
        "identify.packet.connectionstate",
        "identify.packet.packetbuffer"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        connectionstate = aggregate["classes"]["packet.connectionstate"]
        cf = ClassFile(StringIO(jar.read(connectionstate + ".class")))

        # Find the static constructor
        method = cf.methods.find_one(name="<clinit>")
        stack = []

        packets = aggregate.setdefault("packets", {})
        packet = packets.setdefault("packet", {})
        states = packets.setdefault("states", {})
        directions = packets.setdefault("directions", {})

        # TODO: this seems like a bad way of implementing this, since I only
        # want to extract enum constant names and types.  I don't know how to
        # do it better, though.
        NUM_STATES = 4

        for ins in method.code.disassemble():
            if ins.mnemonic == "new":
                const = cf.constants.get(ins.operands[0].value)
                state_class = const.name.value
            elif ins.mnemonic == "ldc":
                const = cf.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantString):
                    state_name = const.string.value
            elif ins.mnemonic == "putstatic":
                const = cf.constants.get(ins.operands[0].value)
                state_field = const.name_and_type.name.value
                
                states[state_name] = {
                    "class": state_class,
                    "field": state_field,
                    "name": state_name
                }
            if len(states) >= NUM_STATES:
                break

        register_method = cf.methods.find_one(returns="L" + connectionstate + ";",
                f=lambda x: x.access_flags.acc_protected and not x.access_flags.acc_static)
        assert len(register_method.args) == 2
        assert register_method.args[1].name == "java/lang/Class"
        direction_class = register_method.args[0].name

        #TODO: Again, hardcoded - finding directions
        directions_by_field = {}
        NUM_DIRECTIONS = 2

        direction_class_file = ClassFile(StringIO(jar.read(direction_class + ".class")))
        direction_init_method = direction_class_file.methods.find_one("<clinit>")
        for ins in direction_init_method.code.disassemble():
            if ins.mnemonic == "new":
                const = direction_class_file.constants.get(ins.operands[0].value)
                dir_class = const.name.value
            elif ins.mnemonic == "ldc":
                const = direction_class_file.constants.get(ins.operands[0].value)
                if isinstance(const, ConstantString):
                    dir_name = const.string.value
            elif ins.mnemonic == "putstatic":
                const = direction_class_file.constants.get(ins.operands[0].value)
                dir_field = const.name_and_type.name.value
                
                directions[dir_name] = {
                    "class": dir_class,
                    "field": dir_field,
                    "name": dir_name
                }
                directions_by_field[dir_field] = directions[dir_name]
            if len(directions) >= NUM_DIRECTIONS:
                break

        for state_name in states:
            state = states[state_name] #TODO: Can I just iterate over the values directly?
            cf = ClassFile(StringIO(jar.read(state["class"] + ".class")))
            method = cf.methods.find_one("<init>")
            cur_id = 0
            for ins in method.code.disassemble():
                if ins.mnemonic == "getstatic":
                    const = cf.constants.get(ins.operands[0].value)
                    field = const.name_and_type.name.value
                    stack.append(directions_by_field[field])
                elif ins.mnemonic in ("ldc", "ldc_w"):
                    const = cf.constants.get(ins.operands[0].value)
                    if isinstance(const, ConstantClass):
                        stack.append("%s.class" % const.name.value)
                elif ins.mnemonic == "invokevirtual":
                    # TODO: Currently assuming that the method is the register one which seems to be correct but may be wrong
                    direction = stack[0]["name"]
                    packet["%s_%s" % (state_name, cur_id)] = {
                        "id": cur_id,
                        "class": stack[1],
                        "from_client": direction == "SERVERBOUND",
                        "from_server": direction == "CLIENTBOUND"
                    }
                    stack = []
                    cur_id = cur_id + 1

        info = packets.setdefault("info", {})
        info["count"] = len(packet)
