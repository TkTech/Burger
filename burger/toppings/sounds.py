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
import urllib
import re
from xml.sax import ContentHandler, make_parser

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class SoundTopping(Topping):
    """Finds all named sound effects which are both used in the server and
       available for download."""

    PROVIDES = [
        "sounds"
    ]

    DEPENDS = [
        "identify.sounds.list",
        "identify.sounds.event"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        sounds = aggregate.setdefault('sounds', {})

        if not 'sounds.list' in aggregate["classes"]:
            # 1.8 - TODO implement this for 1.8
            return

        soundevent = aggregate["classes"]["sounds.event"]
        cf = ClassFile(StringIO(jar.read(soundevent + ".class")))

        # Find the static sound registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_public and m.access_flags.acc_static)

        sound_name = None
        sound_id = 0
        for ins in method.code.disassemble():
            if ins.mnemonic in ('ldc', 'ldc_w'):
                const = cf.constants.get(ins.operands[0].value)
                sound_name = const.string.value
            elif ins.mnemonic == 'invokestatic':
                sounds[sound_name] = {
                    'name': sound_name,
                    'id': sound_id
                }
                sound_id += 1

        # Get fields now
        soundlist = aggregate["classes"]["sounds.list"]
        lcf = ClassFile(StringIO(jar.read(soundlist + ".class")))

        method = lcf.methods.find_one(name="<clinit>")
        for ins in method.code.disassemble():
            if ins.mnemonic in ('ldc', 'ldc_w'):
                const = lcf.constants.get(ins.operands[0].value)
                sound_name = const.string.value
            elif ins.mnemonic == "putstatic":
                if sound_name is None or sound_name == "Accessed Sounds before Bootstrap!":
                    continue
                const = lcf.constants.get(ins.operands[0].value)
                field = const.name_and_type.name.value
                sounds[sound_name]["field"] = field
