from .topping import Topping

class TagsTopping(Topping):
    """Provides a list of all particle types"""

    PROVIDES = [
        "particletypes"
    ]
    DEPENDS = ["identify.particletypes"]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        particletypes = []
        cf = classloader[aggregate["classes"]["particletypes"]]
        ops = tuple(cf.methods.find_one(name = '<clinit>').code.disassemble())
        for idx, op in enumerate(ops):
            if 'ldc' in op.name:
                str_val = op.operands[0].string.value

                # Enum identifiers in older version of MC are all uppercase,
                # these are distinct from the particletype strings we're
                # collecting here.
                if str_val.isupper():
                    continue

                # This instruction sequence is unique to particle type fields
                if ops[idx + 1].name in ('bipush', 'getstatic'):
                    particletypes.append(str_val)

        aggregate['particletypes'] = particletypes
