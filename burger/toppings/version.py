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
        "version.protocol"
    ]

    DEPENDS = [
        "identify.nethandler",
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        versions = aggregate.setdefault("version", {})
        if "nethandler.server" in aggregate["classes"]:
            nethandler = aggregate["classes"]["nethandler.server"] + ".class"
            cf = ClassFile(StringIO(jar.read(nethandler)))
            version = None
            for method in cf.methods:
                for instr in method.code.disassemble():
                    if instr.mnemonic == "bipush":
                        version = instr.operands[0].value
                    elif instr.mnemonic == "ldc" and version is not None:
                        constant = cf.constants.get(instr.operands[0].value)
                        if isinstance(constant, ConstantString):
                            if "Outdated server!" in constant.string.value:
                                versions["protocol"] = version
                                return
        elif verbose:
            print "Unable to determine protocol version"
