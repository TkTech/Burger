from .topping import Topping

try:
    import json
except ImportError:
    import simplejson as json

class TagsTopping(Topping):
    """Provides a list of all block and item tags"""

    PROVIDES = [
        "tags"
    ]
    DEPENDS = []

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        tags = aggregate.setdefault("tags", {})
        prefix = "data/minecraft/tags/"
        suffix = ".json"
        for path in classloader.path_map:
            if not path.startswith(prefix) or not path.endswith(suffix):
                continue
            key = path[len(prefix):-len(suffix)]
            type, name = key.split("/", 2)
            data = json.loads(classloader.path_map[path].read(path))
            data["type"] = type
            data["name"] = name
            tags[key] = data