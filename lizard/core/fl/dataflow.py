from pymtl import *

from lizard.model.hardware_model import HardwareModel, Result
from lizard.model.flmodel import FLModel
from lizard.core.fl.renametable import RenameTableFL
from lizard.util.fl.registerfile import RegisterFileFL
from lizard.util.fl.snapshotting_freelist import SnapshottingFreeListFL


class DataFlowManagerFL(FLModel):

  @HardwareModel.validate
  def __init__(s, dflow_interface):
    super(DataFlowManagerFL, s).__init__(dflow_interface)

    dlen = s.interface.DataLen
    naregs = s.interface.NumAregs
    npregs = s.interface.NumPregs
    nsnapshots = s.interface.NumSnapshots
    nstore_queue = s.interface.NumStoreQueue
    num_src_ports = s.interface.NumSrcPorts
    num_dst_ports = s.interface.NumDstPorts
    num_is_ready_ports = s.interface.NumIsReadyPorts
    num_forward_ports = s.interface.NumForwardPorts

    s.state(
        snapshot_allocator=SnapshottingFreeListFL(nsnapshots, 1, 1, nsnapshots),
        free_regs=SnapshottingFreeListFL(
            npregs - 1,
            num_dst_ports,
            num_dst_ports,
            nsnapshots,
            used_slots_initial=naregs - 1),
        store_ids=SnapshottingFreeListFL(nstore_queue, num_dst_ports,
                                         num_dst_ports, nsnapshots),
    )
    arch_used_pregs_reset = [Bits(1, 0) for _ in range(npregs - 1)]
    for i in range(naregs):
      arch_used_pregs_reset[i] = Bits(1, 1)

    s.state(
        arch_used_pregs=RegisterFileFL(
            Bits(1),
            npregs - 1,
            0,
            num_dst_ports * 2,
            False,
            True,
            reset_values=arch_used_pregs_reset))

    initial_map = [0] + [x for x in range(naregs - 1)]
    s.state(
        rename_table=RenameTableFL(naregs, npregs, num_src_ports, num_dst_ports,
                                   nsnapshots, True, initial_map))
    s.ZERO_TAG = s.rename_table.ZERO_TAG

    preg_reset = [0 for _ in range(npregs)]
    ready_reset = [1 for _ in range(npregs)]

    s.state(
        preg_file=RegisterFileFL(
            Bits(dlen),
            npregs,
            num_is_ready_ports,
            num_dst_ports,
            True,
            False,
            reset_values=preg_reset,
        ),
        ready_table=RegisterFileFL(
            Bits(1),
            npregs,
            num_is_ready_ports,
            num_dst_ports * 2,
            False,
            False,
            reset_values=ready_reset,
        ),
        areg_file=RegisterFileFL(
            s.interface.Preg,
            naregs,
            num_dst_ports,
            num_dst_ports,
            False,
            True,
            reset_values=initial_map,
        ),
        updated=[],
        forwarded={},
    )

    @s.model_method
    def free_store_id(id_):
      s.store_ids.free(id_)

    @s.model_method
    def commit(tag, areg):
      if tag == s.ZERO_TAG:
        return
      old_preg = s.areg_file.read(areg).data
      s.free_regs.free(old_preg)
      s.areg_file.write(addr=areg, data=tag)
      s.arch_used_pregs.write(addr=old_preg, data=0)
      s.arch_used_pregs.write(addr=tag, data=1)

    @s.model_method
    def write(tag, value):
      if tag == s.ZERO_TAG:
        return
      s.preg_file.write(addr=tag, data=value)
      s.ready_table.write(addr=tag, data=1)
      s.updated.append(tag)

    @s.model_method
    def forward(tag, value):
      if tag == s.ZERO_TAG:
        return
      s.forwarded[int(tag)] = int(value)

    @s.model_method
    def get_updated():
      len_ = s.interface['get_updated'].rets['tags'].length
      tags = [0] * len_
      valid = [0] * len_
      i = 0
      for preg in s.updated:
        tags[i] = preg
        valid[i] = 1
        i += 1
      for preg in s.forwarded.keys():
        tags[i] = preg
        valid[i] = 1
        i += 1
      s.updated = []
      return Result(tags=tags, valid=valid)

    @s.model_method
    def get_src(areg):
      return s.rename_table.lookup(areg).preg

    @s.model_method
    def valid_store_mask():
      state_as_bits = Bits(nstore_queue, s.store_ids.get_state().state)
      return int(~state_as_bits)

    @s.ready_method
    def get_store_id():
      return s.store_ids.alloc.rdy()

    @s.model_method
    def get_store_id():
      return s.store_ids.alloc().index

    @s.ready_method
    def get_dst():
      return s.free_regs.alloc.rdy()

    @s.model_method
    def get_dst(areg):
      if areg == 0:
        return s.ZERO_TAG
      allocation = s.free_regs.alloc()

      s.rename_table.update(areg=areg, preg=allocation.index)
      s.ready_table.write(addr=allocation.index, data=0)

      return allocation.index

    @s.model_method
    def is_ready(tag):
      if tag == s.ZERO_TAG:
        return 1
      else:
        return s.ready_table.read(addr=tag).data

    @s.model_method
    def read(tag):
      if tag == s.ZERO_TAG:
        return 0
      else:
        if int(tag) in s.forwarded:
          return s.forwarded[tag]
        return s.preg_file.read(addr=tag).data

    @s.model_method
    def reset_cl_forwarded():
      s.forwarded = {}

    @s.ready_method
    def snapshot():
      return s.snapshot_allocator.alloc.rdy()

    @s.model_method
    def snapshot():
      id_ = s.snapshot_allocator.alloc().index
      s.snapshot_allocator.reset_alloc_tracking(id_)
      s.free_regs.reset_alloc_tracking(id_)
      s.store_ids.reset_alloc_tracking(id_)
      s.rename_table.snapshot(id_)
      return id_

    @s.model_method
    def free_snapshot(id_):
      s.snapshot_allocator.free(id_)

    @s.model_method
    def restore(source_id):
      s.snapshot_allocator.revert_allocs(source_id)
      s.free_regs.revert_allocs(source_id)
      s.store_ids.revert_allocs(source_id)
      s.rename_table.restore(source_id)

    @s.model_method
    def rollback():
      s.snapshot_allocator.set((~Bits(nsnapshots, 0)).uint())
      arch_used_pregs_packed = Bits(npregs - 1, 0)
      arch_used_pregs_dump = s.arch_used_pregs.dump().out
      for i in range(npregs - 1):
        arch_used_pregs_packed[i] = arch_used_pregs_dump[i]
      s.free_regs.set(~arch_used_pregs_packed)
      s.store_ids.set(~Bits(nstore_queue, 0).uint())
      s.rename_table.set(s.areg_file.dump().out)
