import socket
import struct
import time
import RPi.GPIO as GPIO

HEADER = b'\xF8\x55\xCE'
CMD_GET_WEIGHT = 0xA0
CMD_WEIGHT_RESP = 0x10
CMD_PING = 0x91
CMD_PING_RESP = 0x51

# --- GPIO настройки ---
BUTTON_PIN = 17      # Кнопка
LED_PIN = 27         # Лампочка

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)


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
        }


def blink_led():
    GPIO.output(LED_PIN, GPIO.HIGH)
    time.sleep(1)
    GPIO.output(LED_PIN, GPIO.LOW)


def main():
    ip = "10.10.1.80"

    print("Готово. Ожидание нажатия кнопки...")

    try:
        while True:
            if GPIO.input(BUTTON_PIN) == GPIO.LOW:  # Кнопка нажата
                print("Кнопка нажата, опрос весов...")

                try:
                    w = get_weight(ip)
                    print("Вес:", w["weight"], "кг")

                    blink_led()  # Успешный опрос → зажигаем лампу

                except Exception as e:
                    print("Ошибка:", e)

                # антидребезг + защита от повторного срабатывания
                while GPIO.input(BUTTON_PIN) == GPIO.LOW:
                    time.sleep(0.05)

                time.sleep(0.2)

            time.sleep(0.05)

    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()