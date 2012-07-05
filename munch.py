#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import json
import getopt

from jawa.core.jf import JarFile

from burger.eat import eat_jar


def do_burger(jar_path):
    with JarFile(jar_path) as jf:
        return eat_jar(jf)


def main(argv):
    try:
        opts, args = getopt.gnu_getopt(argv[1:], '', [

        ])
    except getopt.GetoptError, e:
        print(str(e))
        return 1

    final_output = []
    for jar in args:
        final_output.append(do_burger(jar))

    print(json.dumps(final_output, sort_keys=True, indent=4))

if __name__ == '__main__':
    sys.exit(main(sys.argv))
