import sys
import socket
import threading
import tkinter as tk
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
import subprocess
import re
from mac_to_ip_map import mac_to_ip_map

# ==== Microfone com sounddevice (sem pyaudio)
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

# ==== Presets e configuração
PRESETS = {
    "1": "Animais na pista",
    "2": "Buraco na pista",
    "3": "Trânsito lento à frente",
    "4": "Veículo parado à frente",
    "5": "Assaltante na pista",
    "6": "Pode realizar a ultrapassagem",
    "7": "Preciso ultrapassar",
    "8": "Obrigado"
}

threshold = 80

peer_id = sys.argv[1]
my_host, my_port = mac_to_ip_map[peer_id].split(':')
my_port = int(my_port)
other_id = 'PEER_B' if peer_id == 'PEER_A' else 'PEER_A'
other_host, other_port = mac_to_ip_map[other_id].split(':')
other_port = int(other_port)

# ==== Funções utilitárias
def get_wifi_signal_strength():
    try:
        raw = subprocess.check_output("netsh wlan show interfaces", shell=True)
        output = raw.decode('cp1252', errors='ignore')
        match = re.search(r"(?:Signal|Sinal)\s*[:=]\s*(\d+)%", output)
        return int(match.group(1)) if match else None
    except Exception:
        return None

def is_in_range():
    signal = get_wifi_signal_strength()
    return signal and signal >= threshold

def speak(msg: str):
    engine = pyttsx3.init()
    engine.setProperty('voice', engine.getProperty('voices')[0].id)
    engine.say(msg)
    engine.runAndWait()

def send_udp(msg: str):
    if is_in_range():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(msg.encode('utf-8'), (other_host, other_port))
        add_message(f"[ENVIADO] {msg}", "right")
    else:
        add_message("[SINAL FRACO] Mensagem bloqueada.", "center")

def recognize_and_send():
    r = sr.Recognizer()
    fs = 16000
    duration = 3
    add_message("[Áudio] Gravando por 3 segundos...", "center")
    rec = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    audio_data = sr.AudioData(rec.tobytes(), fs, 2)
    try:
        text = r.recognize_google(audio_data, language='pt-BR')
        send_udp(f"{text}")
    except sr.UnknownValueError:
        add_message("Áudio não reconhecido.", "center")

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((my_host, my_port))
    while True:
        data, addr = sock.recvfrom(1024)
        msg = data.decode('utf-8')
        add_message(f"[RECEBIDO] {msg}", "left")
        threading.Thread(target=speak, args=(msg,), daemon=True).start()

# ==== Interface gráfica (Tkinter)
root = tk.Tk()
root.title(f"Drivetalk • {peer_id}")
root.geometry("540x700")
root.configure(bg="#1e1e1e")

# Log
frame_msgs = tk.Frame(root, bg="#1e1e1e")
frame_msgs.pack(pady=10)
text_area = tk.Text(frame_msgs, height=20, width=65, bg="#121212", fg="white", font=("Segoe UI", 10))
text_area.pack()
text_area.config(state=tk.DISABLED)

def add_message(msg, align):
    text_area.config(state=tk.NORMAL)
    if align == "left":
        text_area.insert(tk.END, f"← {msg}\n")
    elif align == "right":
        text_area.insert(tk.END, f"{msg} →\n")
    else:
        text_area.insert(tk.END, f"{msg}\n")
    text_area.see(tk.END)
    text_area.config(state=tk.DISABLED)

# Entrada de texto
frame_input = tk.Frame(root, bg="#1e1e1e")
frame_input.pack(pady=5)
entry = tk.Entry(frame_input, font=("Segoe UI", 11), width=40)
entry.grid(row=0, column=0, padx=5)
def send_text():
    msg = entry.get().strip()
    if msg:
        send_udp(msg)
        entry.delete(0, tk.END)
btn_text = tk.Button(frame_input, text="Enviar Texto", command=send_text, bg="#007acc", fg="white", font=("Segoe UI", 10), width=12)
btn_text.grid(row=0, column=1)

# Botão voz
frame_voice = tk.Frame(root, bg="#1e1e1e")
frame_voice.pack(pady=5)
btn_voice = tk.Button(frame_voice, text="🎤 Enviar Voz", bg="#28a745", fg="white", font=("Segoe UI", 12), width=20, command=lambda: threading.Thread(target=recognize_and_send).start())
btn_voice.pack()

# Grade de presets
frame_presets = tk.Frame(root, bg="#1e1e1e")
frame_presets.pack(pady=10)

preset_list = list(PRESETS.values())
for idx, text in enumerate(preset_list):
    row = idx // 2
    col = idx % 2
    btn = tk.Button(frame_presets, text=text, width=28, height=2, bg="#3c3f41", fg="white",
                    font=("Segoe UI", 10), command=lambda t=text: send_udp(t))
    btn.grid(row=row, column=col, padx=5, pady=5)

# ==== Execução
threading.Thread(target=udp_listener, daemon=True).start()
add_message("Interface iniciada com sucesso.", "center")
root.mainloop()
