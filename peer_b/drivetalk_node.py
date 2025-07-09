import sys
import socket
import threading
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
import subprocess
import re
from mac_to_ip_map import mac_to_ip_map

# ============ PRESETS DE MENSAGENS ============
PRESETS = {
    "1": "Animais na pista",
    "2": "Buraco na pista",
    "3": "Trânsito lento à frente",
    "4": "Veículo parado à frente",
    "5": "Assaltante na pista",
    "6": "Pode realizar a ultrapassagem",
    "7": "Preciso ultrapassar"
}

# ============ ALCANCE VIA WIFI (Windows) ============
def get_wifi_signal_strength():
    try:
        raw = subprocess.check_output("netsh wlan show interfaces", shell=True)
        output = raw.decode('cp1252', errors='ignore')
        match = re.search(r"(?:Signal|Sinal)\s*[:=]\s*(\d+)%", output)
        return int(match.group(1)) if match else None
    except Exception as e:
        print(f"[ERRO ao obter sinal Wi‑Fi]: {e}")
        return None

threshold = 80  # % mínimo para permitir envio

def is_in_range():
    signal = get_wifi_signal_strength()
    if signal is None:
        print("[AVISO] Não foi possível obter o sinal Wi‑Fi.")
        return False
    print(f"[INFO] Sinal Wi‑Fi atual: {signal}% (threshold: {threshold}%)")
    return signal >= threshold

# ============ CAPTURA DE ÁUDIO ============
class SoundDeviceMicrophone(sr.AudioSource):
    def __init__(self, device=None, samplerate=16000, channels=1):
        self.device = device
        self.samplerate = samplerate
        self.SAMPLE_RATE = samplerate
        self.SAMPLE_WIDTH = 2
        self.channels = channels
        self.CHUNK = 1024

    def __enter__(self):
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            device=self.device,
            channels=self.channels,
            blocksize=self.CHUNK,
            dtype='int16'
        )
        self.stream.start()
        orig = self.stream.read
        self.stream.read = lambda frames, **kw: (orig(frames, **kw)[0].tobytes(), None)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream.stop()
        self.stream.close()

sr.Microphone = SoundDeviceMicrophone

# ============ CONFIGURAÇÃO DE REDE ============
peer_id = sys.argv[1]
my_host, my_port = mac_to_ip_map[peer_id].split(':')
my_port = int(my_port)
other_id = 'PEER_B' if peer_id == 'PEER_A' else 'PEER_A'
other_host, other_port = mac_to_ip_map[other_id].split(':')
other_port = int(other_port)

# ============ TTS THREAD‑SAFE ============
def speak(msg: str):
    engine = pyttsx3.init()
    engine.setProperty('voice', engine.getProperty('voices')[0].id)
    engine.say(msg)
    engine.runAndWait()

# ============ THREAD DE LISTEN ============
def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((my_host, my_port))
    #print(f">>> [{peer_id}] ouvindo em {my_host}:{my_port}")
    while True:
        data, addr = sock.recvfrom(1024)
        msg = data.decode('utf-8')
        print(f"\n[RECEBIDO de {addr}] {msg}")
        threading.Thread(target=speak, args=(msg,), daemon=True).start()

# ============ ENVIO UDP COM ALCANCE ============
def send_udp(msg: str):
    if is_in_range():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(msg.encode('utf-8'), (other_host, other_port))
        print(f"[ENVIADO a {other_host}:{other_port}] {msg}")
    else:
        print("[BLOQUEADO] Fora de alcance. Sinal Wi‑Fi insuficiente.")

# ============ GRAVAÇÃO E ENVIO DE VOZ ============
def recognize_and_send():
    r = sr.Recognizer()
    duration = 3
    fs = 16000
    print(f"Gravando por {duration}s (modo Drive)…")
    rec = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    audio_data = sr.AudioData(rec.tobytes(), fs, 2)
    try:
        text = r.recognize_google(audio_data, language='pt-BR')
        send_udp(f" {text}")
    except sr.UnknownValueError:
        print("Áudio não reconhecido.")

# ============ PROMPT ============
def print_prompt():
    print(f"\n>> [{peer_id}] (t) texto / (p) preset / (v) voz / (q) sair:")
    for key, text in PRESETS.items():
        print(f"   {key}: {text}")
    print(">> ", end="", flush=True)

# ============ MAIN ============
if __name__ == '__main__':
    threading.Thread(target=udp_listener, daemon=True).start()
    print(f"=== Drivetalk simulated node {peer_id} ===")
    print_prompt()
    while True:
        cmd = sys.stdin.readline().strip().lower()
        if cmd == 't':
            msg = input('Digite mensagem curta: ')
            send_udp(msg)
        elif cmd == 'p':
            choice = input('Escolha preset (digite o número): ').strip()
            if choice in PRESETS:
                send_udp(PRESETS[choice])
            else:
                print('Preset inválido.')
        elif cmd == 'v' or cmd == '':
            recognize_and_send()
        elif cmd == 'q':
            print('Encerrando...')
            break
        else:
            print('Comando inválido.')
        print_prompt()
