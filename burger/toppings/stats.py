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

class StatsTopping(Topping):
    """Gets all statistics and statistic related strings."""

    PROVIDES = [
        "stats.statistics",
        "stats.achievements"
    ]

    DEPENDS = [
        "language"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        stats = aggregate.setdefault("stats", {})
        if "stat" in aggregate["language"]:
            stat_lang = aggregate["language"]["stat"]

            for sk, sv in six.iteritems(stat_lang):
                item = stats.setdefault(sk, {})
                item["desc"] = sv

        achievements = aggregate.setdefault("achievements", {})
        if "achievement" in aggregate["language"]:
            achievement_lang = aggregate["language"]["achievement"]

            for ak, av in six.iteritems(achievement_lang):
                real_name = ak[:-5] if ak.endswith(".desc") else ak
                item = achievements.setdefault(real_name, {})
                if ak.endswith(".desc"):
                    item["desc"] = av
                else:
                    item["name"] = av
