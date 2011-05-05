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

from collections import deque, defaultdict

from solum import JarFile

def import_particles(particles=None):
    """Loads subclasses of Particle.

    :param particles: An optional list of particles to load.
    :type particles: list.
    :returns: list -- found subclasses.
    """
    this_dir = os.path.dirname(__file__)
    particles_dir = os.path.join(this_dir, "particles")
    from_list = ["particle"]

    if particles is not None:
        from_list.extend(particles)
    else:
        for root, dirs, files in os.walk(particles_dir):
            for file_ in files:
                if not file_.endswith(".py") or file_.startswith("__"):
                    continue

                from_list.append(file_[:-3])

    imports = __import__("particles", fromlist=from_list)
    return imports.particle.Particle.__subclasses__()

if __name__ == "__main__":
    try:
        opts, args = getopt.gnu_getopt(
            sys.argv[1:],
            "p:o:",
            ["particles=", "output="]
        )
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(1)

    # Default options
    particles = None
    output = sys.stdout

    for o, a in opts:
        if o in ("-p", "--particles"):
            particles = a.split(",")
        elif o in ("-o", "--output"):
            output = open(a, "ab")
    
    # Load all the particles we want
    loaded_particles = import_particles(particles)

    # Builds the dependency dictionary so we can order
    # particle execution.
    particle_provides = {}
    particle_depends = {}
    for particle in loaded_particles:
        for provided in particle.PROVIDES:
            particle_provides[provided] = particle

        for depends in particle.DEPENDS:
            particle_depends[depends] = particle

    to_be_run = deque(loaded_particles)
    for dk, dv in particle_depends.iteritems():
        if dk not in particle_provides:
            print "(%s) requires (%s)" % (dv, dk)
            sys.exit(1)

        to_be_run.remove(particle_provides[dk])
        to_be_run.appendleft(particle_provides[dk])

    for arg in args:
        aggregate = defaultdict(dict)
        jar = JarFile(arg)

        for particle in to_be_run:
            particle.act(aggregate, jar)

        json.dump(aggregate, output, sort_keys=True, indent=4)
        output.write("\n")
