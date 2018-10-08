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
import six

try:
    import json
except ImportError:
    import simplejson as json

class LanguageTopping(Topping):
    """Provides the contents of the English language files."""

    PROVIDES = [
        "language"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        aggregate["language"] = {}
        LanguageTopping.load_language(
            aggregate,
            classloader,
            "lang/stats_US.lang",
            verbose
        )
        LanguageTopping.load_language(
            aggregate,
            classloader,
            "lang/en_US.lang",
            verbose
        )
        LanguageTopping.load_language(
            aggregate,
            classloader,
            "assets/minecraft/lang/en_US.lang",
            verbose
        )
        LanguageTopping.load_language(
            aggregate,
            classloader,
            "assets/minecraft/lang/en_us.lang",
            verbose
        )
        LanguageTopping.load_language(
            aggregate,
            classloader,
            "assets/minecraft/lang/en_us.json",
            verbose,
            True
        )

    @staticmethod
    def load_language(aggregate, classloader, path, verbose=False, is_json=False):
        try:
            with classloader.open(path) as fin:
                contents = fin.read().decode("utf-8")
        except:
            if verbose:
                print("Can't find file %s in jar" % path)
            return

        for category, name, value in LanguageTopping.parse_lang(contents, verbose, is_json):
            cat = aggregate["language"].setdefault(category, {})
            cat[name] = value

    @staticmethod
    def parse_lang(contents, verbose, is_json):
        if is_json:
            contents = json.loads(contents)
            for tag, value in six.iteritems(contents):
                category, name = tag.split(".", 1)

                yield (category, name, value)
        else:
            contents = contents.split("\n")
            lineno = 0
            for line in contents:
                lineno = lineno + 1
                line = line.strip()

                if not line:
                    continue
                if line[0] == "#":
                    continue

                if not "=" in line or not "." in line:
                    if verbose:
                        print("Language file line %s is malformed: %s" % (lineno, line))
                    continue

                tag, value = line.split("=", 1)
                category, name = tag.split(".", 1)

                yield (category, name, value)