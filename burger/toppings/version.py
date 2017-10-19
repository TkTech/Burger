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

class VersionTopping(Topping):
    """Provides the protocol version."""

    PROVIDES = [
        "version.protocol",
        "version.name"
    ]

    DEPENDS = [
        "identify.nethandler.server",
        "identify.anvilchunkloader"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        VersionTopping.get_protocol_version(aggregate, jar, verbose)
        VersionTopping.get_data_version(aggregate, jar, verbose)

    @staticmethod
    def get_protocol_version(aggregate, jar, verbose):
        versions = aggregate.setdefault("version", {})
        if "nethandler.server" in aggregate["classes"]:
            nethandler = aggregate["classes"]["nethandler.server"] + ".class"
            cf = ClassFile(StringIO(jar.read(nethandler)))
            version = None
            looking_for_version_name = False
            for method in cf.methods:
                for instr in method.code.disassemble():
                    if instr.mnemonic in ("bipush", "sipush"):
                        version = instr.operands[0].value
                    elif instr.mnemonic.startswith("iconst"):
                        version = int(instr.mnemonic[-1])
                    elif instr.mnemonic == "ldc" and version is not None:
                        constant = cf.constants.get(instr.operands[0].value)
                        if isinstance(constant, ConstantString):
                            str = constant.string.value

                            if "multiplayer.disconnect.outdated_client" in str:
                                versions["protocol"] = version
                                looking_for_version_name = True
                                continue
                            elif looking_for_version_name:
                                versions["name"] = str
                                return
                            elif "Outdated server!" in str:
                                versions["protocol"] = version
                                versions["name"] = \
                                    str[len("Outdated server! I'm still on "):]
                                return
        elif verbose:
            print "Unable to determine protocol version"

    @staticmethod
    def get_data_version(aggregate, jar, verbose):
        if "anvilchunkloader" in aggregate["classes"]:
            anvilchunkloader = aggregate["classes"]["anvilchunkloader"] + ".class"
            cf = ClassFile(StringIO(jar.read(anvilchunkloader)))

            for method in cf.methods:
                next_ins_is_version = False
                for ins in method.code.disassemble():
                    if ins.mnemonic in ("ldc", "ldc_w"):
                        const = cf.constants.get(ins.operands[0].value)
                        if isinstance(const, ConstantString):
                            if const.string.value == "DataVersion":
                                next_ins_is_version = True
                        elif isinstance(const, ConstantInteger):
                            if next_ins_is_version:
                                aggregate["version"]["data"] = const.value
                            break
                    elif not next_ins_is_version:
                        pass
                    elif ins.mnemonic in ("bipush", "sipush"):
                        aggregate["version"]["data"] = ins.operands[0].value
                        break
                    elif ins.mnemonic.startswith("iconst"):
                        aggregate["version"]["data"] = int(ins.mnemonic[-1])
                        break

                if next_ins_is_version:
                    break
        elif verbose:
            print "Unable to determine data version"
