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
from solum import ClassFile, ConstantType

from .particle import Particle

class PacketsParticle(Particle):
    PROVIDES = [
        "packets.ids",
        "packets.classes",
        "packets.directions"
    ]

    DEPENDS = [
        "identify.packet.superclass"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        # Find and open the packet superclass
        superclass = aggregate["classes"]["packet.superclass"]
        cf = ClassFile(jar["%s.class" % superclass], str_as_buffer=True)

        # Find the static constructor
        method = cf.methods.find_one(name="<clinit>")
        stack = []

        packets = aggregate.setdefault("packets", {})
        packet = packets.setdefault("packet", {})

        for ins in method.instructions:
            # Pushes an integer constant onto the stack
            if ins.name.startswith("iconst"):
                stack.append(int(ins.name[-1]))
            # Pushes a byte or short to the stack
            elif ins.name.endswith("ipush"):
                stack.append(ins.operands[0][1])
            # Loads an entry from the constant pool onto the stack
            elif ins.name == "ldc":
                const_i = ins.operands[0][1]
                const = cf.constants[const_i]
                name = const["name"]["value"]

                client = stack.pop()
                server = stack.pop()
                id_ = stack.pop()

                packet[id_] = {
                    "id": id_,
                    "class": name,
                    "from_client": bool(client),
                    "from_server": bool(server)
                }

        info = packets.setdefault("info", {})
        info["count"] = len(packet)

