import six

from .topping import Topping
from burger.util import WalkerCallback, class_from_invokedynamic, walk_method

from jawa.constants import *
from jawa.util.descriptor import method_descriptor

class EntityMetadataTopping(Topping):
    PROVIDES = [
        "entities.metadata"
    ]

    DEPENDS = [
        "entities.entity",
        "identify.metadata"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        # This approach works in 1.9 and later; before then metadata was different.
        entities = aggregate["entities"]["entity"]

        datamanager_class = aggregate["classes"]["metadata"]
        datamanager_cf = classloader[datamanager_class]
        register_method = datamanager_cf.methods.find_one(f=lambda m: len(m.args) == 2 and m.args[0].name == "java/lang/Class")
        dataparameter_class = register_method.returns.name
        dataserializer_class = register_method.args[1].name

        entity_classes = {e["class"]: e["name"] for e in six.itervalues(entities)}
        parent_by_class = {}
        metadata_by_class = {}

        def fill_class(cls):
            # Returns the starting index for metadata in subclasses of cls
            if cls == "java/lang/Object":
                return 0
            if cls in metadata_by_class:
                return len(metadata_by_class[cls]) + fill_class(parent_by_class[cls])

            cf = classloader[cls]
            super = cf.super_.name.value
            parent_by_class[cls] = super
            index = fill_class(super)

            metadata = []
            for field in cf.fields.find(type_="L" + dataparameter_class + ";"):
                entry = {
                    "field": field.name.value,
                    "type": field.attributes.find_one(name="Signature").signature.value[4:-2],
                    "index": index
                }
                index += 1
                metadata.append(entry)

            metadata_by_class[cls] = metadata

            return index

        for cls in six.iterkeys(entity_classes):
            fill_class(cls)

        for e in six.itervalues(entities):
            cls = e["class"]
            metadata = e["metadata"] = []

            if metadata_by_class[cls]:
                metadata.append({
                    "class": cls,
                    "data": metadata_by_class[cls]
                })

            cls = parent_by_class[cls]
            while cls not in entity_classes and cls != "java/lang/Object" :
                # Add metadata from _abstract_ parent classes, at the start
                if metadata_by_class[cls]:
                    metadata.insert(0, {
                        "class": cls,
                        "data": metadata_by_class[cls]
                    })
                cls = parent_by_class[cls]

            # And then, add a marker for the concrete parent class.
            if cls in entity_classes:
                # Always do this, even if the immediate concrete parent has no metadata
                metadata.insert(0, {
                    "class": cls,
                    "entity": entity_classes[cls]
                })
