#!/usr/bin/env python

from twisted.internet import reactor, protocol
from twisted.protocols import telnet
import sys

from StringIO import StringIO


class StateMachine(object):

    states = {}
    state = None

    def __init__(self, *args, **kwargs):
        if 'initial_state' in kwargs:
            self.state = kwargs.pop('initial_state')

        super(StateMachine, self).__init__(*args, **kwargs)

    def processEvent(self):
        func = getattr(self, self.state)
        result = func()
        self.state = self.states[self.state][result]



class TelnetClient(telnet.Telnet):
    linemode = True
    rawbuffer = StringIO()

    def setLineMode(self):
        self.linemode = True

    def setRawMode(self):
        self.linemode = False

    def connectionMade(self):
        self.setRawMode()
        self.write(telnet.IAC + telnet.DO + telnet.NOECHO)

    def write(self, data):
        #print "Writing", repr(data)
        telnet.Telnet.write(self, data)

    def processChunk(self, chunk):
        if self.linemode:
            telnet.Telnet.processChunk(self, chunk)
        else:
            self.rawbuffer.write(chunk)
            self.bufferUpdated()

    def bufferUpdated(self):
        pass

    def connectionLost(self, reason):
        print>>sys.stderr, "Disconnected from router"
        reactor.stop()


class BGPClient(TelnetClient, StateMachine):

    states = {
        'sendUsername': {
            True: 'sendCommand',
            False: 'sendUsername',
        },
        'sendCommand': {
            True: 'ignoreEcho',
            False: 'sendCommand',
        },
        'ignoreEcho': {
            True: 'readReply',
            False: 'ignoreEcho',
        },
        'readReply': {
            None: 'readReply',
        }
    }

    state = 'sendUsername'

    reply = []

    def sendCommand(self):
        if not self.rawbuffer.getvalue().endswith('route-server>'):
            return False

        self.rawbuffer = StringIO()
        self.write('sh ip bgp regexp . {}$\r\n'.format(self.factory.autonomous_system))

        return True

    def sendUsername(self):
        if not self.rawbuffer.getvalue().endswith('Username: '):
            return False

        self.rawbuffer = StringIO()
        self.write('rviews\r')

        return True

    def ignoreEcho(self):
        buffer = self.rawbuffer.getvalue()

        if buffer.startswith('sh ip bgp regexp . {}$\r\n'.format(self.factory.autonomous_system)):
            self.rawbuffer = StringIO()
            print>>sys.stderr, "Command sent, waiting reply..."
            return True

        return False

    def readReply(self):
        buffer, self.rawbuffer = self.rawbuffer.getvalue(), StringIO()

        reply = buffer.splitlines()
        self.reply += reply

        if reply[-1] == ' --More-- ':
            #sys.stderr.write(' Received {} lines...\r'.format(len(self.reply)))
            #sys.stderr.flush()
            reply.pop()
            self.reply.pop()
            self.write('\r')

            for line in reply:
                self.processRoute(line.strip())
        elif len(self.reply) < 20:
            self.rawbuffer.write(self.reply.pop())
        else:
            print>>sys.stderr, "Reply completely received"
            self.transport.loseConnection()

    def processRoute(self, route):
        if '/' in route:
            network = route.strip('\x08 *').strip().split(' ', 1)[0]
            self.processNetwork(network)

    def processNetwork(self, network):
        network_ip = [int(i) for i in network.split('/')[0].split('.')]

        while self.factory.current[0] <= network_ip:
            self.factory.prev = self.factory.current
            self.factory.current = next(self.factory.db)

        from_ip, to_ip, country = self.factory.prev

        assert from_ip <= network_ip <= to_ip

        print '{0:>18s} -> {1:<20s} [{2:>16s} - {3:<16s}]'.format(
            network,
            country,
            '.'.join(map(str, from_ip)),
            '.'.join(map(str, to_ip))
        )


    def bufferUpdated(self):
        self.processEvent()


def prepareDB():
    l = []

    with open('GeoIPCountryWhois.csv') as fh:
        for line in fh:
            range_from, range_to, _, _, _, country = line.strip(' "\n').split('","')

            ip_from = [int(i) for i in range_from.split('.')]
            ip_to = [int(i) for i in range_to.split('.')]

            l.append((ip_from, ip_to, country))

    return l

db = prepareDB()


f = protocol.ClientFactory()
f.protocol = BGPClient
f.db = iter(db)
f.prev = next(f.db)
f.current = next(f.db)
f.autonomous_system = int(sys.argv[1])


reactor.connectTCP('route-server.ip.att.net', 23, f)
reactor.run()
