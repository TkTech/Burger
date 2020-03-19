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

from .topping import Topping

from jawa.constants import *

from burger.util import *

def packet_name(packet):
    return "%s_%s_%02X" % (packet["state"], packet["direction"], packet["id"])

class PacketsTopping(Topping):
    """Provides minimal information on all network packets."""

    PROVIDES = [
        "packets.ids",
        "packets.classes",
        "packets.directions"
    ]

    DEPENDS = [
        "identify.packet.connectionstate",
        "identify.packet.packetbuffer"
    ]

    @staticmethod
    def act(aggregate, classloader, verbose=False):
        connectionstate = aggregate["classes"]["packet.connectionstate"]
        cf = classloader[connectionstate]

        # Find the static constructor
        method = cf.methods.find_one(name="<clinit>")
        stack = []

        packets = aggregate.setdefault("packets", {})
        packet = packets.setdefault("packet", {})
        states = packets.setdefault("states", {})
        directions = packets.setdefault("directions", {})

        # There are 3 (post-netty) formats that the registration code takes:
        # - The 1.7 format (13w41a through 1.7.10 and 14w21b)
        # - The 1.8 format (14w25a through 1.14.4)
        # - The 1.15 format (19w34a+)
        # These can be conveniently decided by the number of protected instance
        # methods that return ConnectionState itself.
        register_methods = list(cf.methods.find(returns="L" + connectionstate + ";",
                f=lambda x: x.access_flags.acc_protected and not x.access_flags.acc_static))

        if len(register_methods) == 2:
            PacketsTopping.parse_17_format(classloader, connectionstate, register_methods, directions, states, packet, verbose)
        elif len(register_methods) == 1:
            PacketsTopping.parse_18_format(classloader, connectionstate, register_methods[0], directions, states, packet, verbose)
        elif len(register_methods) == 0:
            PacketsTopping.parse_115_format(classloader, connectionstate, directions, states, packet, verbose)

        info = packets.setdefault("info", {})
        info["count"] = len(packet)

    @staticmethod
    def parse_17_format(classloader, connectionstate, register_methods, directions, states, packets, verbose):
        # The relevant code looks like this:
        """
        enum EnumConnectionState { // eo in 1.7.10
            HANDSHAKING(-1) {{ // a (ep)
                this.registerServerbound(0, C00Handshake.class);
            }},
            PLAY(0) {{ // b (eq)
                this.registerClientbound(0, S00PacketKeepAlive.class);
                this.registerClientbound(1, S01PacketJoinGame.class);
                this.registerClientbound(2, S02PacketChat.class);
                this.registerClientbound(3, S03PacketTimeUpdate.class);
                // ...
                this.registerServerbound(0, C00PacketKeepAlive.class);
                this.registerServerbound(1, C01PacketChatMessage.class);
                this.registerServerbound(2, C02PacketUseEntity.class);
                this.registerServerbound(3, C03PacketPlayer.class);
                // ...
            }},
            STATUS(1) {{ // c (er)
                // ...
            }},
            LOGIN(2) {{ // d (es)
                // ...
            }};
            // ...
            private final com.google.common.collect.BiMap<Integer, Class> serverboundPackets; // h
            private final com.google.common.collect.BiMap<Integer, Class> clientboundPackets; // i
            // ...
            protected EnumConnectionState registerServerbound(int id, Class packetClass) { // a
                if (this.serverboundPackets.containsKey(Integer.valueOf(id))) {
                    String error = "Serverbound packet ID " + id + " is already assigned to " + this.serverboundPackets.get(id) + "; cannot re-assign to " + packetClass;
                    LogManager.getLogger().fatal(error);
                    throw new IllegalArgumentException(error);
                } else if (this.serverboundPackets.containsValue(packetClass)) {
                    String error = "Serverbound packet " + packetClass + " is already assigned to ID " + this.serverboundPackets.inverse().get(packetClass) + "; cannot re-assign to " + id;
                    LogManager.getLogger().fatal(error);
                    throw new IllegalArgumentException(error);
                } else {
                    this.serverboundPackets.put(id, packetClass);
                    return this;
                }
            }

            protected EnumConnectionState registerClientbound(int id, Class packetClass) { // b
                if (this.clientboundPackets.containsKey(Integer.valueOf(id))) {
                    String error = "Clientbound packet ID " + id + " is already assigned to " + this.clientboundPackets.get(id) + "; cannot re-assign to " + packetClass;
                    LogManager.getLogger().fatal(error);
                    throw new IllegalArgumentException(error);
                } else if (this.clientboundPackets.containsValue(packetClass)) {
                    String error = "Clientbound packet " + packetClass + " is already assigned to ID " + this.clientboundPackets.inverse().get(packetClass) + "; cannot re-assign to " + id;
                    LogManager.getLogger().fatal(error);
                    throw new IllegalArgumentException(error);
                } else {
                    this.clientboundPackets.put(id, packetClass);
                    return this;
                }
            }
            // ...
        }
        """
        # We can identify the serverbound and clientbound methods by the string
        # in the error message.  Packet IDs are manual in this version.
        cf = classloader[connectionstate]

        # First, figure out registerServerbound and registerClientbound by looking for the string constants:
        directions_by_method = {}
        for method in register_methods:
            for ins in method.code.disassemble():
                if ins == "ldc":
                    const = ins.operands[0]
                    if isinstance(const, String):
                        if "Clientbound" in const.string.value:
                            directions["CLIENTBOUND"] = {
                                "register_method": method.name.value,
                                "name": "CLIENTBOUND"
                            }
                            directions_by_method[method.name.value] = directions["CLIENTBOUND"]
                            break
                        elif "Serverbound" in const.string.value:
                            directions["SERVERBOUND"] = {
                                "register_method": method.name.value,
                                "name": "SERVERBOUND"
                            }
                            directions_by_method[method.name.value] = directions["SERVERBOUND"]
                            break

        # Now identify the inner enum classes:
        states.update(get_enum_constants(cf, verbose))
        # These are the states on this version, which shouldn't change
        assert states.keys() == set(("HANDSHAKING", "PLAY", "STATUS", "LOGIN"))

        # Now that we have states and directions, go through each state and
        # find its calls to register.  This happens in the state's constructor.
        for state in states.values():
            class StateHandlerCallback(WalkerCallback):
                def on_invoke(self, ins, const, obj, args):
                    if const.name_and_type.name.value == "<init>":
                        # call to super
                        return

                    assert len(args) == 2
                    id = args[0]
                    cls = args[1]
                    # Make sure this is one of the register methods
                    assert const.name_and_type.name.value in directions_by_method
                    dir = directions_by_method[const.name_and_type.name.value]["name"]
                    from_client = (dir == "SERVERBOUND")
                    from_server = (dir == "CLIENTBOUND")
                    packet = {
                        "id": id,
                        "class": cls,
                        "direction": dir,
                        "from_client": from_client,
                        "from_server": from_server,
                        "state": state["name"]
                    }
                    packets[packet_name(packet)] = packet
                    return obj

                def on_new(self, ins, const):
                    raise Exception("Unexpected new: %s" % str(ins))
                def on_put_field(self, ins, const, obj, value):
                    raise Exception("Unexpected putfield: %s" % str(ins))
                def on_get_field(self, ins, const, obj):
                    raise Exception("Unexpected getfield: %s" % str(ins))

            state_cf = classloader[state["class"]]
            walk_method(state_cf, state_cf.methods.find_one(name="<init>"), StateHandlerCallback(), verbose)

    @staticmethod
    def parse_18_format(classloader, connectionstate, register_method, directions, states, packets, verbose):
        # The relevant code looks like this:
        """
        public enum EnumConnectionState { // gy in 1.8
            HANDSHAKING(-1) {{ // a (gz)
                this.registerPacket(EnumPacketDirection.SERVERBOUND, C00Handshake.class);
            }},
            PLAY(0) {{ // b (ha)
                this.registerPacket(EnumPacketDirection.CLIENTBOUND, S00PacketKeepAlive.class);
                this.registerPacket(EnumPacketDirection.CLIENTBOUND, S01PacketJoinGame.class);
                this.registerPacket(EnumPacketDirection.CLIENTBOUND, S02PacketChat.class);
                this.registerPacket(EnumPacketDirection.CLIENTBOUND, S03PacketTimeUpdate.class);
                // ...
                this.registerPacket(EnumPacketDirection.SERVERBOUND, C00PacketKeepAlive.class);
                this.registerPacket(EnumPacketDirection.SERVERBOUND, C01PacketChatMessage.class);
                this.registerPacket(EnumPacketDirection.SERVERBOUND, C02PacketUseEntity.class);
                this.registerPacket(EnumPacketDirection.SERVERBOUND, C03PacketPlayer.class);
            }},
            STATUS(1) {{ // c (hb)
                // ...
            }},
            LOGIN(2) {{ // d (hc)
                // ...
            }};
            // ...
        }
        """
        # Fortunately, we can figure out what EnumPacketDirection is
        # using the signature of the register method.
        cf = classloader[connectionstate]

        assert len(register_method.args) == 2
        assert register_method.args[1].name == "java/lang/Class"
        direction_class = register_method.args[0].name

        directions.update(get_enum_constants(classloader[direction_class], verbose))
        directions_by_field = {direction["field"]: direction for direction in directions.values()}

        # The directions should be the ones we know and love:
        assert directions.keys() == set(("CLIENTBOUND", "SERVERBOUND"))

        # Now identify the inner enum classes:
        states.update(get_enum_constants(cf, verbose))
        # These are the states on this version, which shouldn't change
        assert states.keys() == set(("HANDSHAKING", "PLAY", "STATUS", "LOGIN"))

        # Now that we have states and directions, go through each state and
        # find its calls to register.  This happens in the state's constructor.
        for state in states.values():
            # Packet IDs dynamically count up from 0 for each direction,
            # resetting to 0 for each state.
            cur_id = { dir_name: 0 for dir_name in directions.keys() }

            class StateHandlerCallback(WalkerCallback):
                def on_invoke(self, ins, const, obj, args):
                    if const.name_and_type.name.value == "<init>":
                        # call to super
                        return

                    assert len(args) == 2
                    direction = args[0]["name"]
                    cls = args[1]

                    id = cur_id[direction]
                    cur_id[direction] += 1

                    from_client = (direction == "SERVERBOUND")
                    from_server = (direction == "CLIENTBOUND")
                    packet = {
                        "id": id,
                        "class": cls,
                        "direction": direction,
                        "from_client": from_client,
                        "from_server": from_server,
                        "state": state["name"]
                    }
                    packets[packet_name(packet)] = packet
                    return obj

                def on_get_field(self, ins, const, obj):
                    if const.class_.name == direction_class:
                        return directions_by_field[const.name_and_type.name.value]

                    raise Exception("Unexpected getfield: %s" % str(ins))

                def on_new(self, ins, const):
                    raise Exception("Unexpected new: %s" % str(ins))
                def on_put_field(self, ins, const, obj, value):
                    raise Exception("Unexpected putfield: %s" % str(ins))

            state_cf = classloader[state["class"]]
            walk_method(state_cf, state_cf.methods.find_one(name="<init>"), StateHandlerCallback(), verbose)

    @staticmethod
    def parse_115_format(classloader, connectionstate, directions, states, packets, verbose):
        # The relevant code looks like this:
        """
        public enum ProtocolType {
            HANDSHAKING(-1, builder()
                .registerDirection(PacketDirection.SERVERBOUND, (new ProtocolType.PacketList<IHandshakeNetHandler>())
                    .registerPacket(CHandshakePacket.class, CHandshakePacket::new))),
            PLAY(0, builder()
                .registerDirection(PacketDirection.CLIENTBOUND, (new ProtocolType.PacketList<IClientPlayNetHandler>())
                    .registerPacket(SSpawnObjectPacket.class, SSpawnObjectPacket::new)
                    .registerPacket(SSpawnExperienceOrbPacket.class, SSpawnExperienceOrbPacket::new)
                    .registerPacket(SSpawnGlobalEntityPacket.class, SSpawnGlobalEntityPacket::new)
                    .registerPacket(SSpawnMobPacket.class, SSpawnMobPacket::new)
                    // ...
                ).registerDirection(PacketDirection.SERVERBOUND, (new ProtocolType.PacketList<IServerPlayNetHandler>())
                    .registerPacket(CConfirmTeleportPacket.class, CConfirmTeleportPacket::new)
                    .registerPacket(CQueryTileEntityNBTPacket.class, CQueryTileEntityNBTPacket::new)
                    .registerPacket(CSetDifficultyPacket.class, CSetDifficultyPacket::new)
                    .registerPacket(CChatMessagePacket.class, CChatMessagePacket::new)
                    //...
            )),
            STATUS(1, builder()
                .registerDirection(PacketDirection.SERVERBOUND, (new ProtocolType.PacketList<IClientStatusNetHandler())
                    .registerPacket(CServerQueryPacket.class, CServerQueryPacket::new)
                    .registerPacket(CPingPacket.class, CPingPacket::new))
                .registerDirection(PacketDirection.CLIENTBOUND, (new ProtocolType.PacketList<IServerStatusNetHandler>())
                    .registerPacket(SServerInfoPacket.class, SServerInfoPacket::new)
                    .registerPacket(SPongPacket.class, SPongPacket::new))),
            LOGIN(2, builder()
                .registerDirection(PacketDirection.CLIENTBOUND, (new ProtocolType.PacketList<IClientLoginNetHandler>())
                    .registerPacket(SDisconnectLoginPacket.class, SDisconnectLoginPacket::new)
                    .registerPacket(SEncryptionRequestPacket.class, SEncryptionRequestPacket::new)
                    .registerPacket(SLoginSuccessPacket.class, SLoginSuccessPacket::new)
                    .registerPacket(SEnableCompressionPacket.class, SEnableCompressionPacket::new)
                    .registerPacket(SCustomPayloadLoginPacket.class, SCustomPayloadLoginPacket::new))
                .registerDirection(PacketDirection.SERVERBOUND, (new ProtocolType.PacketList<IServerLoginNetHandler>())
                    .registerPacket(CLoginStartPacket.class, CLoginStartPacket::new)
                    .registerPacket(CEncryptionResponsePacket.class, CEncryptionResponsePacket::new)
                    .registerPacket(CCustomPayloadLoginPacket.class, CCustomPayloadLoginPacket::new)));

            private ProtocolType(int id, Builder builder) {
            }

            private static ProtocolType.Builder builder() {
                return new ProtocolType.Builder();
            }

            static class Builder {
                public <T extends INetHandler> ProtocolType.Builder registerDirection(PacketDirection direction, ProtocolType.PacketList<T> packetList) {
                    // ...
                    return this;
                }
            }

            static class PacketList<T extends INetHandler> {
                private PacketList() { // Yes, this is private, though it's accessed externally...
                    // ...
                }
                public <P extends Packet<T>> ProtocolType.PacketList<T> registerPacket(Class<P> packetClass, Supplier<P> constructor) {
                    // ...
                    return this;
                }
            }
        }
        """
        # (This is using 1.14 MCP names and my own guesses, neither of which I'm completely happy with)
        cf = classloader[connectionstate]
        clinit = cf.methods.find_one(name="<clinit>")

        # Identify the enum constants, though this skips over the rest of the initialization we care about:
        states.update(get_enum_constants(cf, verbose))
        # These are the states on this version, which hopefully won't change
        assert states.keys() == set(("HANDSHAKING", "PLAY", "STATUS", "LOGIN"))

        # Identify the direction class, by first locating builder() as the first call...
        for ins in clinit.code.disassemble():
            if ins.mnemonic == "invokestatic":
                const = ins.operands[0]
                assert const.class_.name == connectionstate
                builder_method = cf.methods.find_one(name=const.name_and_type.name, f=lambda m: m.descriptor == const.name_and_type.descriptor)
                break
        else:
            raise Exception("Needed to find an invokestatic instruction")

        # Now get the Builder class, and then PacketDirection and PacketList
        builder = builder_method.returns.name
        builder_cf = classloader[builder]
        # Assume that registerDirection is the only public method
        register_direction = builder_cf.methods.find_one(f=lambda m: m.access_flags.acc_public)

        direction_class = register_direction.args[0].name
        packet_list = register_direction.args[1].name

        directions.update(get_enum_constants(classloader[direction_class], verbose))
        directions_by_field = {direction["field"]: direction for direction in directions.values()}

        # The directions should be the ones we know and love:
        assert directions.keys() == set(("CLIENTBOUND", "SERVERBOUND"))

        # Now go through the init code one last time, this time looking at all
        # the instructions:
        packets_by_state = {}
        class StateHandlerCallback(WalkerCallback):
            def on_invoke(self, ins, const, obj, args):
                if const.name_and_type.name == "<init>":
                    if const.class_.name == connectionstate:
                        # Call to enum constructor.  Store data now.
                        packets_by_state[args[0]] = args[3]
                    return

                if const.name_and_type.name == builder_method.name and \
                        const.name_and_type.descriptor == builder_method.descriptor:
                    # Builder is represented by a dict that maps direction to
                    # the packetlist
                    return {}

                if const.class_.name == builder:
                    # Assume call to registerDirection
                    direction = args[0]
                    packetlist = args[1]
                    obj[direction] = packetlist
                    return obj

                if const.class_.name == packet_list:
                    cls = args[0]
                    packet_lambda_class = args[1] + ".class"
                    assert cls == packet_lambda_class
                    obj.append(cls)
                    return obj

            def on_get_field(self, ins, const, obj):
                if const.class_.name == direction_class:
                    return directions_by_field[const.name_and_type.name.value]["name"]

                if const.class_.name == connectionstate:
                    # Getting the enum fields to create the values array -- this
                    # is the endpoint for us
                    raise StopIteration()

                raise Exception("Unexpected getfield: %s" % str(ins))

            def on_new(self, ins, const):
                if const.name == connectionstate:
                    # Connection state doesn't need to be represented directly,
                    # since we don't actually use the object once it's fully
                    # constructed
                    return object()
                if const.name == packet_list:
                    # PacketList is just a list
                    return []

                raise Exception("Unexpected new: %s" % str(ins))

            def on_invokedynamic(self, ins, const, args):
                return class_from_invokedynamic(ins, cf)

            def on_put_field(self, ins, const, obj, value):
                # Ignore putfields, since we're registering in the constructor
                # call.
                pass

        walk_method(cf, clinit, StateHandlerCallback(), verbose)
        # packets_by_state now looks like this (albeit with obfuscated names):
        # {'HANDSHAKING': {'SERVERBOUND': ['CHandshakePacket']}, 'PLAY': {'CLIENTBOUND': ['SSpawnObjectPacket', 'SSpawnExperienceOrbPacket', 'SSpawnGlobalEntityPacket', 'SSpawnMobPacket'], 'SERVERBOUND': ['CConfirmTeleportPacket', 'CQueryTileEntityNBTPacket', 'CSetDifficultyPacket', 'CChatMessagePacket']}, 'STATUS': {'SERVERBOUND': [], 'CLIENTBOUND': []}, 'LOGIN': {'CLIENTBOUND': [], 'SERVERBOUND': []}}
        # We need to transform this into something more like what's used in other versions.

        for state, directions in packets_by_state.items():
            for direction, packetlist in directions.items():
                for id, packet_class in enumerate(packetlist):
                    from_client = (direction == "SERVERBOUND")
                    from_server = (direction == "CLIENTBOUND")
                    packet = {
                        "id": id,
                        "class": packet_class,
                        "direction": direction,
                        "from_client": from_client,
                        "from_server": from_server,
                        "state": state
                    }
                    packets[packet_name(packet)] = packet
