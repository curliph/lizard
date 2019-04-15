from pymtl import *
from util.rtl.interface import Interface, UseInterface
from util.rtl.method import MethodSpec
from util.rtl.lookup_registerfile import LookupRegisterFileInterface, LookupRegisterFile
from core.rtl.messages import CsrFunc
from msg.codes import CsrRegisters
from config.general import CSR_SPEC_NBITS, XLEN
from bitutil import bit_enum


class CSRManagerInterface(Interface):

  def __init__(s, num_read_ports, num_write_ports):
    s.num_read_ports = num_read_ports
    s.num_write_ports = num_write_ports

    super(CSRManagerInterface, s).__init__([
        MethodSpec(
            'read',
            args={
                'csr': Bits(CSR_SPEC_NBITS),
            },
            rets={
                'value': Bits(XLEN),
                'valid': Bits(1),
            },
            call=False,
            rdy=False,
            count=num_read_ports,
        ),
        MethodSpec(
            'op',
            args={
                'csr': Bits(CSR_SPEC_NBITS),
                'op': Bits(CsrFunc.bits),
                'rs1_is_x0': Bits(1),
                'value': Bits(XLEN),
            },
            rets={
                'old': Bits(XLEN),
                'success': Bits(1),
            },
            call=True,
            rdy=False,
        ),
        MethodSpec(
            'write',
            args={
                'csr': Bits(CSR_SPEC_NBITS),
                'value': Bits(XLEN),
            },
            rets={
                'valid': Bits(1),
            },
            call=True,
            rdy=False,
            count=num_write_ports,
        ),
    ])


class CSRManager(Model):

  def __init__(s, interface):
    UseInterface(s, interface)

    s.require(
        MethodSpec(
            'debug_recv',
            args=None,
            rets={'msg': Bits(XLEN)},
            call=True,
            rdy=True,
        ),
        MethodSpec(
            'debug_send',
            args={'msg': Bits(XLEN)},
            rets=None,
            call=True,
            rdy=True,
        ),
    )

    num_read_ports = s.interface.num_read_ports
    num_write_ports = s.interface.num_write_ports
    # 1 extra read and write port for doing the op
    s.csr_file = LookupRegisterFile(
        LookupRegisterFileInterface(
            Bits(CSR_SPEC_NBITS), Bits(XLEN), num_read_ports + 1,
            num_write_ports + 1), [
                CsrRegisters.mtvec,
                CsrRegisters.mepc,
                CsrRegisters.mcause,
                CsrRegisters.mtval,
            ],
        reset_values=[
            0,
            0,
            0,
            0,
        ])

    # PYMTL_BROKEN
    s.temp_debug_recv_call = Wire(1)
    s.temp_debug_send_call = Wire(1)
    s.temp_debug_send_msg = Wire(Bits(XLEN))
    s.temp_op_success = Wire(1)
    s.temp_op_old = Wire(Bits(XLEN))
    s.temp_read_key = Bits(CSR_SPEC_NBITS)
    s.temp_write_key = Bits(CSR_SPEC_NBITS)
    s.temp_write_value = Bits(XLEN)
    s.temp_write_call = Bits(1)

    @s.combinational
    def handle_op():
      s.temp_debug_recv_call.v = 0

      s.temp_debug_send_call.v = 0
      s.temp_debug_send_msg.v = 0

      s.temp_op_success.v = 0
      s.temp_op_old.v = 0

      s.temp_read_key.v = 0
      s.temp_write_key.v = 0
      s.temp_write_value.v = 0
      s.temp_write_call.v = 0

      if s.op_call:
        if s.op_csr == CsrRegisters.proc2mngr:
          if s.op_op == CsrFunc.CSR_FUNC_READ_WRITE and s.debug_send_rdy:
            s.temp_debug_send_call.v = 1
            s.temp_debug_send_msg.v = s.op_value

            s.temp_op_success.v = 1
            s.temp_op_old.v = 0
        elif s.op_csr == CsrRegisters.mngr2proc:
          if s.op_op != CsrFunc.CSR_FUNC_READ_WRITE and s.debug_recv_rdy and s.op_rs1_is_x0:
            s.temp_debug_recv_call.v = 1

            s.temp_op_success.v = 1
            s.temp_op_old.v = s.debug_recv_msg
        else:
          s.temp_op_success.v = s.csr_file.read_valid[num_read_ports]
          s.temp_read_key.v = s.op_csr
          s.temp_op_old.v = s.csr_file.read_value[num_read_ports]
          if s.op_op == CsrFuc.CSR_FUNC_READ_WRITE:
            s.temp_write_key.v = s.op_csr
            s.temp_write_value.v = s.op_value
            s.temp_write_call.v = 1
          elif s.op_op == CsrFunc.CSR_FUNC_READ_SET:
            s.temp_write_key.v = s.op_csr
            s.temp_write_value.v = s.op_value | s.temp_op_old
            s.temp_write_call.v = 1
          elif s.op_op == CsrFunc.CSR_FUNC_READ_CLEAR:
            s.temp_write_key.v = s.op_csr
            s.temp_write_value.v = s.op_value & (~s.temp_op_old)
            s.temp_write_call.v = 1

      s.debug_recv_call.v = s.temp_debug_recv_call
      s.debug_send_call.v = s.temp_debug_send_call
      s.debug_send_msg.v = s.temp_debug_send_msg
      s.op_success.v = s.temp_op_success
      s.op_old.v = s.temp_op_old

      s.csr_file.read_key[num_read_ports].v = s.temp_read_key
      s.csr_file.write_key[0].v = s.temp_write_key
      s.csr_file.write_value[0].v = s.temp_write_value
      s.csr_file.write_call[0].v = s.temp_write_call

    for i in range(num_read_ports):
      s.connect(s.csr_file.read_key[i], s.read_csr[i])
      s.connect(s.read_value[i], s.csr_file.read_value[i])
      s.connect(s.read_valid[i], s.csr_file.read_valid[i])

    for i in range(num_write_ports):
      s.connect(s.csr_file.write_key[i + 1], s.write_csr[i])
      s.connect(s.csr_file.write_value[i + 1], s.write_value[i])
      s.connect(s.csr_file.write_call[i + 1], s.write_call[i])
      s.connect(s.write_valid[i], s.csr_file.write_valid[i + 1])
