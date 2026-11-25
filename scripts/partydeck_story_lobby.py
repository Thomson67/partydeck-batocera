"""Local party setup for the pinned Story Co-op v1.0.5 (BETA000003) protocol."""
import asyncio
from contextlib import AsyncExitStack, suppress
import json
from pathlib import Path
import signal
import struct
import sys

from partydeck_i18n import tr
from partydeck_story_coop import client_host

# PacketTypes.hpp distinguishes the client and server packet ID spaces.
CLIENT_INIT_LIST, CLIENT_CREATE, CLIENT_LEAVE, CLIENT_INVITE, CLIENT_JOIN, CLIENT_TELEPORT = 24, 25, 26, 27, 28, 31
SERVER_AUTH, SERVER_LIST_APPEND, SERVER_LIST_UPDATE, SERVER_JOIN, SERVER_INVITE = 3, 21, 23, 24, 25


def send(writer, packet):
    writer.write(struct.pack('<H', len(packet)) + packet)


async def read_packet(reader):
    size, = struct.unpack('<H', await reader.readexactly(2))
    return await reader.readexactly(size)


def hide_locations(packet):
    kind = packet[0]
    if kind == SERVER_LIST_APPEND and len(packet) >= 5:
        count, = struct.unpack_from('<I', packet, 1)
        offset = 5
    elif kind == SERVER_LIST_UPDATE:
        count, offset = 1, 1
    else:
        return packet
    output = bytearray(packet)
    for _ in range(count):
        if offset + 4 > len(packet):
            return packet
        length, = struct.unpack_from('<H', packet, offset + 2)
        location = offset + 4 + length
        if location + 4 > len(packet):
            return packet
        output[location:location + 3] = b'\xff\xff\x00'  # scene=-1, room=0
        offset = location + 4
    return bytes(output)


class Player:
    def __init__(self, slot, writer):
        self.slot = slot
        self.writer = writer
        self.network_id = None
        self.party_id = 0
        self.ready = False
        self.creating = False
        self.invitation = None

    def send(self, kind, payload=b''):
        send(self.writer, bytes((kind,)) + payload)


class Lobby:
    def __init__(self, backend, options, host_settings):
        self.backend = backend
        self.options = options
        self.host_settings = host_settings
        self.players = {}
        self.party_id = 0

    def invite(self, inviter, guest):
        if guest.invitation is None:
            guest.invitation = (inviter.network_id, inviter.party_id)
            inviter.send(CLIENT_INVITE, struct.pack('<H', guest.network_id))

    def update(self):
        host = self.players.get(1)
        if not self.options['automatic'] or host is None or not host.ready:
            return
        guests = [player for slot, player in self.players.items() if slot != 1 and player.ready]
        if not host.party_id:
            # If J1's connection dropped, keep the existing campaign session
            # when a member is still in it. The native server manages admin transfer.
            member = next((guest for guest in guests if guest.party_id and guest.party_id == self.party_id), None)
            if member:
                self.invite(member, host)
            elif not host.creating:
                host.send(CLIENT_CREATE, self.host_settings.read_bytes())
                host.creating = True
            return
        self.party_id = host.party_id
        for guest in guests:
            if not guest.party_id:
                self.invite(host, guest)

    async def client_packets(self, player, reader):
        while True:
            packet = await read_packet(reader)
            kind = packet[0] if packet else -1
            if kind == CLIENT_TELEPORT and not self.options['teleport']:
                continue
            send(player.writer, packet)
            if kind == CLIENT_INIT_LIST and player.network_id is not None:
                # The client has already sent its appearance and name. The
                # server uses that name when it selects the host's campaign.
                player.ready = True
                self.update()
            elif kind == CLIENT_LEAVE:
                player.ready = False
            await player.writer.drain()

    async def server_packets(self, player, reader, writer):
        while True:
            packet = await read_packet(reader)
            kind = packet[0] if packet else -1
            if kind == SERVER_AUTH and len(packet) == 3:
                player.network_id, = struct.unpack_from('<H', packet, 1)
            elif kind == SERVER_JOIN and len(packet) >= 7:
                player.party_id, = struct.unpack_from('<I', packet, 1)
                player.invitation = None
                player.creating = False
                if self.options['automatic'] and player.party_id:
                    print(tr('Story Co-op : J{p0} a rejoint le groupe {p1}.',
                             p0=player.slot, p1=player.party_id), flush=True)
                self.update()
            elif kind == SERVER_INVITE and len(packet) == 7 and player.ready:
                if struct.unpack_from('<HI', packet, 1) == player.invitation:
                    # Use the server's invitation and normal join operation.
                    player.send(CLIENT_JOIN, packet[1:])
                    await player.writer.drain()
                    continue
            if packet and not self.options['locations']:
                packet = hide_locations(packet)
            send(writer, packet)
            await writer.drain()

    async def connect(self, slot, reader, writer):
        player = None
        tasks = ()
        try:
            # A listening address is assigned to each player by the launcher.
            # Wait for cleanup of the previous socket on rapid reconnect.
            for _ in range(20):
                if slot not in self.players:
                    break
                await asyncio.sleep(.05)
            if slot in self.players:
                return
            upstream_reader, upstream_writer = await asyncio.open_connection('127.0.0.1', self.backend)
            if slot in self.players:
                upstream_writer.close()
                await upstream_writer.wait_closed()
                return
            player = self.players[slot] = Player(slot, upstream_writer)
            tasks = (asyncio.create_task(self.client_packets(player, reader)),
                     asyncio.create_task(self.server_packets(player, upstream_reader, writer)))
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except OSError as error:
            print(tr('Story Co-op : liaison locale interrompue ({p0}).', p0=error), file=sys.stderr, flush=True)
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if player is not None:
                del self.players[slot]
                for other in self.players.values():
                    if other.invitation and other.invitation[0] == player.network_id:
                        other.invitation = None
                player.writer.close()
                with suppress(ConnectionError):
                    await player.writer.wait_closed()
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()


async def serve(program, port, count, host_settings, options):
    # Both the server and these listeners share the per-session network namespace.
    backend = port + 1
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    server = await asyncio.create_subprocess_exec(str(program), '--port', str(backend))
    waiter = asyncio.create_task(server.wait())
    stopped = asyncio.create_task(stop.wait())
    try:
        deadline = loop.time() + 8
        while True:
            if stopped.done() or waiter.done():
                return waiter.result() if waiter.done() else 0
            try:
                _, writer = await asyncio.open_connection('127.0.0.1', backend)
                writer.close()
                await writer.wait_closed()
                break
            except ConnectionRefusedError:
                if loop.time() >= deadline:
                    raise
                await asyncio.sleep(.05)
        lobby = Lobby(backend, options, host_settings)
        async with AsyncExitStack() as listeners:
            for slot in range(1, count + 1):
                await listeners.enter_async_context(await asyncio.start_server(
                    lambda reader, writer, slot=slot: lobby.connect(slot, reader, writer),
                    client_host(slot), port))
            print(f'Story Co-op READY {port}', flush=True)
            await asyncio.wait((waiter, stopped), return_when=asyncio.FIRST_COMPLETED)
            return waiter.result() if waiter.done() else 0
    finally:
        stopped.cancel()
        if server.returncode is None:
            with suppress(ProcessLookupError):
                server.terminate()
            try:
                await asyncio.wait_for(asyncio.shield(waiter), 4)
            except asyncio.TimeoutError:
                with suppress(ProcessLookupError):
                    server.kill()
                await waiter


if __name__ == '__main__':
    program, port, count, settings, options = sys.argv[1:]
    raise SystemExit(asyncio.run(serve(Path(program), int(port), int(count), Path(settings), json.loads(options))))
