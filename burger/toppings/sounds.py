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

try:
    import json
except ImportError:
    import simplejson as json

import traceback

import six
import six.moves.urllib.request

from burger import website
from .topping import Topping

from jawa.constants import *

RESOURCES_SITE = "http://resources.download.minecraft.net/%(short_hash)s/%(hash)s"

def get_sounds(asset_index, resources_site=RESOURCES_SITE):
    """Downloads the sounds.json file from the assets index"""
    hash = asset_index["objects"]["minecraft/sounds.json"]["hash"]
    short_hash = hash[0:2]
    sounds_url = resources_site % {'hash': hash, 'short_hash': short_hash}

    sounds_file = six.moves.urllib.request.urlopen(sounds_url)

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
        "version.name",
        "language"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        sounds = aggregate.setdefault('sounds', {})

        if 'sounds.event' not in aggregate["classes"]:
            # 1.8 - TODO implement this for 1.8
            if verbose:
                print("Not enough information to run sounds topping; missing sounds.event")
            return

        try:
            version_meta = website.get_version_meta(aggregate["version"]["id"], verbose)
        except Exception as e:
            if verbose:
                print("Error: Failed to download version meta for sounds: %s" % e)
                traceback.print_exc()
            return
        try:
            assets = website.get_asset_index(version_meta, verbose)
        except Exception as e:
            if verbose:
                print("Error: Failed to download asset index for sounds: %s" % e)
                traceback.print_exc()
            return
        try:
            sounds_json = get_sounds(assets)
        except Exception as e:
            if verbose:
                print("Error: Failed to download sound list: %s" % e)
                traceback.print_exc()
            return

        soundevent = aggregate["classes"]["sounds.event"]
        cf = classloader[soundevent]

        # Find the static sound registration method
        method = cf.methods.find_one(args='', returns="V", f=lambda m: m.access_flags.acc_static)

        sound_name = None
        sound_id = 0
        for ins in method.code.disassemble():
            if ins in ('ldc', 'ldc_w'):
                const = ins.operands[0]
                sound_name = const.string.value
            elif ins == 'invokestatic':
                sound = {
                    "name": sound_name,
                    "id": sound_id
                }
                sound_id += 1

                if sound_name in sounds_json:
                    json_sound = sounds_json[sound_name]
                    if "sounds" in json_sound:
                        sound["sounds"] = []
                        for value in json_sound["sounds"]:
                            data = {}
                            if isinstance(value, six.string_types):
                                data["name"] = value
                                path = value
                            elif isinstance(value, dict):
                                # Guardians use this to have a reduced volume
                                data = value
                                path = value["name"]
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
        lcf = classloader[soundlist]

        method = lcf.methods.find_one(name="<clinit>")
        for ins in method.code.disassemble():
            if ins in ('ldc', 'ldc_w'):
                const = ins.operands[0]
                sound_name = const.string.value
            elif ins == "putstatic":
                if sound_name is None or sound_name == "Accessed Sounds before Bootstrap!":
                    continue
                const = ins.operands[0]
                field = const.name_and_type.name.value
                sounds[sound_name]["field"] = field
