"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2015 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

TARGET_RUNNING = (1 << 0)
TARGET_HALTED = (1 << 1)

WATCHPOINT_READ = 1
WATCHPOINT_WRITE = 2
WATCHPOINT_READ_WRITE = 3

class Target(object):

    def __init__(self, emu, transport=None):
        self.transport = transport
        self.flash = None
        self.part_number = ""

        self.emu = emu

        # We want to get notified about breakpoints hit.
        self.emu.add_breakpoint_callback(self.breakpoint_callback)

        self.endian = emu.pack_endian
        self.pack_format = emu.pack_format
        self.step = emu.step

        self.state = None

    @property
    def state(self):
        """Return the current state of the application."""
        return self._state

    @state.setter
    def state(self, state):
        """Store the current state of the application."""
        self._state = state

    def setFlash(self, flash):
        self.flash = flash

    def init(self):
        return

    def info(self, request):
        return

    def readIDCode(self):
        return

    def halt(self):
        return

    def step(self):
        return

    def resume(self):
        return

    def writeMemory(self, addr, value, transfer_size = 32):
        return

    def readMemory(self, addr, transfer_size = 32):
        return

    def writeBlockMemoryUnaligned8(self, addr, value):
        return

    def writeBlockMemoryAligned32(self, addr, data):
        return

    def readBlockMemoryUnaligned8(self, addr, size):
        return

    def readBlockMemoryAligned32(self, addr, size):
        return

    def readCoreRegister(self, id):
        return

    def writeCoreRegister(self, id):
        return

    def setBreakpoint(self, addr):
        return

    def removeBreakpoint(self, addr):
        return

    def setWatchpoint(addr, size, type):
        return

    def removeWatchpoint(addr, size, type):
        return

    def reset(self):
        return

    def getState(self):
        return

    # GDB functions
    def getTargetXML(self):
        return ''

    def getMemoryMapXML(self):
        return self.memoryMapXML

    def getRegisterContext(self):
        return ''

    def setRegisterContext(self, data):
        return

    def setRegister(self, reg, data):
        return

    def getTResponse(self, gdbInterrupt = False):
        return ''
