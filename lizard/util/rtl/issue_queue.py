from pymtl import *
from lizard.bitutil import clog2
from lizard.util.rtl.pipeline_stage import gen_valid_value_manager
from lizard.util.rtl.register import Register, RegisterInterface
from lizard.util.rtl.method import MethodSpec
from lizard.util.rtl.interface import Interface, UseInterface
from lizard.util.rtl.types import canonicalize_type


class AbstractIssueType(BitStructDefinition):

  def __init__(s, src_tag, opaque, KillOpaqueType):
    s.src0_val = BitField(1)
    s.src0_rdy = BitField(1)
    s.src0 = BitField(canonicalize_type(src_tag).nbits)
    s.src1_val = BitField(1)
    s.src1_rdy = BitField(1)
    s.src1 = BitField(canonicalize_type(src_tag).nbits)
    # A custom opaque field for passing private info
    s.opaque = BitField(canonicalize_type(opaque).nbits)
    s.kill_opaque = BitField(canonicalize_type(KillOpaqueType).nbits)
    s.ordered = BitField(1)  # This is ignore if the interface is not ordered


class IssueQueueSlotInterface(Interface):

  def __init__(s, slot_type, KillArgType, num_notify, with_order=False):
    s.SlotType = slot_type
    s.SrcTag = Bits(slot_type.src0.nbits)
    s.Opaque = Bits(slot_type.opaque.nbits)
    s.KillArgType = KillArgType

    s.NumNotify = num_notify
    s.WithOrder = with_order

    status_rets = {'valid': Bits(1), 'ready': Bits(1)}
    if s.WithOrder:
      status_rets['ordered'] = Bits(1)
    super(IssueQueueSlotInterface, s).__init__(
        [
            MethodSpec(
                'status',
                args=None,
                rets=status_rets,
                call=False,
                rdy=False,
            ),
            MethodSpec(
                'input',
                args={
                    'value': s.SlotType,
                },
                rets=None,
                call=True,
                rdy=False,
            ),
            MethodSpec(
                'peek',
                args=None,
                rets={
                    'value': s.SlotType,
                },
                call=False,
                rdy=False,
            ),
            MethodSpec(
                'take',
                args=None,
                rets={},
                call=True,
                rdy=False,
            ),
            MethodSpec(
                'notify',
                args={
                    'tag': s.SrcTag.nbits,
                },
                rets=None,
                call=True,
                rdy=False,
                count=num_notify,
            ),
            MethodSpec(
                'kill_notify',
                args={
                    'msg': s.KillArgType,
                },
                rets=None,
                call=False,
                rdy=False,
            ),
        ],
        ordering_chains=[['notify', 'status', 'peek', 'take', 'input']],
    )


class GenericIssueSlot(Model):
  """
  make_kill is a lambda that generates a something that has DropControllerInterface

  """

  def __init__(s, interface, make_kill, bypass_ready=True):
    """ This model implements a generic issue slot, an issue queue has an instance
      of this for each slot in the queue

      SlotType: Should subclass AbstractSlotType and add any additional fields
    """
    UseInterface(s, interface)

    # The storage for everything
    #s.valid_ = Register(RegisterInterface(Bits(1)), reset_value=0)

    # Make the valid manager from the DropControllerInterface passed in
    s.val_manager_ = gen_valid_value_manager(make_kill)()

    s.opaque_ = Register(RegisterInterface(s.interface.Opaque, enable=True))
    s.src0_ = Register(RegisterInterface(s.interface.SrcTag, enable=True))
    s.src0_val_ = Register(RegisterInterface(Bits(1), enable=True))
    s.src0_rdy_ = Register(RegisterInterface(Bits(1), enable=True))
    s.src1_ = Register(RegisterInterface(s.interface.SrcTag, enable=True))
    s.src1_val_ = Register(RegisterInterface(Bits(1), enable=True))
    s.src1_rdy_ = Register(RegisterInterface(Bits(1), enable=True))
    if s.interface.WithOrder:
      s.ordered_ = Register(RegisterInterface(Bits(1), enable=True))
      s.connect(s.peek_value.ordered, s.ordered_.read_data)
      s.connect(s.status_ordered, s.ordered_.read_data)
      s.connect(s.ordered_.write_data, s.input_value.ordered)
      s.connect(s.ordered_.write_call, s.input_call)

    s.srcs_ready_ = Wire(1)
    s.kill_ = Wire(1)

    # Does it match this cycle?
    s.src0_match_ = Wire(1)
    s.src1_match_ = Wire(1)

    # Connect the output method
    s.connect(s.peek_value.opaque, s.opaque_.read_data)
    s.connect(s.peek_value.src0, s.src0_.read_data)
    s.connect(s.peek_value.src0_val, s.src0_val_.read_data)
    s.connect(s.peek_value.src1, s.src1_.read_data)
    s.connect(s.peek_value.src1_val, s.src1_val_.read_data)

    # Connect inputs into registers
    s.connect(s.opaque_.write_data, s.input_value.opaque)
    s.connect(s.src0_.write_data, s.input_value.src0)
    s.connect(s.src0_val_.write_data, s.input_value.src0_val)
    s.connect(s.src1_.write_data, s.input_value.src1)
    s.connect(s.src1_val_.write_data, s.input_value.src1_val)

    # Connect all the enables
    s.connect(s.opaque_.write_call, s.input_call)
    s.connect(s.src0_.write_call, s.input_call)
    s.connect(s.src0_val_.write_call, s.input_call)
    s.connect(s.src1_.write_call, s.input_call)
    s.connect(s.src1_val_.write_call, s.input_call)

    # Connect up val manager
    s.connect(s.val_manager_.add_msg, s.input_value.kill_opaque)
    s.connect(s.peek_value.kill_opaque, s.val_manager_.peek_msg)
    s.connect(s.val_manager_.add_call, s.input_call)
    s.connect(s.status_valid, s.val_manager_.peek_rdy)
    s.connect(s.val_manager_.take_call, s.take_call)
    # Lift the global kill notify signal
    s.connect_m(s.val_manager_.kill_notify, s.kill_notify)

    s.src0_notify_match = Wire(s.interface.NumNotify)
    s.src1_notify_match = Wire(s.interface.NumNotify)

    @s.combinational
    def match_src():
      for i in range(s.interface.NumNotify):
        s.src0_notify_match[i].v = s.src0_val_.read_data and s.notify_call[
            i] and (s.src0_.read_data == s.notify_tag[i])
        s.src1_notify_match[i].v = s.src1_val_.read_data and s.notify_call[
            i] and (s.src1_.read_data == s.notify_tag[i])

      s.src0_match_.v = reduce_or(s.src0_notify_match)
      s.src1_match_.v = reduce_or(s.src1_notify_match)

    @s.combinational
    def handle_ready():
      s.peek_value.src0_rdy.v = s.src0_rdy_.read_data or s.src0_match_
      s.peek_value.src1_rdy.v = s.src1_rdy_.read_data or s.src1_match_
      s.status_ready.v = s.status_valid and s.srcs_ready_

    if bypass_ready:

      @s.combinational
      def handle_srcs_ready():
        s.srcs_ready_.v = s.peek_value.src0_rdy and s.peek_value.src1_rdy
    else:

      @s.combinational
      def handle_srcs_ready():
        s.srcs_ready_.v = s.src0_rdy_.read_data and s.src1_rdy_.read_data

    @s.combinational
    def set_reg_rdy():
      s.src0_rdy_.write_call.v = s.input_call or (s.src0_match_ and
                                                  s.status_valid)
      s.src1_rdy_.write_call.v = s.input_call or (s.src1_match_ and
                                                  s.status_valid)

      if s.input_call:
        s.src0_rdy_.write_data.v = s.input_value.src0_rdy or not s.input_value.src0_val
        s.src1_rdy_.write_data.v = s.input_value.src1_rdy or not s.input_value.src1_val
      else:
        s.src0_rdy_.write_data.v = s.src0_match_
        s.src1_rdy_.write_data.v = s.src1_match_

  def line_trace(s):
    return str(s.val_manager.peek_rdy)


class IssueQueueInterface(Interface):

  def __init__(s, slot_type, KillArgType, num_notify, ordered=True):
    s.SlotType = slot_type
    s.SrcTag = Bits(slot_type.src0.nbits)
    s.Opaque = Bits(slot_type.opaque.nbits)
    s.KillArgType = KillArgType
    s.NumNotify = num_notify
    s.Ordered = ordered

    super(IssueQueueInterface, s).__init__([
        MethodSpec(
            'add', args={
                'value': s.SlotType,
            }, rets=None, call=True, rdy=True),
        MethodSpec(
            'remove',
            args=None,
            rets={
                'value': s.SlotType,
            },
            call=True,
            rdy=True),
        MethodSpec(
            'notify',
            args={
                'tag': s.SrcTag.nbits,
            },
            rets=None,
            call=True,
            rdy=False,
            count=num_notify),
        MethodSpec(
            'kill_notify',
            args={
                'msg': s.KillArgType,
            },
            rets=None,
            call=False,
            rdy=False),
    ])


class CompactingIssueQueue(Model):

  def __init__(s, interface, make_kill, num_slots=4, bypass_ready=False):
    """ This model implements a generic issue queue

      create_slot: A function that instatiates a model that conforms
                    to the IssueSlot interface. In most cases, GenericIssueSlot
                    can be used instead of having to implement your own model

      input_type: the data type that wil be passed via the input() method
                  to the issue slot

      SlotType: A Bits() or BitStruct() that contains the data stored in each issue slot (IS)

      NotifyType: A Bits() or BitStruct() that will be passed in as an arg to the notify method

      BranchType: A Bits() or BitStruct() that will be broadcasted to each IS when a branch/kill event happens

      num_slots: The number of slots in the IQ
    """
    UseInterface(s, interface)

    # Create all the slots in our issue queue
    s.slots_ = [
        GenericIssueSlot(
            IssueQueueSlotInterface(
                s.interface.SlotType,
                s.interface.KillArgType,
                s.interface.NumNotify,
                with_order=s.interface.Ordered), make_kill, bypass_ready)
        for _ in range(num_slots)
    ]

    # nth entry is shifted from nth slot to n-1 slot
    s.do_shift_ = [Wire(1) for _ in range(num_slots - 1)]
    s.will_issue_ = [Wire(1) for _ in range(num_slots)]

    s.prev_rdy_ = Wire(num_slots)
    s.first_rdy_ = Wire(num_slots)

    # PYMTL-BROKEN: array -> bitstruct -> element assignment broken
    s.last_slot_in_ = Wire(s.interface.SlotType)

    if s.interface.Ordered:
      s.wait_pred = Wire(num_slots)

      s.prev_ordered = Wire(num_slots)
      s.prev_nonordered = Wire(num_slots)

      @s.combinational
      def set_wait_pred_0():
        # Is there a ordered predicessor
        s.prev_ordered[0].v = 0
        # Is there non-ordered predecessor
        s.prev_nonordered[0].v = 0
        s.wait_pred[0].v = 0

      @s.combinational
      def set_wait_pred_k():
        for i in range(1, num_slots):
          s.prev_ordered[i].v = s.prev_ordered[i - 1] or (
              s.slots_[i - 1].status_valid and s.slots_[i - 1].status_ordered)
          s.prev_nonordered[i].v = s.prev_nonordered[i - 1] or (
              s.slots_[i - 1].status_valid and
              not s.slots_[i - 1].status_ordered)
          if s.slots_[i].status_ordered:  # If ordered, must make sure first one
            s.wait_pred[i].v = s.prev_ordered[i] or s.prev_nonordered[i]
          else:  # Otherwise only need to make sure there is not aordered predecessor
            s.wait_pred[i].v = s.prev_ordered[i]

    @s.combinational
    def set_first_rdy():
      s.prev_rdy_[0].v = s.slots_[0].status_ready
      s.first_rdy_[0].v = s.slots_[0].status_ready

    @s.combinational
    def set_first_rdy():
      for i in range(1, num_slots):
        s.prev_rdy_[i].v = s.prev_rdy_[i - 1].v or s.slots_[i].status_ready
        s.first_rdy_[i].v.v = not s.prev_rdy_[i -
                                              1].v and s.slots_[i].status_ready

    @s.combinational
    def mux_output():
      s.remove_value.v = 0
      for i in range(num_slots):
        if s.first_rdy_[i]:
          s.remove_value.v = s.slots_[i].peek_value

    @s.combinational
    def last_slot_input():
      s.slots_[num_slots - 1].input_value.v = s.last_slot_in_.v

    # if ith slot shitting, ith slot input called, and i+1 output called
    for i in range(num_slots - 1):

      @s.combinational
      def slot_input(i=i):
        s.slots_[i].input_call.v = s.do_shift_[i]
        s.slots_[i].input_value.v = s.slots_[i + 1].peek_value

    # Broadcast kill and notify signal to each slot
    for i in range(num_slots):
      # Kill signal
      s.connect_m(s.slots_[i].kill_notify, s.kill_notify)
      # preg notify signal
      s.connect_m(s.slots_[i].notify, s.notify)

    # We need to forward the notify from the current cycle into the input

    s.src0_notify_match = Wire(s.interface.NumNotify)
    s.src1_notify_match = Wire(s.interface.NumNotify)

    @s.combinational
    def match_src():
      for i in range(s.interface.NumNotify):
        s.src0_notify_match[i].v = s.notify_call[i] and (
            s.add_value.src0 == s.notify_tag[i])
        s.src1_notify_match[i].v = s.notify_call[i] and (
            s.add_value.src1 == s.notify_tag[i])

    @s.combinational
    def handle_add():
      s.slots_[num_slots - 1].input_call.v = s.add_call
      s.last_slot_in_.v = s.add_value
      # Forward any notifications from current cycle
      s.last_slot_in_.src0_rdy.v = reduce_or(
          s.src0_notify_match) or s.add_value.src0_rdy
      s.last_slot_in_.src1_rdy.v = reduce_or(
          s.src1_notify_match) or s.add_value.src1_rdy

    if num_slots > 1:

      @s.combinational
      def shift0():
        # The 0th slot only shifts in if invalid or issuing
        s.do_shift_[0].v = (not s.slots_[0].status_valid or
                            s.will_issue_[0]) and (s.slots_[1].status_valid and
                                                   not s.will_issue_[1])

    for i in range(1, num_slots - 1):

      @s.combinational
      def shiftk(i=i):
        # We can only shift in if current slot is invalid, issuing, or shifting out
        # and predicessor is valid, and not issuing
        s.do_shift_[i].v = (not s.slots_[i].status_valid or s.will_issue_[i] or
                            s.do_shift_[i - 1]) and (
                                s.slots_[i + 1].status_valid and
                                not s.will_issue_[i + 1])

    @s.combinational
    def output0():
      # The 0th slot only outputs if issuing
      s.slots_[0].take_call.v = s.will_issue_[0]

    for i in range(1, num_slots):

      @s.combinational
      def outputk(i=i):
        s.slots_[i].take_call.v = s.will_issue_[i] or s.do_shift_[i - 1]

    # The add call, to add something to the IQ
    @s.combinational
    def add_rdy():
      s.add_rdy.v = not s.slots_[num_slots -
                                 1].status_valid or s.slots_[num_slots -
                                                             1].take_call

    if s.interface.Ordered:

      @s.combinational
      def handle_remove():
        # Must be valid and first entry
        s.remove_rdy.v = s.first_rdy_ != 0 and (
            (s.first_rdy_ & ~s.wait_pred) != 0)
        for i in range(num_slots):
          s.will_issue_[i].v = s.first_rdy_ != 0 and s.remove_call and (
              s.first_rdy_[i] and not s.wait_pred[i])
    else:

      @s.combinational
      def handle_remove():
        s.remove_rdy.v = s.first_rdy_ != 0
        for i in range(num_slots):
          s.will_issue_[i].v = s.remove_call and s.first_rdy_[i]

  def line_trace(s):
    return ":".join(["{}".format(x.valid_out) for x in s.slots_])
