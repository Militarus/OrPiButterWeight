import socket
import time
import RPi.GPIO as GPIO

# ================= НАСТРОЙКИ =================
SCALE_IP = "10.10.1.80"
SCALE_PORT = 5001

DEVICE_ADDR = 0x01

BUTTON_PIN = 4      # BCM
OUTPUT_PIN = 17     # BCM

PULSE_TIME = 1.0
WEIGHT_THRESHOLD = 0.050
# ============================================


# ================= CRC (из protocol 100) =================
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(frame: bytes) -> bytes:
    crc = crc16(frame)
    return frame + crc.to_bytes(2, byteorder="little")


def check_crc(frame: bytes) -> bool:
    data = frame[:-2]
    received_crc = int.from_bytes(frame[-2:], byteorder="little")
    calculated_crc = crc16(data)
    return received_crc == calculated_crc


# ================= GPIO =================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(OUTPUT_PIN, GPIO.OUT)
GPIO.output(OUTPUT_PIN, GPIO.LOW)


def pulse_output():
    GPIO.output(OUTPUT_PIN, GPIO.HIGH)
    time.sleep(PULSE_TIME)
    GPIO.output(OUTPUT_PIN, GPIO.LOW)


# ================= Протокол =================
def build_weight_request() -> bytes:
    frame = bytes([
        0x02,              # STX
        DEVICE_ADDR,       # адрес
        0x23,              # команда R 0x52
        0x03               # ETX
    ])
    return append_crc(frame)


def parse_weight_response(response: bytes):
    if len(response) < 6:
        print("Ответ слишком короткий")
        return None

    if not check_crc(response):
        print("Ошибка CRC в ответе")
        return None

    if response[0] != 0x02 or response[-3] != 0x03:
        print("Неверная структура кадра")
        return None

    # Данные между ADR и ETX
    data = response[2:-3]
    try:
        weight = float(data.decode().strip())
        return weight
    except:
        print("Ошибка преобразования веса")
        return None


def read_weight():
    try:
        request = build_weight_request()

        with socket.create_connection((SCALE_IP, SCALE_PORT), timeout=2) as s:
            s.sendall(request)
            response = s.recv(1024)

        return parse_weight_response(response)

    except Exception as e:
        print("Ошибка связи:", e)
        return None


# ================= ОСНОВНОЙ ЦИКЛ =================
print("Система запущена")

while True:
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
        time.sleep(0.2)

        weight = read_weight()

        if weight is not None:
            print(f"Вес: {weight} кг")

            if weight >= WEIGHT_THRESHOLD:
                pulse_output()
        else:
            print("Ошибка чтения веса")

        while GPIO.input(BUTTON_PIN) == GPIO.LOW:
            time.sleep(0.05)

    time.sleep(0.05)
