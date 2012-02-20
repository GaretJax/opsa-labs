"""
You can run this file by executing:

    python server.py 1024

on the command line. The twisted networking library is
required in order to run the server.
"""

import sys

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor

class Echo(DatagramProtocol):

    def datagramReceived(self, data, (host, port)):
        print "received %r from %s:%d" % (data, host, port)
        self.transport.write(data, (host, port))

reactor.listenUDP(int(sys.argv[1]), Echo())
reactor.run()
