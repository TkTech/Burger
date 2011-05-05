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
from .particle import Particle

class LanguageParticle(Particle):
    """Provides the contents of the English language files.

    Looks into the contents of en_US.lang and stats_US.lang,
    returning their contents as a list of tuples in the form
    (category, name, value).
    """

    PROVIDES = [
        "lang.stats",
        "lang.achievements",
        "lang.gui"
    ]

    DEPENDS = []

    @staticmethod
    def act(aggregate, jar):
        def load_lang(contents):
            for category, name, value in Particle.parse_lang(contents):
                if category not in aggregate["lang"]:
                    aggregate["lang"][category] = {}

                aggregate["lang"][category][name] = value

        aggregate["lang"] = {}
        load_lang(jar["lang/stats_US.lang"])
        load_lang(jar["lang/en_US.lang"])

