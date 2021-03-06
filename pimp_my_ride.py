#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__       = "Sebastian 'topo' Muniz"
__copyright__   = "Copyright 2017"
__credits__     = []
__license__     = "GPL"
__version__     = "0.1"
__maintainer__  = "Sebastian Muniz"
__email__       = "sebastianmuniz@gmail.com"
__description__ = "Pimped out multi-architecture CPU emulator"

from traceback import format_exc
import logging

import unicorn as uc

from unicorn.arm64_const import *
from unicorn.arm_const import *
from unicorn.x86_const import *
from unicorn.mips_const import *

import capstone as cs

import colorlog

__all__ = ["PimpMyRide", "PimpMyRideException", "LOG_LEVELS"]

PAGE_SIZE = 0x1000 # Default page size is 4KB

COMPILE_GCC = 0
COMPILE_MSVC = 1

LOG_LEVELS = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL
}

class PimpMyRideException(Exception):
    """Generic exception for PimpMyRide."""
    pass


class PimpMyRide(object):
    """
    Main class implementing the multi-architecture CPU emulator with debugging
    support.
    
    """

    def __init__(self, architecture, bits, is_little_endian, stack, stack_size,
            log_level=LOG_LEVELS['info'], compiler=COMPILE_GCC):

        log_format = "  %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"

        #logging.basicConfig(level=log_level)

        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        handler.setFormatter(colorlog.ColoredFormatter(log_format))

        self.logger = colorlog.getLogger(type(self).__name__)
        self.logger.setLevel(log_level)
        self.logger.addHandler(handler)

        self.__uc = None  # Unicorn instance.

        self.__cs = None  # Capstone instance.

        # Emulation parameters.
        self.code = None
        self.start_address = None
        self.return_address = None

        self.__memory_areas = []
        self.__memory_contents = []

        self.stack = self._align_address(stack)
        self.stack_size = stack_size

        self.compiler = compiler

        self.breakpoints = list()
        self.breakpoints_callback = list()

        # Convert IDA architectures IDs to our own.
        if architecture == "ppc": # FIXME : pyelftools does not recognize
                                    # PowerPC architecture, hence does not
                                    # return its type.
            raise PimpMyRideException("PowerPC is unsupported.")

        elif architecture == "MIPS":
            cur_arch = uc.UC_ARCH_MIPS
            if is_little_endian:
                cur_mode = uc.UC_MODE_MIPS32 + uc.UC_MODE_LITTLE_ENDIAN
            else:
                cur_mode = uc.UC_MODE_MIPS32 + uc.UC_MODE_BIG_ENDIAN

            cs_arch = cs.CS_ARCH_MIPS
            if is_little_endian:
                cs_mode = cs.CS_MODE_MIPS32 + cs.CS_MODE_LITTLE_ENDIAN
            else:
                cs_mode = cs.CS_MODE_MIPS32 + cs.CS_MODE_BIG_ENDIAN

        elif architecture == "ARM":
            #if self.mode == uc.UC_MODE_ARM:
            #elif self.mode == uc.UC_MODE_THUMB:
            cur_arch = uc.UC_ARCH_ARM
            cur_mode = uc.UC_MODE_ARM

            cs_arch = cs.CS_ARCH_ARM
            cs_mode = cs.CS_MODE_ARM

        elif architecture == "AArch64":
            cur_arch = uc.UC_ARCH_ARM64
            cur_mode = uc.UC_MODE_ARM

            cs_arch = cs.CS_ARCH_ARM64
            cs_mode = cs.CS_MODE_ARM

        elif architecture == "x86":
            cur_arch = uc.UC_ARCH_X86
            cs_arch = cs.CS_ARCH_X86

            if bits == 32:
                cur_mode = uc.UC_MODE_32
                cs_mode = cs.CS_MODE_32
            elif bits == 16:
                cur_mode = uc.UC_MODE_16
                cs_mode = cs.CS_MODE_16
            else:
                raise PimpMyRideException("Unknown %dbit for x86 architecture" % bits)

        elif architecture == "x64":
            cur_arch = uc.UC_ARCH_X86
            cur_mode = uc.UC_MODE_64

            cs_arch = cs.CS_ARCH_X86
            cs_mode = cs.CS_MODE_64

        else:
            raise PimpMyRideException(
                "Unsupported architecture %s" % architecture)

        self.logger.debug("Architecture: %s %dbits" % (
                architecture, bits))

        self.architecture = cur_arch
        self.mode = cur_mode

        self._cs_arch = cs_arch
        self._cs_mode = cs_mode
        #self.instruction_set = current_arch.InstructionSet()

        self.__regs = dict()
        self.__hooks = dict()

        # Setup the register configuration.
        self._setup_registers()

    @property
    def code(self):
        """Return the current code under execution."""
        return self._code

    @code.setter
    def code(self, code):
        """Store the current code under execution."""
        self._code = code

    @property
    def architecture(self):
        """Return the current architecture under execution."""
        return self._arch

    @architecture.setter
    def architecture(self, arch):
        """Store the current architecture under execution."""
        self._arch = arch

    @property
    def mode(self):
        """Return the current mode under execution."""
        return self._mode

    @mode.setter
    def mode(self, mode):
        """Store the current mode under execution."""
        self._mode = mode

    def add_memory_content(self, address, content):
        """Add a code region for the code emulation."""
        # Add the areas as a tuple (addr, size) unless we can think of a better
        # way to do it.
        # TODO : Validate area is valid for current architecture
        if not len(content):
            raise PimpMyRideException(
                    "Invalid memory content size specified (%d)" % size)
        self.__memory_contents.append([address, content])

    def add_memory_area(self, address, size):
        """Add a memory region for the code emulation."""
        # Add the areas as a tuple (addr, size) unless we can think of a better
        # way to do it.
        # TODO : Validate area is valid for current architecture
        if size <= 0:
            raise PimpMyRideException(
                    "Invalid memory area size specified (%d)" % size)
        self.__memory_areas.append([address, size])

    @property
    def start_address(self):
        """Return the initial start address."""
        return self._start_address

    @start_address.setter
    def start_address(self, address):
        """Store the initial start address."""
        self._start_address = address

    @property
    def return_address(self):
        """Return the return address."""
        return self._return_address

    @return_address.setter
    def return_address(self, address):
        """Store the return address."""
        self._return_address = address

    def stop(self):
        """Stop the emulation phase."""
        # TODO
        pass

    def init(self):
        """Initialize emulator settings previous to its usage."""
        #
        # Initialize Unicorn's operational parameters.
        #
        if not self.architecture:
            raise PimpMyRideException("Architecture not specified")

        if self.mode is None:
            raise PimpMyRideException("Mode not specified")

        if self.start_address is None:
            raise PimpMyRideException("Start address not specified")

        if self.return_address is None:
            raise PimpMyRideException("Return address not specified")

        if not len(self.__memory_areas):
            raise PimpMyRideException("No memory areas specified")

        if not len(self.__memory_contents):
            raise PimpMyRideException("No memory contents specified")

        # Create a new Unicorn instance.
        self.__uc = uc.Uc(self.architecture, self.mode)

        # Create a new Capstone instance.
        self.__cs = cs.Cs(self._cs_arch, self._cs_mode) 

        #
        # Initialize the emulator memory.
        #
        self.__initialize_memory()

        #
        # Inialize the emulator hooks.
        #
        self.__initialize_hooks()

        #
        # Inialize the emulated CPU registers.
        #
        self.__initialize_registers()

    def start(self, count=0, timeout=0):
        """Start the emulation phase with the parameters previously defined."""
        #
        # Proceed to the emulation phase.
        #
        try:
            self.logger.info("Starting emulation at 0x%08X (count=%d)" % (
                    self.start_address, count))

            self.__uc.emu_start(self.start_address,
                                self.return_address,
                                timeout,
                                count)

        except uc.UcError, err:
            self.logger.debug(format_exc())
            self.logger.error("Emulation error : %s" % err)

            self.__show_regs()

            #raise PimpMyRideException(err)

    def _setup_registers(self):
        if self.architecture == uc.UC_ARCH_X86:
            self.pack_endian = '<'
            if self.mode == uc.UC_MODE_16:
                self.step = 2
                self.pack_format = 'H'
                self.REG_PC = UC_X86_REG_PC
                self.REG_SP = UC_X86_REG_SP
                self.REG_RA = 0
                self.REG_RES = UC_X86_REG_AX
                self.REG_ARGS = []
            elif self.mode == uc.UC_MODE_32:
                self.step = 4
                self.pack_format = 'I'
                self.REG_PC = UC_X86_REG_EIP
                self.REG_SP = UC_X86_REG_ESP
                self.REG_RA = 0
                self.REG_RES = UC_X86_REG_EAX
                self.REG_ARGS = []
            elif self.mode == uc.UC_MODE_64:
                self.step = 8
                self.pack_format = 'Q'
                self.REG_PC = UC_X86_REG_RIP
                self.REG_SP = UC_X86_REG_RSP
                self.REG_RA = 0
                self.REG_RES = UC_X86_REG_RAX
                if self.compiler == COMPILE_GCC:
                    self.REG_ARGS = [UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX, UC_X86_REG_RCX, 
                            UC_X86_REG_R8, UC_X86_REG_R9]
                elif self.compiler == COMPILE_MSVC:
                    self.REG_ARGS = [UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9]

        elif self.architecture == uc.UC_ARCH_ARM:
            #
            # ARM (thumb and normal mode) architecture definitions.
            #
            self.pack_endian = '<'
            if self.mode == uc.UC_MODE_ARM:
                self.step = 4
                self.pack_format = 'I'
            elif self.mode == uc.UC_MODE_THUMB:
                self.step = 2
                self.pack_format = 'H'
            self.REG_PC = UC_ARM_REG_PC
            self.REG_SP = UC_ARM_REG_SP
            self.REG_RA = UC_ARM_REG_LR
            self.REG_RES = UC_ARM_REG_R0
            self.REG_ARGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]

        elif self.architecture == uc.UC_ARCH_ARM64:
            #
            # ARM 64bits architecture definitions.
            #
            self.step = 8 
            self.pack_format = 'Q'
            self.pack_endian = '<'
            self.REG_PC = UC_ARM64_REG_PC
            self.REG_SP = UC_ARM64_REG_SP
            self.REG_RA = UC_ARM64_REG_LR
            self.REG_RES = UC_ARM64_REG_X0
            self.REG_ARGS = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                    UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7]

        elif self.architecture == uc.UC_ARCH_MIPS:
            #
            # MIPS architecture definitions.
            #
            self.pack_endian = '<'
            if self.mode == uc.UC_MODE_MIPS32:
                self.step = 4
                self.pack_format = 'I'
            elif self.mode == uc.UC_MODE_MIPS64:
                self.step = 8
                self.pack_format = 'Q'
            self.REG_PC = UC_MIPS_REG_PC
            self.REG_SP = UC_MIPS_REG_SP
            self.REG_RA = UC_MIPS_REG_RA
            self.REG_RES = UC_MIPS_REG_V0
            self.REG_ARGS = [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3]

    def _align_address(self, address):
        """Align the specified address to a page boundary."""
        return address // PAGE_SIZE * PAGE_SIZE

    def __initialize_memory(self):
        """Initialize the emulator memory with the appropriate ranges and
        contents.
        """
        # Initialize the stack memory.
        stack_size = (self.stack_size) * PAGE_SIZE

        self._memory_map(self.stack, stack_size)
        self.write_memory(self.stack, "\x00" * stack_size)

        sp = self.stack + self.stack_size * PAGE_SIZE
        self.__uc.reg_write(self.REG_SP, sp)

        # Iterate through all the memory areas specified to map them all and
        # write content to them if necessary.
        for address, size in self.__memory_areas:
            size = self._align_address(size) + PAGE_SIZE # FIXME : horrible kludge! Will break contignous sections.
            address_aligned = self._align_address(address)

            self._memory_map(address_aligned, size, uc.UC_PROT_ALL)

        # Add the content to every previously mapped memory area.
        # Iterate through all the memory areas specified to map them all and
        # write content to them if necessary.
        for address, content in self.__memory_contents:
            self.write_memory(address, content)

    def __is_valid_memory_range(self, start_address, end_address):
        """..."""
        # Iterate through all the memory areas to validate the range.
        for address, size in self.__memory_areas:
            if start_address >= address and end_address <= address + size:
                self.logger.debug(
                    "Successfully validating memory range 0x%08X - 0x%08X" % (
                    start_address, end_address))
                return True

        # FIXME Make this better by adding this area to the other memory areas
        # (probably with different settings & permissions).
        if start_address >= self.stack and end_address <= (self.stack_size * PAGE_SIZE) + self.stack:
            self.logger.debug(
                "Successfully validating memory range 0x%08X - 0x%08X" % (
                start_address, end_address))
            return True

        self.logger.debug(
            "Unable to validate memory range 0x%08X - 0x%08X" % (
            start_address, end_address))
        return False

    def read_memory(self, address, size):
        """Read the content of a memory area.."""
        # Check memory range to read is valid.
        if not self.__is_valid_memory_range(address, address + size):
            return ""

        self.logger.debug("Reading %d(0x%X) bytes at 0x%08X" % (
            size, size, address))

        # This will fail if the memory area was not yet defined in Unicorn.
        return str(self.__uc.mem_read(address, size))

    def write_memory(self, address, content):
        """Set the content of a memory area with user-defined content."""
        # check memory range to write is valid.
        if not self.__is_valid_memory_range(address, address + len(content)):
            return ""

        self.logger.debug("Writting %d(0x%X) bytes at 0x%08X" % (
            len(content), len(content), address))

        # This will fail if the memory area was not yet defined in Unicorn.
        self.__uc.mem_write(address, content)

    def _memory_map(self, address, size, perm=None):
        """Map the specified address to a new memory area."""
        # This function should not be called directrly. Use add_memory_area
        # instead.
        self.logger.debug("Mapping 0x%08X - 0x%08X (size 0x%X)" % (
            address, address + size, size))

        if perm:
            self.__uc.mem_map(address, size, perm)
        else:
            self.__uc.mem_map(address, size)

    def _get_bit(self, value, offset):
        """Get the specified bit value from a bigger number."""
        mask = 1 << offset
        return 1 if (value & mask) > 0 else 0

    def _reg_map(self, reg_name):
        """Map register name to its corresponding index used by Unicorn."""

        reg_map = None

        if self.architecture == uc.UC_ARCH_MIPS:
            reg_map = {
                "zero" : UC_MIPS_REG_ZERO, #=2
                "at" : UC_MIPS_REG_AT, #=3
                "v0" : UC_MIPS_REG_V0, #=4
                "v1" : UC_MIPS_REG_V1, #=5
                "a0" : UC_MIPS_REG_A0, #=6
                "a1" : UC_MIPS_REG_A1, #=7
                "a2" : UC_MIPS_REG_A2, #=8
                "a3" : UC_MIPS_REG_A3, #=9
                "t0" : UC_MIPS_REG_T0, #=10
                "t1" : UC_MIPS_REG_T1, #=11
                "t2" : UC_MIPS_REG_T2, #=12
                "t3" : UC_MIPS_REG_T3, #=13
                "t4" : UC_MIPS_REG_T4, #=14
                "t5" : UC_MIPS_REG_T5, #=15
                "t6" : UC_MIPS_REG_T6, #=16
                "t7" : UC_MIPS_REG_T7, #=17
                "s0" : UC_MIPS_REG_S0, #=18
                "s1" : UC_MIPS_REG_S1, #=19
                "s2" : UC_MIPS_REG_S2, #=20
                "s3" : UC_MIPS_REG_S3, #=21
                "s4" : UC_MIPS_REG_S4, #=22
                "s5" : UC_MIPS_REG_S5, #=23
                "s6" : UC_MIPS_REG_S6, #=24
                "s7" : UC_MIPS_REG_S7, #=25
                "t8" : UC_MIPS_REG_T8, #=26
                "t9" : UC_MIPS_REG_T9, #=27
                "k0" : UC_MIPS_REG_K0, #=28
                "k1" : UC_MIPS_REG_K1, #=29
                "gp" : UC_MIPS_REG_GP, #=30
                "sp" : UC_MIPS_REG_SP, #=31
                "fp" : UC_MIPS_REG_FP, #=32
                #"s8" : UC_MIPS_REG_S8, #=32
                "ra" : UC_MIPS_REG_RA, #=33
                "hi" : UC_MIPS_REG_HI, #= 129
                "lo" : UC_MIPS_REG_LO, #= 130
                "pc" : UC_MIPS_REG_PC, #= 1
                #UC_MIPS_REG_HI0, #=45
                #UC_MIPS_REG_HI1, #=46
                #UC_MIPS_REG_HI2, #=47
                #UC_MIPS_REG_HI3, #=48
                #UC_MIPS_REG_LO0, #=45
                #UC_MIPS_REG_LO1, #=46
                #UC_MIPS_REG_LO2, #=47
                #UC_MIPS_REG_LO3, #=48
                }

        elif self.architecture == uc.UC_ARCH_ARM64:
            reg_map = {
                "r0"    : UC_ARM64_REG_X0, #= 199
                "r1"    : UC_ARM64_REG_X1, #= 200
                "r2"    : UC_ARM64_REG_X2, #= 201
                "r3"    : UC_ARM64_REG_X3, #= 202
                "r4"    : UC_ARM64_REG_X4, #= 203
                "r5"    : UC_ARM64_REG_X5, #= 204
                "r6"    : UC_ARM64_REG_X6, #= 205
                "r7"    : UC_ARM64_REG_X7, #= 206
                "r8"    : UC_ARM64_REG_X8, #= 207
                "r9"    : UC_ARM64_REG_X9, #= 208
                "r10"   : UC_ARM64_REG_X10, #= 209
                "r11"   : UC_ARM64_REG_X11, #= 210
                "r12"   : UC_ARM64_REG_X12, #= 211
                "r13"   : UC_ARM64_REG_X13, #= 212
                "r14"   : UC_ARM64_REG_X14, #= 213
                "r15"   : UC_ARM64_REG_X15, #= 214
                "r16"   : UC_ARM64_REG_X16, #= 215
                "r17"   : UC_ARM64_REG_X17, #= 216
                "r18"   : UC_ARM64_REG_X18, #= 217
                "r19"   : UC_ARM64_REG_X19, #= 218
                "r20"   : UC_ARM64_REG_X20, #= 219
                "r21"   : UC_ARM64_REG_X21, #= 220
                "r22"   : UC_ARM64_REG_X22, #= 221
                "r23"   : UC_ARM64_REG_X23, #= 222
                "r24"   : UC_ARM64_REG_X24, #= 223
                "r25"   : UC_ARM64_REG_X25, #= 224
                "r26"   : UC_ARM64_REG_X26, #= 225
                "r27"   : UC_ARM64_REG_X27, #= 226
                "r28"   : UC_ARM64_REG_X28, #= 227

                "r29"   : UC_ARM64_REG_X29, #= 1
                "r30"   : UC_ARM64_REG_X30, #= 2

                "r31"   : UC_ARM64_REG_SP, #= 4
                "sp"    : UC_ARM64_REG_SP, #= 4
                #"xzr"   : UC_ARM64_REG_XZR, #= 7

                "pc"    : UC_ARM64_REG_PC, #= 260
                }

        elif self.architecture == uc.UC_ARCH_X86:
            if self.mode == uc.UC_MODE_16:
                raise Exception("Register map not implemented")
            elif self.mode == uc.UC_MODE_32:
                raise Exception("Register map not implemented")
            elif self.mode == uc.UC_MODE_64:
                reg_map = {
                    "rax" : UC_X86_REG_RAX,
                    "rbx" : UC_X86_REG_RBX,
                    "rcx" : UC_X86_REG_RCX,
                    "rdx" : UC_X86_REG_RDX,
                    "rdi" : UC_X86_REG_RSI,
                    "rsi" : UC_X86_REG_RDI,
                    "rbp" : UC_X86_REG_RBP,
                    "rsp" : UC_X86_REG_RSP,
                    "rip" : UC_X86_REG_RIP,
                    "r8"  : UC_X86_REG_R8,
                    "r9"  : UC_X86_REG_R9,
                    "r10" : UC_X86_REG_R10,
                    "r11" : UC_X86_REG_R11,
                    "r12" : UC_X86_REG_R12,
                    "r13" : UC_X86_REG_R13,
                    "r14" : UC_X86_REG_R14,
                    "r15" : UC_X86_REG_R15,
                }

        elif self.architecture == uc.UC_ARCH_ARM:
            if self.mode == uc.UC_MODE_ARM:
                reg_map = {
                    "r0"    : UC_ARM64_REG_W0, #= 199
                    "r1"    : UC_ARM64_REG_W1, #= 200
                    "r2"    : UC_ARM64_REG_W2, #= 201
                    "r3"    : UC_ARM64_REG_W3, #= 202
                    "r4"    : UC_ARM64_REG_W4, #= 203
                    "r5"    : UC_ARM64_REG_W5, #= 204
                    "r6"    : UC_ARM64_REG_W6, #= 205
                    "r7"    : UC_ARM64_REG_W7, #= 206
                    "r8"    : UC_ARM64_REG_W8, #= 207
                    "r9"    : UC_ARM64_REG_W9, #= 208
                    "r10"   : UC_ARM64_REG_W10, #= 209
                    "r11"   : UC_ARM64_REG_W11, #= 210
                    "r12"   : UC_ARM64_REG_W12, #= 211
                    "r13"   : UC_ARM64_REG_W13, #= 212
                    "r14"   : UC_ARM64_REG_W14, #= 213
                    "r15"   : UC_ARM64_REG_W15, #= 214
                    "r16"   : UC_ARM64_REG_W16, #= 215
                    "r17"   : UC_ARM64_REG_W17, #= 216
                    "r18"   : UC_ARM64_REG_W18, #= 217
                    "r19"   : UC_ARM64_REG_W19, #= 218
                    "r20"   : UC_ARM64_REG_W20, #= 219
                    "r21"   : UC_ARM64_REG_W21, #= 220
                    "r22"   : UC_ARM64_REG_W22, #= 221
                    "r23"   : UC_ARM64_REG_W23, #= 222
                    "r24"   : UC_ARM64_REG_W24, #= 223
                    "r25"   : UC_ARM64_REG_W25, #= 224
                    "r26"   : UC_ARM64_REG_W26, #= 225
                    "r27"   : UC_ARM64_REG_W27, #= 226
                    "r28"   : UC_ARM64_REG_W28, #= 227

                    "r29"   : UC_ARM64_REG_W29, #= 1
                    "r30"   : UC_ARM64_REG_W30, #= 2

                    "r31"    : UC_ARM64_REG_SP, #= 4
                    "sp"    : UC_ARM64_REG_SP, #= 4
                    #"xzr"   : UC_ARM64_REG_XZR, #= 7

                    "pc"    : UC_ARM64_REG_PC, #= 260
                    }
            elif self.mode == uc.UC_MODE_THUMB:
                raise Exception("Register map for ARM thumb-mode not implemented")

        else:
            raise Exception("Register map not implemented")

        return reg_map.get(reg_name, 0x11223344)

    def read_register(self, reg_name):
        """Return the value of the register specified by its name."""
        reg_idx = self._reg_map(reg_name)
        reg_val = self.__uc.reg_read(reg_idx)
        #print "_" * 50
        #self.logger.info("Requesting register %s = 0x%08X" % (reg_name, reg_val))

        return reg_val

    def __show_regs(self):
        """..."""
        self.logger.debug("Registers:")
        try:
            if self.architecture == uc.UC_ARCH_MIPS:
                    zr = self.__uc.reg_read(UC_MIPS_REG_ZERO)
                    at = self.__uc.reg_read(UC_MIPS_REG_AT)
                    v0 = self.__uc.reg_read(UC_MIPS_REG_V0)
                    v1 = self.__uc.reg_read(UC_MIPS_REG_V1)
                    a0 = self.__uc.reg_read(UC_MIPS_REG_A0)
                    a1 = self.__uc.reg_read(UC_MIPS_REG_A1)
                    a2 = self.__uc.reg_read(UC_MIPS_REG_A2)
                    a3 = self.__uc.reg_read(UC_MIPS_REG_A3)
                    t0 = self.__uc.reg_read(UC_MIPS_REG_T0)
                    t1 = self.__uc.reg_read(UC_MIPS_REG_T1)
                    t2 = self.__uc.reg_read(UC_MIPS_REG_T2)
                    t3 = self.__uc.reg_read(UC_MIPS_REG_T3)
                    t4 = self.__uc.reg_read(UC_MIPS_REG_T4)
                    t5 = self.__uc.reg_read(UC_MIPS_REG_T5)
                    t6 = self.__uc.reg_read(UC_MIPS_REG_T6)
                    t7 = self.__uc.reg_read(UC_MIPS_REG_T7)
                    s0 = self.__uc.reg_read(UC_MIPS_REG_S0)
                    s1 = self.__uc.reg_read(UC_MIPS_REG_S1)
                    s2 = self.__uc.reg_read(UC_MIPS_REG_S2)
                    s3 = self.__uc.reg_read(UC_MIPS_REG_S3)
                    s4 = self.__uc.reg_read(UC_MIPS_REG_S4)
                    s5 = self.__uc.reg_read(UC_MIPS_REG_S5)
                    s6 = self.__uc.reg_read(UC_MIPS_REG_S6)
                    s7 = self.__uc.reg_read(UC_MIPS_REG_S7)
                    gp = self.__uc.reg_read(UC_MIPS_REG_GP)
                    sp = self.__uc.reg_read(UC_MIPS_REG_SP)
                    pc = self.__uc.reg_read(UC_MIPS_REG_PC)
                    ra = self.__uc.reg_read(UC_MIPS_REG_RA)
                    bv = self.__uc.reg_read(UC_MIPS_REG_CC7)

                    self.logger.debug("    $0 = 0x%08x at = 0x%08x v0 = 0x%08x v1 = 0x%08x" % (zr, at, v0, v1))
                    self.logger.debug("    a0 = 0x%08x a1 = 0x%08x a2 = 0x%08x a3 = 0x%08x" % (a0, a1, a2, a3))
                    self.logger.debug("    t0 = 0x%08x t1 = 0x%08x t2 = 0x%08x t3 = 0x%08x" % (t0, t1, t2, t3))
                    self.logger.debug("    t4 = 0x%08x t5 = 0x%08x t6 = 0x%08x t7 = 0x%08x" % (t4, t5, t6, t7))
                    self.logger.debug("    s0 = 0x%08x s1 = 0x%08x s2 = 0x%08x s3 = 0x%08x" % (s0, s1, s2, s3))
                    self.logger.debug("    s4 = 0x%08x s5 = 0x%08x s6 = 0x%08x s7 = 0x%08x" % (s4, s5, s6, s7))
                    self.logger.debug("    gp = 0x%08x sp = 0x%08x pc = 0x%08x ra = 0x%08x" % (gp, sp, pc, ra))
                    self.logger.debug("    BadVAddr = 0x%08X" % (bv))

            elif self.architecture == uc.UC_ARCH_X86:
                if self.mode == uc.UC_MODE_16:
                    ax = self.__uc.reg_read(UC_X86_REG_AX)
                    bx = self.__uc.reg_read(UC_X86_REG_BX)
                    cx = self.__uc.reg_read(UC_X86_REG_CX)
                    dx = self.__uc.reg_read(UC_X86_REG_DX)
                    di = self.__uc.reg_read(UC_X86_REG_SI)
                    si = self.__uc.reg_read(UC_X86_REG_DI)
                    bp = self.__uc.reg_read(UC_X86_REG_BP)
                    sp = self.__uc.reg_read(UC_X86_REG_SP)
                    ip = self.__uc.reg_read(UC_X86_REG_PC)
                    eflags = self.__uc.reg_read(UC_X86_REG_EFLAGS)

                    self.logger.debug("    AX = 0x%04x BX = 0x%04x CX = 0x%04x DX = 0x%04x" % (ax, bx, cx, dx))
                    self.logger.debug("    DI = 0x%04x SI = 0x%04x BP = 0x%04x SP = 0x%04x" % (di, si, bp, sp))
                    self.logger.debug("    IP = 0x%04x" % eip)     

                elif self.mode == uc.UC_MODE_32:
                    eax = self.__uc.reg_read(UC_X86_REG_EAX)
                    ebx = self.__uc.reg_read(UC_X86_REG_EBX)
                    ecx = self.__uc.reg_read(UC_X86_REG_ECX)
                    edx = self.__uc.reg_read(UC_X86_REG_EDX)
                    edi = self.__uc.reg_read(UC_X86_REG_ESI)
                    esi = self.__uc.reg_read(UC_X86_REG_EDI)
                    ebp = self.__uc.reg_read(UC_X86_REG_EBP)
                    esp = self.__uc.reg_read(UC_X86_REG_ESP)
                    eip = self.__uc.reg_read(UC_X86_REG_EIP)
                    eflags = self.__uc.reg_read(UC_X86_REG_EFLAGS)

                    self.logger.debug("    EAX = 0x%08x EBX = 0x%08x ECX = 0x%08x EDX = 0x%08x" % (eax, ebx, ecx, edx))
                    self.logger.debug("    EDI = 0x%08x ESI = 0x%08x EBP = 0x%08x ESP = 0x%08x" % (edi, esi, ebp, esp))
                    self.logger.debug("    EIP = 0x%08x" % eip)

                elif self.mode == uc.UC_MODE_64:
                    rax = self.__uc.reg_read(UC_X86_REG_RAX)
                    rbx = self.__uc.reg_read(UC_X86_REG_RBX)
                    rcx = self.__uc.reg_read(UC_X86_REG_RCX)
                    rdx = self.__uc.reg_read(UC_X86_REG_RDX)
                    rdi = self.__uc.reg_read(UC_X86_REG_RSI)
                    rsi = self.__uc.reg_read(UC_X86_REG_RDI)
                    rbp = self.__uc.reg_read(UC_X86_REG_RBP)
                    rsp = self.__uc.reg_read(UC_X86_REG_RSP)
                    rip = self.__uc.reg_read(UC_X86_REG_RIP)
                    r8 = self.__uc.reg_read(UC_X86_REG_R8)
                    r9 = self.__uc.reg_read(UC_X86_REG_R9)
                    r10 = self.__uc.reg_read(UC_X86_REG_R10)
                    r11 = self.__uc.reg_read(UC_X86_REG_R11)
                    r12 = self.__uc.reg_read(UC_X86_REG_R12)
                    r13 = self.__uc.reg_read(UC_X86_REG_R13)
                    r14 = self.__uc.reg_read(UC_X86_REG_R14)
                    r15 = self.__uc.reg_read(UC_X86_REG_R15)
                    eflags = self.__uc.reg_read(UC_X86_REG_EFLAGS)

                    self.logger.debug("    RAX = 0x%016x RBX = 0x%016x RCX = 0x%016x RDX = 0x%016x" % (rax, rbx, rcx, rdx))
                    self.logger.debug("    RDI = 0x%016x RSI = 0x%016x RBP = 0x%016x RSP = 0x%016x" % (rdi, rsi, rbp, rsp))
                    self.logger.debug("    R$8 = 0x%016x R9  = 0x%016x R10 = 0x%016x R11 = 0x%016x" % (r8, r9, r10, r11))
                    self.logger.debug("    R12 = 0x%016x R13 = 0x%016x R14 = 0x%016x R15 = 0x%016x" % (r12, r13, r14, r15))
                    self.logger.debug("    RIP = 0x%016x" % rip)

                self.logger.debug("    EFLAGS:")
                self.logger.debug("    CF=%d PF=%d AF=%d ZF=%d SF=%d TF=%d IF=%d DF=%d OF=%d IOPL=%d " \
                        "NT=%d RF=%d VM=%d AC=%d VIF=%d VIP=%d ID=%d"
                        % (self._get_bit(eflags, 0),
                           self._get_bit(eflags, 2),
                           self._get_bit(eflags, 4),
                           self._get_bit(eflags, 6),
                           self._get_bit(eflags, 7),
                           self._get_bit(eflags, 8),
                           self._get_bit(eflags, 9),
                           self._get_bit(eflags, 10),
                           self._get_bit(eflags, 11),
                           self._get_bit(eflags, 12) + self._get_bit(eflags, 13) * 2,
                           self._get_bit(eflags, 14),
                           self._get_bit(eflags, 16),
                           self._get_bit(eflags, 17),
                           self._get_bit(eflags, 18),
                           self._get_bit(eflags, 19),
                           self._get_bit(eflags, 20),
                           self._get_bit(eflags, 21)))

        except uc.UcError as e:
            #self.logger.debug("Exception: %s" % e)
            raise PimpMyRideException(e)

    def __initialize_hooks(self):
        """Commit all the hooks specified by the user."""
        # Add code hooks (if any).
        for hook, cb in self.__hooks.iteritems():
            self.logger.debug("Adding CODE hook : %s" % cb)
            self.__uc.hook_add(hook, cb)

        #TODO Add more hooks

    def __initialize_registers(self):
        """Set the registers to the user-specified values before the emulation
            starts.
        """
        for reg, value in self.__regs.iteritems():
            self.write_register(reg, value)

    def init_register(self, register, value):
        """Store the initial value of the specified register."""
        self.__regs[register] = value

    def write_register(self, register, value):
        """Write the specified value into the specified register."""
        reg_idx = self._reg_map(register)
        print "_" * 50
        self.logger.info("Writing register %s = 0x%08X" % (register, value))
        self.__uc.reg_write(reg_idx, value)

    def result(self):
        """Return the emulation results (if any)."""
        self.__show_regs()

    def _show_disasm_inst(self, opcodes, addr):
        """..."""
        disasm = list()
        try:
            for i in self.__cs.disasm(str(opcodes), addr):
                #if i.target not in (None, i.address + i.size):
                #    self.logger.error("a branch")
                #else:
                #    self.logger.error("not a branch")
                disasm.append([i.mnemonic, i.op_str, None])#i.groups])
                self.logger.debug("    0x%x  %s\t%s\t%s" % (
                        i.address, " ".join(["%02X" % ord(x) for x in str(i.bytes)]), i.mnemonic, i.op_str))
        except cs.CsError, err:
            self.logger.error(format_exc())
            raise PimpMyRideException(err)

        return disasm

    def add_code_hook(self, callback_fn):
        """Store user-specified callback function for the instruction tracing."""
        self.__hooks[uc.UC_HOOK_CODE] = callback_fn

    def trace_instructions(self):
        """Request the emulator to trace every executed instruction."""
        # TODO Enhance this code to differentiate internal callback from
        # user-defined hooks.
        self.logger.debug("Internal code trace enabled.")
        self.add_code_hook(self.__code_callback)

    def __code_callback(self, _uc, address, size, user_data):
        """Built-in callback for instructions tracing."""
        self.logger.debug("Tracing instruction at 0x%x, instruction size = %u" %(address, size))
        try:
            self.__show_regs()

            opcodes = _uc.mem_read(address, size)

            self.logger.debug("")
            disasm = self._show_disasm_inst(opcodes, address)
            self.logger.debug("")

            if self.architecture == uc.UC_ARCH_MIPS:
                new_pc = self.read_register("pc")

            elif self.architecture == uc.UC_ARCH_X86:
                if self.mode == uc.UC_MODE_16:
                    raise Exception("get PC map not implemented")
                elif self.mode == uc.UC_MODE_32:
                    raise Exception("get PC not implemented")
                elif self.mode == uc.UC_MODE_64:
                    new_pc = self.read_register("rip")
            else:
                raise Exception("get PC not implemented for current architecture")

            if str(disasm[0][0]) == 'jal':
                self.logger.error("============> %r" % (str(disasm[0][0]) == 'jal'))
                #new_pc = int(str(disasm[0][1]), 16)
                #new_pc = int(str(disasm[0][1]), 16)
                self.logger.error("new pc (jal) = 0x%08X" % new_pc)

            #self.__uc.reg_write(UC_MIPS_REG_PC, new_pc)

            self.logger.warning("New address 0x%08X" % new_pc)
            self.start_address = new_pc
            self.logger.debug("_" * 80)

            # Check breakpoint
            if address in self.breakpoints:
                self.logger.debug("_" * 80)
                self.logger.debug("Stopping execution...")
                self.__uc.emu_stop()

                self.logger.info("Breakpoint hit at 0x%08X" % address)
                for cb in self.breakpoints_callback:
                    cb(address)
                self.logger.debug("_" * 80)

            # TODO : call user-defined function now?

        except uc.UcError as err:
            self.logger.error("Error (CODE hook): %s" % err)

    def __memory_access_invalid_callback(self, uc, access, address, size, value, user_data):
        """Built-in callback for invalid memory accesses (READ or WRITE, FETCH)"""
        try:
            # FIXME : finish this
            self.logger.debug("Memory access invalid at 0x%08X" % address)

            # TODO : call user-defined function now?
        except uc.UcError as err:
            self.logger.error("Error (MEMORY hook): %s" % err)

    def add_breakpoint_callback(self, callback):
        """Add a callback function for every breakpoint hit."""
        self.breakpoints_callback.append(callback)
        return

    def set_breakpoint(self, addr):
        """Store a list of the address to check for breakpoints."""
        self.breakpoints.append(addr)
        return

    def remove_breakpoint(self, addr):
        """Remove the specified address from the breakpoint addresses list."""
        if addr in self.breakpoints:
            self.breakpoints.remove(addr)
        return

