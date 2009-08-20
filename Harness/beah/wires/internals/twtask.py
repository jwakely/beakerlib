# Beah - Test harness. Part of Beaker project.
#
# Copyright (C) 2009 Marian Csontos <mcsontos@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from twisted.internet import reactor
from twisted.internet import protocol
from beah.wires.internals.twadaptors import TaskAdaptor_JSON

class TaskStdoutProtocol(protocol.ProcessProtocol):
    def __init__(self, task_info, task_protocol=TaskAdaptor_JSON):
        self.task_info = task_info
        self.task_protocol = task_protocol or TaskAdaptor_JSON
        self.task = None
        self.controller = None

    def connectionMade(self):
        self.transport.closeStdin()
        self.task = self.task_protocol()
        self.task.task_info = self.task_info
        self.task.set_controller(self.controller)
        self.controller.task_started(self.task)

    def outReceived(self, data):
        #print "stdout: %r" % data
        self.task.dataReceived(data)

    def errReceived(self, data):
        #print "stderr: %r" % data
        self.task.lose_item(data)

    def processExited(self, reason):
        self.controller.task_finished(self.task, rc=reason.value.exitCode)
        self.task.set_controller()

    def processEnded(self, reason):
        self.controller.task_finished(self.task, rc=reason.value.exitCode)
        self.task.set_controller()

def Spawn(host, port, proto=None):
    import os
    def spawn(controller, backend, task_info):
        # 1. set env.variables
        # BEACON_THOST - host name
        # BEACON_TPORT - port
        # BEACON_TID - id of task - used to introduce itself when opening socket
        task_env = { 'BEACON_THOST': str(host),
                'BEACON_TPORT': str(port),
                'BEACON_TID'  : str(task_info['id']),
                'BEAHLIB_ROOT' : os.getenv('BEAHLIB_ROOT')
                }
        val = os.getenv('PYTHONPATH')
        if val:
            task_env.update(PYTHONPATH=val)
        # 2. spawn a task
        protocol = (proto or TaskStdoutProtocol)(task_info)
        protocol.controller = controller
        reactor.spawnProcess(protocol, task_info['file'],
                args=[task_info['file']], env=task_env)
        # FIXME: send an answer to backend(?)
        return protocol.task_protocol
    return spawn

from twisted.internet.protocol import ReconnectingClientFactory
class TaskFactory(ReconnectingClientFactory):
    def __init__(self, task, controller_protocol):
        self.task = task
        self.controller_protocol = controller_protocol

    ########################################
    # INHERITED METHODS:
    ########################################
    def startedConnecting(self, connector):
        print self.__class__.__name__, ': Started to connect.'

    def buildProtocol(self, addr):
        print self.__class__.__name__, ': Connected.  Address: %r' % addr
        print self.__class__.__name__, ': Resetting reconnection delay'
        self.resetDelay()
        controller = self.controller_protocol()
        controller.add_task(self.task)
        return controller

    def clientConnectionLost(self, connector, reason):
        print self.__class__.__name__, ': Lost connection.  Reason:', reason
        self.task.set_controller()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print self.__class__.__name__, ': Connection failed. Reason:', reason
        self.task.set_controller()
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

from beah.wires.internals.twadaptors import ControllerAdaptor_Task_JSON
def start_task(config, task, host=None, port=None,
        adaptor=ControllerAdaptor_Task_JSON,
        ):
    host = host or config.THOST()
    port = port or config.TPORT()
    reactor.connectTCP(host, int(port), TaskFactory(task, adaptor))