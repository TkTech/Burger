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
from xml.sax import ContentHandler, make_parser

from solum import ClassFile, ConstantType

from .topping import Topping


def load_resource_list():
    parser = make_parser()
    handler = FindSounds()
    parser.setContentHandler(handler)
    f = urllib.urlopen("http://s3.amazonaws.com/MinecraftResources/")
    try:
        parser.parse(f)
    finally:
        f.close()
    return handler.sounds


class FindSounds(ContentHandler):
    def __init__(self):
        self.sounds = []
        self.inside_key = False
        self.key = ""

    def startElement(self, name, attrs):
        if name == "Key":
            self.inside_key = True

    def endElement(self, name):
        if name == "Key":
            self.parse_key(self.key)
            self.key = ""
            self.inside_key = False

    def characters(self, characters):
        if self.inside_key:
            self.key += characters

    def parse_key(self, key):
        if "." not in key:
            return
        key, _, extension = str(key).partition(".")
        package, _, name = key.replace("/", ".").partition(".")
        self.sounds.append({'package': package,
                            'name': name,
                            'format': extension})


class SoundTopping(Topping):
    """Finds all named sound effects which are both used in the server and
       available for download."""

    PROVIDES = [
        "sounds"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar, verbose=False):
        sounds = aggregate.setdefault('sounds', {})
        try:
            resources = load_resource_list()
        except:
            if verbose:
                print "Unable to load resource list from mojang."
            return
        strings = []
        for cf in jar.classes:
            strings += [c['string']['value'] for c in cf.constants.find(
                ConstantType.STRING,
                lambda c: "." in c['string']['value']
            )]
        for resource in resources:
            if resource['name'] in strings:
                sounds[resource['name']] = resource
