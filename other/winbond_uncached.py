from micropython import const


class W25QFlash:
    SECTOR_SIZE = const(4096)
    BLOCK_SIZE = const(512)
    PAGE_SIZE = const(256)
    
    def __init__(self, spi, cs, baud=40000000):
        self.cs = cs
        self.spi = spi
        self.cs.init(self.cs.OUT, value=1)
        self.spi.init(baudrate=baud, phase=1, polarity=1)  # highest possible baudrate is 40 MHz for ESP-12

        self._cache = bytearray(self.SECTOR_SIZE)  # buffer for writing single blocks
        self._CAPACITY = self.identify()  # calc number of bytes (and makes sure the chip is detected and supported)
        self._ADR_LEN = 3 if (len(bin(self._CAPACITY-1))-2) <= 24 else 4  # address length (default: 3 bytes, 32MB+: 4)
        # setup address mode:
        if self._ADR_LEN == 4:
            if not self._read_status_reg(16):  # not in 4-byte mode
                #print("entering 4-byte address mode")
                self._await()
                self.cs(0)
                self.spi.write(b'\xB7')  # 'Enter 4-Byte Address Mode'
                self.cs(1)

    def identify(self):
        # Determines manufacturer and device id and raises an error if the device is not detected or
        # not supported. Returns the number of blocks (calculated based on the detected chip).

        self._await()
        self.cs(0)
        self.spi.write(b'\x9F')  # 'Read JEDEC ID'
        mf, mem_type, cap = self.spi.read(3, 0x00)  # manufacturer id, memory type id, capacity id
        self.cs(1)

        if not (mf and mem_type and cap):  # something is 0x00
            raise OSError("device not responding, check wiring. (%s, %s, %s)" % (hex(mf), hex(mem_type), hex(cap)))
        if mf != 0xEF or mem_type not in [0x40, 0x60]:  # Winbond manufacturer, Q25 series memory (tested 0x40 only)
            raise OSError("manufacturer (%s) or memory type (%s) not supported" % (hex(mf), hex(mem_type)))
        #print("manufacturer:", hex(mf))
        #print("device:", hex(mem_type << 8 | cap))
        #print("capacity: %d bytes" % int(2**cap))
        return 2**cap  # calculate number of bytes

    def format(self):
        # Performs a chip erase, which resets all memory to 0xFF (might take a few seconds/minutes).
        # Important: Run os.VfsFat.mkfs(flash) to make the flash an accessible file system.
        #            As always, you will then need to run os.mount(flash, '/MyFlashDir') then.
        self._wren()
        self._await()
        self.cs(0)
        self.spi.write(b'\xC7')  # 'Chip Erase'
        self.cs(1)
        self._await()  # wait for the chip to finish formatting

    def _read_status_reg(self, nr):  # Returns the value (0 or 1) in status register <nr> (S0, S1, S2, ...)
        reg, bit = divmod(nr, 8)
        self.cs(0)
        self.spi.write((b'\x05', b'\x35', b'\x15')[reg])  # 'Read Status Register-...' (1, 2, 3)
        stat = 2**bit & self.spi.read(1, 0xFF)[0]
        self.cs(1)
        return stat

    def _await(self):  # Waits for device not to be busy and returns if so
        self.cs(0)
        self.spi.write(b'\x05')  # 'Read Status Register-1'
        while 0x1 & self.spi.read(1, 0xFF)[0]:  # last bit (1) is BUSY bit in stat. reg. byte (0 = not busy, 1 = busy)
            pass
        self.cs(1)

    def _sector_erase(self, addr):  # Resets all memory within the specified sector (4KB) to 0xFF
        self._wren()
        self._await()
        self.cs(0)
        self.spi.write(b'\x20')  # 'Sector Erase'
        self.spi.write(addr.to_bytes(self._ADR_LEN, 'big'))
        self.cs(1)

    def _read(self, buf, addr):
        # Reads len(<buf>) bytes from the chip - starting at <addr> - into <buf>. To keep things
        # easy, len(<buf>) has to be a multiple of self.SECTOR_SIZE (or even better: less than that).
        #print("read %d bytes starting at %s" % (len(buf), hex(addr)))
        #assert addr+len(buf) <= self._CAPACITY, \
        #    "memory not addressable at %s with range %d (max.: %s)" % \
        #    (hex(addr), len(buf), hex(self._CAPACITY-1))

        self._await()
        self.cs(0)
        self.spi.write(b'\x0C' if self._ADR_LEN == 4 else b'\x0B')  # 'Fast Read' (0x03 = default), 0x0C for 4-byte mode
        self.spi.write(addr.to_bytes(self._ADR_LEN, 'big'))
        self.spi.write(b'\xFF')  # dummy byte
        self.spi.readinto(buf, 0xFF)
        self.cs(1)

    def _wren(self):  # Sets the Write Enable Latch (WEL) bit in the status register
        self._await()
        self.cs(0)
        self.spi.write(b'\x06')  # 'Write Enable'
        self.cs(1)

    def _write(self, buf, addr):
        # Writes the data from <buf> to the device starting at <addr>, which has to be erased (0xFF)
        # before. Last byte of <addr> has to be zero, which means <addr> has to be a multiple of
        # self.PAGE_SIZE (= start of page), because wrapping to the next page (if page size exceeded)
        # is implemented for full pages only. Length of <buf> has to be a multiple of self.PAGE_SIZE,
        # because only full pages are supported at the moment (<addr> will be auto-incremented).
        #print("write buf[%d] to %s (%d)" % (len(buf), hex(addr), addr))
        #assert len(buf) % self.PAGE_SIZE == 0, "invalid buffer length: %d" % len(buf)
        #assert not addr & 0xf, "address (%d) not at page start" % addr
        #assert addr+len(buf) <= self._CAPACITY, \
        #    "memory not addressable at %s with range %d (max.: %s)" % \
        #    (hex(addr), len(buf), hex(self._CAPACITY-1))

        for i in range(0, len(buf), self.PAGE_SIZE):
            self._wren()
            self._await()
            self.cs(0)
            self.spi.write(b'\x02')  # 'Page Program'
            self.spi.write(addr.to_bytes(self._ADR_LEN, 'big'))
            self.spi.write(buf[i:i+self.PAGE_SIZE])
            addr += self.PAGE_SIZE
            self.cs(1)

    def _writeblock(self, blocknum, buf):
        # To write a block, the sector (eg 4kB = 8 blocks) has to be erased first. Therefore, a sector will be read
        # and saved in cache first, then the given block will be replaced and the whole sector written back when
        #assert len(buf) == self.BLOCK_SIZE, "invalid block length: %d" % len(buf)
        #print("writeblock(%d, buf[%d])" % (blocknum, len(buf)))

        sector_nr = blocknum // 8
        sector_addr = sector_nr * self.SECTOR_SIZE
        index = (blocknum << 9) & 0xfff  # index of first byte of page in sector (multiple of self.PAGE_SIZE)

        self._read(self._cache, sector_addr)
        self._cache[index:index+self.BLOCK_SIZE] = buf  # apply changes
        self._sector_erase(sector_addr)
        self._write(self._cache, sector_addr)  # addr is multiple of self.SECTOR_SIZE, so last byte is zero

    def readblocks(self, blocknum, buf):
        # Read data from the chip starting at block number <blocknum> to <buf> (len = multiple of self.BLOCK_SIZE)
        #print("READ %d bytes starting at block %d" % (len(buf), blocknum))
        #assert len(buf) % self.BLOCK_SIZE == 0, 'invalid buffer length: %d' % len(buf)

        buf_len = len(buf)
        if buf_len == self.BLOCK_SIZE:
            self._read(buf, blocknum << 9)
        else:
            offset = 0
            buf_mv = memoryview(buf)
            while offset < buf_len:
                self._read(buf_mv[offset:offset+self.BLOCK_SIZE], blocknum << 9)
                offset += self.BLOCK_SIZE
                blocknum += 1

    def writeblocks(self, blocknum, buf):
        # Writes the content from <buf> (len must be multiple of self.BLOCK_SIZE) to block number <blocknum>
        #print("WRITE %d bytes starting at block %d" % (len(buf), blocknum))
        #assert len(buf) % self.BLOCK_SIZE == 0, 'invalid buffer length: %d' % len(buf)

        buf_len = len(buf)
        if buf_len == self.BLOCK_SIZE:
            self._writeblock(blocknum, buf)
        else:
            offset = 0
            buf_mv = memoryview(buf)
            while offset < buf_len:
                self._writeblock(blocknum, buf_mv[offset:offset+self.BLOCK_SIZE])
                offset += self.BLOCK_SIZE
                blocknum += 1

    def count(self):  # Returns the number of blocks (self.BLOCK_SIZE bytes) available on the device
        return int(self._CAPACITY / self.BLOCK_SIZE)
