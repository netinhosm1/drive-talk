import sys
import socket
import threading
import time
import subprocess
import re
import tkinter as tk
from tkinter import simpledialog, messagebox

import customtkinter as ctk
import sounddevice as sd
import speech_recognition as sr
import pyttsx3

# ==== Prompt obrigatório para nome do usuário ====
_root = tk.Tk()
_root.withdraw()
peer_id = None
while not peer_id:
    peer_id = simpledialog.askstring(
        "Drivetalk — Identificação",
        "Digite seu nome de usuário (ex: Neto, Carlos):",
        parent=_root
    )
    if peer_id is None:
        if messagebox.askyesno("Confirmação", "Deseja sair?"):
            sys.exit(0)
        else:
            peer_id = ""
_root.destroy()

# ==== Setup CustomTkinter ====
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ==== Network / Discovery settings ====
DISC_PORT = 6000
TALK_PORT = 5005
discovered = {}

# ==== Presets ====
PRESETS = [
    "Animais na pista", "Buraco na pista",
    "Trânsito lento à frente", "Veículo parado à frente",
    "Assaltante na pista", "Pode realizar a ultrapassagem",
    "Preciso ultrapassar", "Obrigado"
]

# ==== Custom Microphone ====
class SoundDeviceMicrophone(sr.AudioSource):
    def __init__(self, device=None, samplerate=16000, channels=1):
        self.device, self.samplerate, self.channels = device, samplerate, channels
        self.SAMPLE_RATE, self.SAMPLE_WIDTH, self.CHUNK = samplerate, 2, 1024
    def __enter__(self):
        self.stream = sd.InputStream(
            samplerate=self.samplerate, device=self.device,
            channels=self.channels, blocksize=self.CHUNK, dtype='int16'
        )
        self.stream.start()
        orig = self.stream.read
        self.stream.read = lambda f, **kw: orig(f, **kw)[0].tobytes()
        return self
    def __exit__(self, exc_t, exc_v, exc_tb):
        self.stream.stop(); self.stream.close()

sr.Microphone = SoundDeviceMicrophone

# ==== Speech Recognizer Pre-calibration ====
recognizer = sr.Recognizer()
with sr.Microphone() as src:
    recognizer.adjust_for_ambient_noise(src, duration=1)

# ==== Helpers ====
def speak(text):
    eng = pyttsx3.init()
    eng.setProperty('voice', eng.getProperty('voices')[0].id)
    eng.say(text); eng.runAndWait()

def get_wifi_signal():
    try:
        out = subprocess.check_output("netsh wlan show interfaces", shell=True)\
                       .decode('cp1252','ignore')
        m = re.search(r"(?:Signal|Sinal)\s*[:=]\s*(\d+)%", out)
        return int(m.group(1)) if m else 0
    except:
        return 0

def can_send():
    return get_wifi_signal() >= 10

# ==== Discovery Thread ====
def discovery_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', DISC_PORT))
    while True:
        msg = f"HELLO|{peer_id}|{TALK_PORT}"
        sock.sendto(msg.encode(), ('255.255.255.255', DISC_PORT))
        sock.settimeout(2)
        start = time.time()
        while time.time() - start < 2:
            try: data, addr = sock.recvfrom(256)
            except socket.timeout: break
            tag, pid, prt = data.decode().split('|'); prt=int(prt)
            if pid != peer_id and tag in ("HELLO","HELLO_RESPONSE"):
                discovered[pid] = (addr[0], prt)
                resp = f"HELLO_RESPONSE|{peer_id}|{TALK_PORT}"
                sock.sendto(resp.encode(), (addr[0], DISC_PORT))
        time.sleep(10)

# ==== UDP Listener & Sender ====
def udp_listener(log_fn):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', TALK_PORT))
    while True:
        data, _ = sock.recvfrom(1024)
        msg = data.decode()
        log_fn(f"← {msg}", "received")
        threading.Thread(target=speak, args=(msg,), daemon=True).start()

def send_to_peers(msg, log_fn):
    if not can_send():
        log_fn("❌ Sinal fraco — bloqueado", "center"); return
    for ip, port in discovered.values():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(f"{msg}".encode(), (ip, port))
    log_fn(f"{msg} →", "sent")

# ==== Voice Record & Send ====
def record_and_send(log_fn):
    log_fn("⏺ Gravando 3s...", "center")
    rec = sd.rec(int(3*16000), samplerate=16000, channels=1, dtype='int16')
    sd.wait()
    audio = sr.AudioData(rec.tobytes(), 16000, 2)
    try:
        txt = recognizer.recognize_google(audio, language='pt-BR')
        send_to_peers(txt, log_fn)
    except sr.UnknownValueError:
        log_fn("⚠️ Áudio não reconhecido", "center")

# ==== Wake-word Thread ====
def wake_thread(log_fn):
    mic = sr.Microphone()
    while True:
        with mic as src:
            audio = recognizer.listen(src, phrase_time_limit=2)
        try:
            w = recognizer.recognize_google(audio, language='pt-BR').lower()
            if "drive" in w:
                log_fn("🔑 WakeWord detectada", "center")
                speak("Oi, pode falar")
                record_and_send(log_fn)
        except: pass

# ==== Main GUI ====
class DriveTalkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Drivetalk • {peer_id}")
        self.geometry("600x820")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # log row fixed
        # Log Box
        self.log_box = ctk.CTkTextbox(self, corner_radius=8, height=220)
        self.log_box.grid(row=0, column=0, padx=20, pady=(20,10), sticky="ew")
        self.log_box.configure(state="disabled")
        # Status Bar
        self.status = ctk.CTkProgressBar(self, width=560)
        self.status.grid(row=1, column=0, padx=20, pady=(0,10))
        # Entry & Buttons
        frm = ctk.CTkFrame(self); frm.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        frm.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(frm, placeholder_text="Digite mensagem...")
        self.entry.grid(row=0, column=0, padx=(0,5), sticky="ew")
        ctk.CTkButton(frm, text="Enviar Texto", command=self.on_send_text).grid(row=0, column=1)
        ctk.CTkButton(frm, text="🎤 Voz", fg_color="#28a745", command=self.on_send_voice)\
            .grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")
        # Presets Grid
        grid = ctk.CTkFrame(self); grid.grid(row=3, column=0, padx=20, pady=(0,20), sticky="ew")
        for i, txt in enumerate(PRESETS):
            btn = ctk.CTkButton(grid, text=txt, command=lambda t=txt: send_to_peers(t, self.log))
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky="ew")
            grid.grid_columnconfigure(i%2, weight=1)
        # Peer List Scrollable
        self.peer_frame = ctk.CTkScrollableFrame(self, height=100)
        self.peer_frame.grid(row=4, column=0, padx=20, pady=(0,20), sticky="ew")
        # Start Threads
        threading.Thread(target=discovery_loop, daemon=True).start()
        threading.Thread(target=udp_listener, args=(self.log,), daemon=True).start()
        threading.Thread(target=wake_thread, args=(self.log,), daemon=True).start()
        threading.Thread(target=self.update_status, daemon=True).start()
        threading.Thread(target=self.refresh_peers, daemon=True).start()
        self.log("🚀 Interface iniciada", "center")

    def log(self, message, typ):
        self.log_box.configure(state="normal")
        if typ=="received":
            self.log_box.insert("end", f"    {message}\n")
        elif typ=="sent":
            self.log_box.insert("end", f"{message.rjust(60)}\n")
        else:
            self.log_box.insert("end", f"{message.center(60)}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def on_send_text(self):
        t = self.entry.get().strip()
        if t:
            send_to_peers(t, self.log)
            self.entry.delete(0, "end")

    def on_send_voice(self):
        threading.Thread(target=record_and_send, args=(self.log,), daemon=True).start()

    def update_status(self):
        while True:
            val = get_wifi_signal()/100
            self.status.set(val)
            time.sleep(2)

    def refresh_peers(self):
        while True:
            for w in self.peer_frame.winfo_children():
                w.destroy()
            if not discovered:
                lbl = ctk.CTkLabel(self.peer_frame, text="Nenhum peer conectado")
                lbl.pack(pady=5)
            else:
                for pid, (ip, _) in discovered.items():
                    lbl = ctk.CTkLabel(self.peer_frame, text=f"{pid} → {ip}")
                    lbl.pack(fill="x", pady=2)
            time.sleep(3)

if __name__ == "__main__":
    app = DriveTalkApp()
    app.mainloop()
