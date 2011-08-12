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
import getpass

try:
    import json
except ImportError:
    import simplejson as json

from collections import deque

from solum import JarFile

from burger.website import Website


def import_toppings(toppings=None):
    """
    Attempts to imports either a list of toppings or, if none were
    given, attempts to load all available toppings.
    """
    this_dir = os.path.dirname(__file__)
    toppings_dir = os.path.join(this_dir, "burger", "toppings")
    from_list = ["topping"]

    if toppings is not None:
        from_list.extend(toppings)
    else:
        # If we weren't given a list of toppings to load,
        # traverse the toppings directory and import everything.
        for root, dirs, files in os.walk(toppings_dir):
            for file_ in files:
                if not file_.endswith(".py"):
                    continue
                elif file_.startswith("__"):
                    continue

                from_list.append(file_[:-3])

    imports = __import__("burger.toppings", fromlist=from_list)
    return imports.topping.Topping.__subclasses__()

if __name__ == "__main__":
    try:
        opts, args = getopt.gnu_getopt(
            sys.argv[1:],
            "t:o:vu:p:dlc",
            [
                "toppings=",
                "output=",
                "verbose",
                "username=",
                "password=",
                "download",
                "list",
                "compact"
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

    # Load all the toppings we want
    loaded_toppings = import_toppings(toppings)

    # List all of the available toppings,
    # as well as their docstring if available.
    if list_toppings:
        for topping in loaded_toppings:
            print topping
            if topping.__doc__:
                print " -- %s" % topping.__doc__
        sys.exit(0)

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

    for topping in topping_nodes:
        for dependency in topping.depends:
            if not dependency in topping_provides:
                print "(%s) requires (%s)" % (topping, dependency)
                sys.exit(1)
            topping.childs.append(topping_provides[dependency])

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
        def reporthook(chunks, chunksize, total):
            if not verbose:
                return

            percent = float(chunks) * float(chunksize) / float(total)
            percent *= 100
            sys.stdout.write("\rDownloading... %s%%" % int(percent))
            sys.stdout.flush()

        client_path = Website.client_jar(reporthook=reporthook)
        if verbose:
            sys.stdout.write("\n")
        jarlist.append(client_path)

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
        json.dump(summary, output, sort_keys=True, indent=4)
    else:
        json.dump(summary, output)

    if download_fresh_jar:
        os.remove(client_path)
