import time
import socket
import struct
import OPi.GPIO as GPIO

# ================= НАСТРОЙКИ =================
BUTTON_PIN = 7          # номер пина (BOARD режим)
SCALE_IP = "192.168.4.137"
SCALE_PORT = 5001

HEADER = b'\xF8\x55\xCE'
CMD_GET_WEIGHT = 0xA0
CMD_WEIGHT_RESP = 0x10
CMD_PING = 0x91
CMD_PING_RESP = 0x51


# =============== CRC (алгоритм 1С) ===============
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


# =============== ПРОТОКОЛ ВЕСОВ ===============
def check_connection():
    with socket.create_connection((SCALE_IP, SCALE_PORT), timeout=2) as sock:
        sock.sendall(build_packet(CMD_PING, b'\x04'))

        recv_exact(sock, 3)
        length = struct.unpack('<H', recv_exact(sock, 2))[0]
        body = recv_exact(sock, length)
        crc_recv = struct.unpack('<H', recv_exact(sock, 2))[0]

        return body[0] == CMD_PING_RESP and crc16_1c(body) == crc_recv


def get_weight():
    with socket.create_connection((SCALE_IP, SCALE_PORT), timeout=2) as sock:
        sock.sendall(build_packet(CMD_GET_WEIGHT))

        recv_exact(sock, 3)
        length = struct.unpack('<H', recv_exact(sock, 2))[0]
        body = recv_exact(sock, length)
        crc_recv = struct.unpack('<H', recv_exact(sock, 2))[0]

        if crc16_1c(body) != crc_recv:
            raise RuntimeError("CRC ошибка")

        weight_raw = struct.unpack('<i', body[1:5])[0]
        division = body[5]
        stable = body[6]

        div_map = {0: 0.0001, 1: 0.001, 2: 0.01, 3: 0.1, 4: 1.0}
        return weight_raw * div_map.get(division, 1), bool(stable)


# =============== GPIO НАСТРОЙКА ===============
GPIO.setmode(GPIO.BOARD)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Система готова. Жду нажатия кнопки...")

try:
    while True:
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:  # кнопка нажата
            print("Кнопка нажата")

            if not check_connection():
                print("Весы не на связи!")
                time.sleep(1)
                continue

            # ждём стабилизации
            for _ in range(10):
                weight, stable = get_weight()
                if stable:
                    print(f"Вес: {weight:.3f} кг (СТАБИЛЕН)")
                    break
                time.sleep(0.3)
            else:
                print("Вес не стабилизировался")

            time.sleep(1)  # защита от дребезга

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
