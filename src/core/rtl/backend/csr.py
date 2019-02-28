from pymtl import *
from util.rtl.interface import Interface, UseInterface
from util.rtl.method import MethodSpec
from util.rtl.register import Register, RegisterInterface
from core.rtl.messages import DispatchMsg, ExecuteMsg, PipelineMsgStatus
from core.rtl.csr_manager import CSROpType
from config.general import *


class CSRInterface(Interface):

  def __init__(s):
    super(CSRInterface, s).__init__([
        MethodSpec(
            'get',
            args={},
            rets={
                'msg': ExecuteMsg(),
            },
            call=True,
            rdy=True,
        ),
    ])


class CSR(Model):

  def __init__(s, interface):
    UseInterface(s, interface)
    s.require(
        MethodSpec(
            'dispatch_get',
            args=None,
            rets={
                'msg': DispatchMsg(),
            },
            call=True,
            rdy=True,
        ),
        MethodSpec(
            'csr_op',
            args={
                'csr': Bits(CSR_SPEC_NBITS),
                'op': Bits(CSROpType.bits),
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
    )

    s.execute_val = Register(
        RegisterInterface(Bits(1), True, False), reset_value=0)
    s.execute_msg = Register(RegisterInterface(ExecuteMsg(), True, False))

    s.advance = Wire(1)

    @s.combinational
    def handle_advance():
      s.advance.v = (not s.execute_val.read_data or
                     s.get_call) and s.dispatch_get_rdy

    s.connect(s.get_rdy, s.execute_val.read_data)
    s.connect(s.get_msg, s.execute_msg.read_data)

    s.connect(s.dispatch_get_call, s.advance)
    s.connect(s.execute_msg.write_call, s.advance)

    @s.combinational
    def handle_writeback():
      s.execute_val.write_call.v = 0
      s.execute_val.write_data.v = 0
      s.execute_msg.write_data.v = 0
      s.execute_msg.write_data.hdr.v = s.dispatch_get_msg.hdr

      s.csr_op_csr.v = 0
      s.csr_op_op.v = 0
      s.csr_op_rs1_is_x0.v = 0
      s.csr_op_value.v = 0
      s.csr_op_call.v = 0

      if s.advance:
        s.execute_val.write_data.v = 1
        s.execute_val.write_call.v = 1
        if s.dispatch_get_msg.hdr_status == PipelineMsgStatus.PIPELINE_MSG_STATUS_VALID:
          s.execute_msg.write_data.rd_val_pair.v = s.dispatch_get_msg.rd_val_pair

          # TODO do CSR op
        else:
          s.execute_msg.write_data.exception_info.v = s.dispatch_get_msg.exception_info
      else:
        s.execute_val.write_call.v = s.get_call

  def line_trace(s):
    return str(s.execute_msg.read_data)
