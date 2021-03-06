from pymtl import *
from lizard.bitutil import clog2
from lizard.util.rtl.method import MethodSpec
from lizard.util.rtl.interface import Interface, UseInterface
from lizard.util.rtl.register import Register, RegisterInterface


class DivideInterface(Interface):

  def __init__(s, data_len):
    s.DataLen = data_len
    super(DivideInterface, s).__init__([
        MethodSpec(
            'preempt',
            args=None,
            rets=None,
            call=True,
            rdy=False,
        ),
        MethodSpec(
            'result',
            args=None,
            rets={
                'quotient': Bits(s.DataLen),
                'rem': Bits(s.DataLen),
            },
            call=True,
            rdy=True,
        ),
        MethodSpec(
            'div',
            args={
                'dividend': Bits(s.DataLen),
                'divisor': Bits(s.DataLen),
                'signed': Bits(1),
            },
            rets=None,
            call=True,
            rdy=True,
        ),
    ])


class NonRestoringDividerStepInterface(Interface):

  def __init__(s, data_len):
    s.DataLen = data_len
    super(NonRestoringDividerStepInterface, s).__init__([
        MethodSpec(
            'div',
            args={
                'acc': Bits(s.DataLen + 1),
                'divisor': Bits(s.DataLen),
                'dividend': Bits(s.DataLen),
            },
            rets={
                'acc_next': Bits(s.DataLen +
                                 1),  # Eventually becomes the remainder
                'dividend_next': Bits(s.DataLen
                                     ),  # Eventually becomes the quotient
            },
            call=False,
            rdy=False,
        ),
    ])


class NonRestoringDividerStep(Model):

  def __init__(s, interface, nsteps=1):
    UseInterface(s, interface)
    s.acc_shift = Wire(s.interface.DataLen + 1)
    dlen = s.interface.DataLen

    # PTMTL_BROKEN
    s.acc_next_end_ = Wire(1)
    s.div_dividend_end_ = Wire(1)

    @s.combinational
    def eval(end=dlen - 1, aend=dlen, acc_len=dlen + 1):
      s.div_acc_next.v = s.div_acc
      s.div_dividend_next.v = s.div_dividend
      for i in range(nsteps):
        s.div_dividend_end_.v = s.div_dividend_next[end]
        s.acc_shift.v = (s.div_acc_next.v << 1) | zext(s.div_dividend_end_,
                                                       acc_len)
        if s.div_acc_next.v[aend]:  # Negative, so add
          s.div_acc_next.v = s.acc_shift.v + s.div_divisor
        else:  # Otherwise subtract
          s.div_acc_next.v = s.acc_shift.v - s.div_divisor
        s.acc_next_end_.v = not s.div_acc_next[aend]
        s.div_dividend_next.v = s.div_dividend_next << 1 | zext(
            s.acc_next_end_, aend)


class NonRestoringDivider(Model):

  def __init__(s, interface, ncycles):
    UseInterface(s, interface)
    assert s.interface.DataLen % ncycles == 0
    nsteps = s.interface.DataLen // ncycles
    END = s.interface.DataLen - 1
    AEND = s.interface.DataLen
    iface = NonRestoringDividerStepInterface(s.interface.DataLen)
    s.unit = NonRestoringDividerStep(iface, nsteps)

    s.acc = Register(RegisterInterface(s.interface.DataLen + 1, enable=True))
    s.divisor = Register(RegisterInterface(s.interface.DataLen, enable=True))
    s.dividend = Register(RegisterInterface(s.interface.DataLen, enable=True))
    # Set if we need to take twos compliment at end
    s.negate = Register(RegisterInterface(1, enable=True))
    s.negate_rem = Register(RegisterInterface(1, enable=True))
    s.connect(s.negate.write_call, s.div_call)
    s.connect(s.negate_rem.write_call, s.div_call)
    s.connect(s.divisor.write_call, s.div_call)

    # Connect up the unit
    s.connect(s.unit.div_acc, s.acc.read_data)
    s.connect(s.unit.div_divisor, s.divisor.read_data)
    s.connect(s.unit.div_dividend, s.dividend.read_data)

    s.counter = Register(RegisterInterface(clog2(ncycles + 1), enable=True))
    s.busy = Register(RegisterInterface(1, enable=True), reset_value=0)

    @s.combinational
    def handle_calls():
      # Arguments
      s.div_rdy.v = not s.busy.read_data or s.result_call
      # Results
      s.result_rdy.v = s.busy.read_data and s.counter.read_data == 0
      s.result_quotient.v = s.dividend.read_data
      s.result_rem.v = s.acc.read_data[:s.interface.DataLen]
      # Figure out if we need to negative
      s.negate.write_data.v = s.div_signed and (s.div_divisor[END]
                                                ^ s.div_dividend[END])
      s.negate_rem.write_data.v = s.div_signed and s.div_dividend[END]

    @s.combinational
    def handle_counter():
      s.counter.write_call.v = s.counter.read_data != 0 or s.div_call
      s.counter.write_data.v = 0
      if s.div_call:
        s.counter.write_data.v = ncycles
      else:
        s.counter.write_data.v = s.counter.read_data - 1

    @s.combinational
    def set_div_regs():
      s.acc.write_call.v = s.div_call or s.counter.read_data > 0
      s.dividend.write_call.v = s.div_call or s.counter.read_data > 0

      # Load the values
      s.acc.write_data.v = 0
      s.divisor.write_data.v = 0
      s.divisor.write_data.v = ~s.div_divisor + 1 if (
          s.div_signed and s.div_divisor[END]) else s.div_divisor
      s.dividend.write_data.v = ~s.div_dividend + 1 if (
          s.div_signed and s.div_dividend[END]) else s.div_dividend

      if not s.div_call:
        s.dividend.write_data.v = s.unit.div_dividend_next
        s.acc.write_data.v = s.unit.div_acc_next
        # Special case last cycle
        if s.counter.read_data == 1:
          if s.unit.div_acc_next[AEND]:
            s.acc.write_data.v += s.divisor.read_data
          if s.negate_rem.read_data:  # Last cycle, compliment
            s.acc.write_data.v = ~s.acc.write_data + 1
          # Only if not divided by zero
          if s.negate.read_data and s.divisor.read_data != 0:
            s.dividend.write_data.v = ~s.dividend.write_data + 1

    @s.combinational
    def handle_busy():
      s.busy.write_call.v = s.div_call or s.result_call or s.preempt_call
      s.busy.write_data.v = s.div_call
