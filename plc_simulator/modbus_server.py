"""
PLC 模拟器 — Modbus TCP Server (:1502)

轻量实现，使用原生 socket，不依赖 pymodbus。

支持的功能码:
  0x01 读线圈
  0x02 读离散输入
  0x03 读保持寄存器
  0x05 写单线圈
  0x06 写单寄存器
  0x0F 写多线圈
"""
import socket
import struct
import threading
import sys
from typing import Optional, Dict, Callable


HOST = '0.0.0.0'
PORT = 1502


class ModbusMemory:
    """Modbus 数据存储"""

    def __init__(self):
        self.coils = [False] * 10000           # 0xxxx
        self.discrete_inputs = [False] * 10000  # 1xxxx
        self.holding_regs = [0] * 50000        # 4xxxx (16-bit)

    def read_coil(self, addr: int) -> bool:
        return self.coils[addr - 1] if 1 <= addr <= len(self.coils) else False

    def write_coil(self, addr: int, value: bool):
        if 1 <= addr <= len(self.coils):
            self.coils[addr - 1] = value

    def read_discrete(self, addr: int) -> bool:
        return self.discrete_inputs[addr - 1] if 1 <= addr <= len(self.discrete_inputs) else False

    def write_discrete(self, addr: int, value: bool):
        if 1 <= addr <= len(self.discrete_inputs):
            self.discrete_inputs[addr - 1] = value

    def read_holding(self, addr: int) -> int:
        return self.holding_regs[addr - 1] if 1 <= addr <= len(self.holding_regs) else 0

    def write_holding(self, addr: int, value: int):
        if 1 <= addr <= len(self.holding_regs):
            self.holding_regs[addr - 1] = value & 0xFFFF


class PlcSimulatorServer:
    """PLC 模拟器 Modbus TCP Server"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.mem = ModbusMemory()
        self._server: Optional[socket.socket] = None
        self._running = False

        # 线圈写入回调 (addr → callback)
        self._coil_callbacks: Dict[int, Callable] = {}

    def on_coil_write(self, addr: int, callback: Callable[[bool], None]):
        """注册线圈写入回调"""
        self._coil_callbacks[addr] = callback

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._running = True
        print(f"[PLC Sim] Modbus TCP Server 已启动 {self.host}:{self.port}", flush=True)

        while self._running:
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    print(f"[PLC Sim] 连接: {addr}", flush=True)
                    t = threading.Thread(target=self._handle, args=(client, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[PLC Sim] accept 错误: {e}", file=sys.stderr)

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        print("[PLC Sim] 服务已停止", flush=True)

    def _handle(self, client: socket.socket, addr: tuple):
        try:
            client.settimeout(30.0)
            while self._running:
                # 读 MBAP 头 (7 bytes)
                header = self._recv_exact(client, 7)
                if not header:
                    break

                tid, pid, length, uid = struct.unpack('>HHHB', header)
                length -= 1  # 减去 uid

                # 读 PDU
                pdu = self._recv_exact(client, length)
                if not pdu:
                    break

                response = self._process(tid, uid, pdu)
                if response:
                    client.sendall(response)
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            pass
        except Exception as e:
            print(f"[PLC Sim] 客户端 {addr} 错误: {e}", file=sys.stderr)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _recv_exact(self, sock: socket.socket, n: int) -> Optional[bytes]:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _process(self, tid: int, uid: int, pdu: bytes) -> Optional[bytes]:
        if len(pdu) < 1:
            return None

        func = pdu[0]
        try:
            if func == 0x01:
                return self._read_coils(tid, uid, pdu)
            elif func == 0x02:
                return self._read_discrete(tid, uid, pdu)
            elif func == 0x03:
                return self._read_holding(tid, uid, pdu)
            elif func == 0x05:
                return self._write_coil(tid, uid, pdu)
            elif func == 0x06:
                return self._write_register(tid, uid, pdu)
            elif func == 0x0F:
                return self._write_coils(tid, uid, pdu)
            else:
                return self._exception(tid, uid, func, 0x01)
        except Exception as e:
            print(f"[PLC Sim] 处理错误: {e}", file=sys.stderr)
            return self._exception(tid, uid, func, 0x04)

    # ── 读操作 ──

    def _read_coils(self, tid, uid, pdu):
        func = pdu[0]
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        count = struct.unpack('>H', pdu[3:5])[0]
        bits = []
        for i in range(count):
            bits.append('1' if self.mem.read_coil(addr + i) else '0')
        byte_data = []
        for i in range(0, len(bits), 8):
            byte = int(''.join(reversed(bits[i:i+8])), 2)
            byte_data.append(byte)
        resp = struct.pack('>HHHB', tid, 0, 2 + len(byte_data), uid)
        resp += bytes([func, len(byte_data)] + byte_data)
        return resp

    def _read_discrete(self, tid, uid, pdu):
        func = pdu[0]
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        count = struct.unpack('>H', pdu[3:5])[0]
        bits = []
        for i in range(count):
            bits.append('1' if self.mem.read_discrete(addr + i) else '0')
        byte_data = []
        for i in range(0, len(bits), 8):
            byte = int(''.join(reversed(bits[i:i+8])), 2)
            byte_data.append(byte)
        resp = struct.pack('>HHHB', tid, 0, 2 + len(byte_data), uid)
        resp += bytes([func, len(byte_data)] + byte_data)
        return resp

    def _read_holding(self, tid, uid, pdu):
        func = pdu[0]
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        count = struct.unpack('>H', pdu[3:5])[0]
        data = b""
        for i in range(count):
            data += struct.pack('>H', self.mem.read_holding(addr + i))
        resp = struct.pack('>HHHB', tid, 0, 2 + len(data), uid)
        resp += bytes([func, len(data)]) + data
        return resp

    # ── 写操作 ──

    def _write_coil(self, tid, uid, pdu):
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        value = pdu[3] == 0xFF  # 0xFF00 = ON, 0x0000 = OFF
        self.mem.write_coil(addr, value)

        # 回调
        cb = self._coil_callbacks.get(addr)
        if cb:
            try:
                cb(value)
            except Exception:
                pass

        # 响应: echo 请求的前4字节
        return struct.pack('>HHHB', tid, 0, 6, uid) + pdu[:4]

    def _write_register(self, tid, uid, pdu):
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        value = struct.unpack('>H', pdu[3:5])[0]
        self.mem.write_holding(addr, value)
        return struct.pack('>HHHB', tid, 0, 6, uid) + pdu[:4] + struct.pack('>H', 0)

    def _write_coils(self, tid, uid, pdu):
        addr = struct.unpack('>H', pdu[1:3])[0] + 1
        count = struct.unpack('>H', pdu[3:5])[0]
        byte_count = pdu[5]
        for i in range(count):
            byte_idx = i // 8
            bit_idx = i % 8
            value = (pdu[6 + byte_idx] >> bit_idx) & 1
            self.mem.write_coil(addr + i, bool(value))
            cb = self._coil_callbacks.get(addr + i)
            if cb:
                try:
                    cb(bool(value))
                except Exception:
                    pass
        resp = struct.pack('>HHHB', tid, 0, 6, uid)
        resp += struct.pack('>BHH', func, addr - 1, count)
        return resp

    def _exception(self, tid, uid, func, code):
        return struct.pack('>HHHB', tid, 0, 3, uid) + bytes([func | 0x80, code])
