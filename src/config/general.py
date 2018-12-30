from pymtl import *
from bitutil import clog2, clog2nz
from bitutil import bit_enum

XLEN = 64
XLEN_BYTES = XLEN // 8
ILEN = 32
ILEN_BYTES = ILEN // 8

CSR_SPEC_LEN = 12

ROB_SIZE = 8
ROB_TAG_LEN = clog2( ROB_SIZE )

DECODED_IMM_LEN = 32

RESET_VECTOR = Bits( XLEN, 0x200 )

REG_COUNT = 32
REG_SPEC_LEN = clog2( REG_COUNT )

REG_TAG_COUNT = 64
REG_TAG_LEN = clog2( REG_TAG_COUNT )
INST_TAG_LEN = ROB_TAG_LEN

MAX_SPEC_DEPTH = 4
MAX_SPEC_DEPTH_LEN = clog2( MAX_SPEC_DEPTH + 1 )

BIT32_MASK = Bits( 32, 0xFFFFFFFF )
