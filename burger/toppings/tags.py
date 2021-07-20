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
            idx = key.find("/")
            type, name = key[:idx], key[idx + 1:]
            with classloader.open(path) as fin:
                data = json.load(fin)
            data["type"] = type
            data["name"] = name
            tags[key] = data

        # Tags can reference other tags -- flatten that out.
        flattening = set()
        flattened = set()
        def flatten_tag(name):
            if name in flattening:
                if verbose:
                    print("Already flattening " + name + " -- is there a cycle?", flattening)
                return
            if name in flattened:
                return

            flattening.add(name)

            tag = tags[name]
            values = tag["values"]
            new_values = []
            for entry in values:
                if entry.startswith("#"):
                    assert entry.startswith("#minecraft:")
                    referenced_tag_name = tag["type"] + "/" + entry[len("#minecraft:"):]
                    flatten_tag(referenced_tag_name)
                    new_values.extend(tags[referenced_tag_name]["values"])
                else:
                    new_values.append(entry)
            tag["values"] = new_values

            flattening.discard(name)
            flattened.add(name)

        for name in tags:
            flatten_tag(name)
