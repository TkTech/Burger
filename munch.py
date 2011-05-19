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
import json

from collections import deque

from solum import JarFile

def import_toppings(toppings=None):
    """Loads subclasses of Topping.

    :param toppings: An optional list of toppings to load.
    :type toppings: list.
    :returns: list -- found subclasses.
    """
    this_dir = os.path.dirname(__file__)
    toppings_dir = os.path.join(this_dir, "toppings")
    from_list = ["topping"]

    if toppings is not None:
        from_list.extend(toppings)
    else:
        for root, dirs, files in os.walk(toppings_dir):
            for file_ in files:
                if not file_.endswith(".py") or file_.startswith("__"):
                    continue

                from_list.append(file_[:-3])

    imports = __import__("toppings", fromlist=from_list)
    return imports.topping.Topping.__subclasses__()

if __name__ == "__main__":
    try:
        opts, args = getopt.gnu_getopt(
            sys.argv[1:],
            "p:o:v",
            [
                "toppings=",
                "output=", 
                "verbose"
            ]
        )
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    # Default options
    toppings = None
    output = sys.stdout
    verbose = False

    for o, a in opts:
        if o in ("-p", "--toppings"):
            toppings = a.split(",")
        elif o in ("-o", "--output"):
            output = open(a, "ab")
        elif o in ("-v", "--verbose"):
            verbose = True
    
    # Load all the toppings we want
    loaded_toppings = import_toppings(toppings)

    # Builds the dependency dictionary so we can order
    # topping execution.
    topping_provides = {}
    topping_depends = {}
    for topping in loaded_toppings:
        for provided in topping.PROVIDES:
            topping_provides[provided] = topping

        for depends in topping.DEPENDS:
            topping_depends[depends] = topping

    to_be_run = deque(loaded_toppings)
    for dk, dv in topping_depends.iteritems():
        if dk not in topping_provides:
            print "(%s) requires (%s)" % (dv, dk)
            sys.exit(1)

        to_be_run.remove(topping_provides[dk])
        to_be_run.appendleft(topping_provides[dk])

    for arg in args:
        aggregate = {}
        jar = JarFile(arg)

        for topping in to_be_run:
            topping.act(aggregate, jar, verbose)

        json.dump(aggregate, output, sort_keys=True, indent=4)
        output.write("\n")
