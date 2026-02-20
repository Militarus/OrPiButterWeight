import socket
import struct

HEADER = b'\xF8\x55\xCE'
CMD_GET_WEIGHT = 0xA0
CMD_WEIGHT_RESP = 0x10


# --- CRC из документа 1С ---
def crc16_1c(data: bytes) -> int:
    crc = 0
    for byte in data:
        a = 0
        temp = (crc >> 8) << 8
        for _ in range(8):
            if (temp ^ a) & 0x8000:
                a = ((a << 1) ^ 0x1021) & 0xFFFF
            else:
                a = (a << 1) & 0xFFFF
            temp = (temp << 1) & 0xFFFF
        crc = a ^ ((crc << 8) & 0xFFFF) ^ byte
    return crc & 0xFFFF


def build_packet(command: int, payload: bytes = b'') -> bytes:
    body = bytes([command]) + payload
    length = len(body)
    crc = crc16_1c(body)
    return HEADER + struct.pack('<H', length) + body + struct.pack('<H', crc)


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Связь разорвана")
        data += chunk
    return data


def get_weight(ip: str, port: int = 5001):
    with socket.create_connection((ip, port), timeout=3) as sock:
        sock.sendall(build_packet(CMD_GET_WEIGHT))

        if recv_exact(sock, 3) != HEADER:
            raise RuntimeError("Неверный заголовок")

        length = struct.unpack('<H', recv_exact(sock, 2))[0]
        body = recv_exact(sock, length)
        crc_recv = struct.unpack('<H', recv_exact(sock, 2))[0]

        if crc16_1c(body) != crc_recv:
            raise RuntimeError("CRC не совпадает")

        if body[0] != CMD_WEIGHT_RESP:
            raise RuntimeError(f"Неожиданный ответ {body[0]:02X}")

        weight_raw = struct.unpack('<i', body[1:5])[0]
        division = body[5]
        stable = body[6]

        div_map = {
            0: 0.0001,
            1: 0.001,
            2: 0.01,
            3: 0.1,
            4: 1.0
        }

        return {
            "weight": weight_raw * div_map.get(division, 1),
            "stable": bool(stable),
            "raw": weight_raw,
            "division_code": division
        }


if __name__ == "__main__":
    w = get_weight("192.168.0.100")
    print("Вес:", w["weight"])
    print("Стабилен:", w["stable"])