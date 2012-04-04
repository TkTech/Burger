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
import os
import sys
import getopt
import urllib

try:
    import json
except ImportError:
    import simplejson as json

from collections import deque

from solum import JarFile

from burger.website import Website
from burger.roundedfloats import transform_floats


def import_toppings():
    """
    Attempts to imports either a list of toppings or, if none were
    given, attempts to load all available toppings.
    """
    this_dir = os.path.dirname(__file__)
    toppings_dir = os.path.join(this_dir, "burger", "toppings")
    from_list = []

    # Traverse the toppings directory and import everything.
    for root, dirs, files in os.walk(toppings_dir):
        for file_ in files:
            if not file_.endswith(".py"):
                continue
            elif file_.startswith("__"):
                continue
            elif file_ == "topping.py":
                continue

            from_list.append(file_[:-3])

    from burger.toppings.topping import Topping
    toppings = {}
    count = 0

    for topping in from_list:
        __import__("burger.toppings.%s" % topping)
        subclasses = Topping.__subclasses__()
        if len(subclasses) == count:
            print "Topping '%s' contains no topping" % topping
        elif len(subclasses) >= count + 2:
            print "Topping '%s' contains more than one topping" % topping
        else:
            toppings[topping] = subclasses[-1]
        count = len(subclasses)

    return toppings

if __name__ == "__main__":
    try:
        opts, args = getopt.gnu_getopt(
            sys.argv[1:],
            "t:o:vu:p:dlcs:",
            [
                "toppings=",
                "output=",
                "verbose",
                "username=",
                "password=",
                "download",
                "list",
                "compact",
                "url=",
                "source="
            ]
        )
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    # Default options
    toppings = None
    output = sys.stdout
    verbose = False
    username = None
    password = None
    download_fresh_jar = False
    list_toppings = False
    compact = False
    url = None

    for o, a in opts:
        if o in ("-t", "--toppings"):
            toppings = a.split(",")
        elif o in ("-o", "--output"):
            output = open(a, "ab")
        elif o in ("-v", "--verbose"):
            verbose = True
        elif o in ("-c", "--compact"):
            compact = True
        elif o in ("-u", "--username"):
            username = a
        elif o in ("-p", "--password"):
            password = a
        elif o in ("-d", "--download"):
            download_fresh_jar = True
        elif o in ("-l", "--list"):
            list_toppings = True
        elif o in ("-s", "--url", "--source"):
            url = a

    # Load all toppings
    all_toppings = import_toppings()

    # List all of the available toppings,
    # as well as their docstring if available.
    if list_toppings:
        for topping in all_toppings:
            print "%s" % topping
            if all_toppings[topping].__doc__:
                print " -- %s\n" % all_toppings[topping].__doc__
        sys.exit(0)

    # Get the toppings we want
    if toppings is None:
        loaded_toppings = all_toppings.values()
    else:
        loaded_toppings = []
        for topping in toppings:
            if topping not in all_toppings:
                print "Topping '%s' doesn't exist" % topping
            else:
                loaded_toppings.append(all_toppings[topping])

    class DependencyNode:
        def  __init__(self, topping):
            self.topping = topping
            self.provides = topping.PROVIDES
            self.depends = topping.DEPENDS
            self.childs = []

        def __repr__(self):
            return str(self.topping)

    # Order topping execution by building dependency tree
    topping_nodes = []
    topping_provides = {}
    for topping in loaded_toppings:
        topping_node = DependencyNode(topping)
        topping_nodes.append(topping_node)
        for provides in topping_node.provides:
            topping_provides[provides] = topping_node

    # Include missing dependencies
    for topping in topping_nodes:
        for dependency in topping.depends:
            if not dependency in topping_provides:
                for other_topping in all_toppings.values():
                    if dependency in other_topping.PROVIDES:
                        topping_node = DependencyNode(other_topping)
                        topping_nodes.append(topping_node)
                        for provides in topping_node.provides:
                            topping_provides[provides] = topping_node

    # Find dependency childs
    for topping in topping_nodes:
        for dependency in topping.depends:
            if not dependency in topping_provides:
                print "(%s) requires (%s)" % (topping, dependency)
                sys.exit(1)
            if not topping_provides[dependency] in topping.childs:
                topping.childs.append(topping_provides[dependency])

    # Run leaves first
    to_be_run = []
    while len(topping_nodes) > 0:
        stuck = True
        for topping in topping_nodes:
            if len(topping.childs) == 0:
                stuck = False
                for parent in topping_nodes:
                    if topping in parent.childs:
                        parent.childs.remove(topping)
                to_be_run.append(topping.topping)
                topping_nodes.remove(topping)
        if stuck:
            print "Can't resolve dependencies"
            sys.exit(1)

    jarlist = args

    # Should we download a new copy of the JAR directly
    # from minecraft.net?
    if download_fresh_jar:
        client_path = Website.client_jar()
        jarlist.append(client_path)

    # Download a JAR from the given URL
    if url:
        url_path = urllib.urlretrieve(url)[0]
        jarlist.append(url_path)

    summary = []

    for path in jarlist:
        jar = JarFile(path)
        aggregate = {
            "source": {
                "file": path,
                "classes": jar.class_count,
                "other": jar.count,
                "size": os.path.getsize(path)
            }
        }

        for topping in to_be_run:
            topping.act(aggregate, jar, verbose)

        summary.append(aggregate)

    if not compact:
        json.dump(transform_floats(summary), output, sort_keys=True, indent=4)
    else:
        json.dump(transform_floats(summary), output)

    # Cleanup temporary downloads
    if download_fresh_jar:
        os.remove(client_path)
    if url:
        os.remove(url_path)
