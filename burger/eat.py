# -*- coding: utf8 -*-
from jawa.core import constants


class Burger(object):
    def __init__(self, jf):
        self.jf = jf
        self._cf_cache = {}
        self._output = {}
        self._identify_core_classes()

    def _identify_core_classes(self):
        """
        Loops over all of the classes in the Jar looking for standard base
        classes or other classes needed by further passes.
        """
        out = self._output.setdefault('classes', {})

        def identify(class_file):
            # We can identify almost every class we need just by
            # looking for consistent strings.
            matches = (
                ('when adding', 'block.superclass'),
                ('Duplicate packet', 'packet.superclass'),
                ('X#X', 'recipe.superclass'),
                ('CONFLICT @', 'item.superclass'),
                ('Skipping Entity with id', 'entity.list'),
                ('Outdated client!', 'nethandler.server'),
                ('Plains', 'biome.superclass')
            )
            for c in class_file.constants.find(constants.ConstantString):
                value = c.string
                for match, match_name in matches:
                    if match not in value:
                        continue

                    out[match_name] = class_file.this.name
                    return

        for path in self.jf.regex('.+\.class'):
            identify(self.get_class(path))

    def get_class(self, path):
        """
        Returns the class for the given JAR path. Since we perform multiple
        passes, we use this to cache the ClassFile objects as needed.
        """
        if path not in self._cf_cache:
            self._cf_cache[path] = self.jf.open_class(path)
        return self._cf_cache[path]

    def final(self):
        return self._output


def eat_jar(jf):
    bg = Burger(jf)
    return bg.final()
