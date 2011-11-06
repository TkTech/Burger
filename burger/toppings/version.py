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

from .topping import Topping


class VersionTopping(Topping):
    """Provides the protocol version."""

    PROVIDES = [
        "version.protocol"
    ]

    DEPENDS = [
        "identify.nethandler",
        "packets.ids",
        "packets.classes"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        versions = aggregate.setdefault("version", {})
        try:
            handshake = aggregate["packets"]["packet"][2]["class"]
            login = aggregate["packets"]["packet"][1]["class"]
        except:
            if verbose:
                print "Unable to find packets needed",
                print "to determine protocol version"
            return

        # client
        if "nethandler.client" in aggregate["classes"]:
            cf = jar.open_class(aggregate["classes"]["nethandler.client"])
            method = cf.methods.find_one(args=(handshake,))
            if method is None:
                return

            lookForVersion = False
            version = None
            for instr in method.instructions:
                if instr.opcode == 187:
                    constant = cf.constants.storage[instr.operands[0][1]]
                    if constant["name"]["value"] == login:
                        lookForVersion = True
                    else:
                        lookForVersion = False
                elif lookForVersion and instr.opcode == 16:
                    version = instr.operands[0][1]
                    break

            if version:
                versions["protocol"] = version

        # server
        elif "nethandler.server" in aggregate["classes"]:
            cf = jar.open_class(aggregate["classes"]["nethandler.server"])
            methods = cf.methods.find(args=(login,))
            version = None
            for method in methods:
                for instr in method.instructions:
                    if instr.opcode == 16:
                        version = instr.operands[0][1]
                    elif instr.opcode == 18 and version:
                        constant = cf.constants[instr.operands[0][1]]
                        if constant["string"]["value"] == "Outdated server!":
                            versions["protocol"] = version
                            return

        elif verbose:
            print "Unable to determine protocol version"
