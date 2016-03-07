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
try:
    import json
except ImportError:
    import simplejson as json

from .topping import Topping

from jawa.constants import *
from jawa.cf import ClassFile

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

ASSET_INDEX = "https://s3.amazonaws.com/Minecraft.Download/indexes/1.9.json"
RESOURCES_SITE = "http://resources.download.minecraft.net/%s/%s"

def get_asset_index(url=ASSET_INDEX):
    """Downloads the Minecraft asset index"""
    index_file = urllib.urlopen(url)
    try:
        return json.load(index_file)
    finally:
        index_file.close()

def get_sounds(asset_index, resources_site=RESOURCES_SITE):
    """Downloads the sounds.json file from the assets index"""
    sounds_hash = asset_index["objects"]["minecraft/sounds.json"]["hash"]
    sounds_url = resources_site % (sounds_hash[0:2], sounds_hash)

    sounds_file = urllib.urlopen(sounds_url)

    try:
        return json.load(sounds_file)
    finally:
        sounds_file.close()

class SoundTopping(Topping):
    """Finds all named sound effects which are both used in the server and
       available for download."""

    PROVIDES = [
        "sounds"
    ]

    DEPENDS = [
        "identify.sounds.list",
        "identify.sounds.event",
        "language"
    ]

    @staticmethod
    def act(aggregate, jar, verbose=False):
        sounds = aggregate.setdefault('sounds', {})
        assets = get_asset_index()
        sounds_json = get_sounds(assets)

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
                sound = {
                    "name": sound_name,
                    "id": sound_id
                }
                sound_id += 1

                if sound_name in sounds_json:
                    json_sound = sounds_json[sound_name]
                    if "sounds" in json_sound:
                        sound["sounds"] = []
                        for path in json_sound["sounds"]:
                            data = {
                                "name": path
                            }
                            asset_key = "minecraft/sounds/%s.ogg" % path
                            if asset_key in assets["objects"]:
                                data["hash"] = assets["objects"][asset_key]["hash"]
                            sound["sounds"].append(data)
                    if "subtitle" in json_sound:
                        subtitle = json_sound["subtitle"]
                        sound["subtitle_key"] = subtitle
                        # Get rid of the starting key since the language topping
                        # splits it off like that
                        subtitle_trimmed = subtitle[len("subtitles."):]
                        if subtitle_trimmed in aggregate["language"]["subtitles"]:
                            sound["subtitle"] = aggregate["language"]["subtitles"][subtitle_trimmed]

                sounds[sound_name] = sound

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
