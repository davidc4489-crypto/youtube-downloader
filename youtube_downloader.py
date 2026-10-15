# -*- coding: utf-8 -*-
"""
Youtube Downloader - petite application de bureau pour telecharger une video
YouTube au format MP3 (audio) ou MP4 (video).

Dependances : yt-dlp, ffmpeg (embarque dans l'exe Windows).
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import queue
from pathlib import Path

import yt_dlp

APP_NAME = "Youtube Downloader"
APP_VERSION = "1.0.0"

MP4_QUALITIES = {
    "Meilleure qualite": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

MP3_BITRATES = ["320", "192", "128"]


# --------------------------------------------------------------------------- #
#  Coeur du telechargement (independant de l'interface graphique)
# --------------------------------------------------------------------------- #

def resource_dir() -> Path:
    """Dossier des ressources embarquees (PyInstaller) ou dossier du script."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def find_ffmpeg() -> str | None:
    """Retourne le chemin de ffmpeg : embarque en priorite, sinon celui du systeme."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [
        resource_dir() / exe_name,
        Path(sys.executable).parent / exe_name,
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("ffmpeg")


def default_download_dir() -> Path:
    home = Path.home()
    for name in ("Downloads", "Téléchargements"):
        p = home / name
        if p.is_dir():
            return p
    return home


YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE
)


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url.strip()))


def build_ydl_opts(fmt: str, dest: Path, quality=None, bitrate="192",
                   progress_hook=None, postprocessor_hook=None, logger=None) -> dict:
    """Construit les options yt-dlp pour 'mp3' ou 'mp4'."""
    opts = {
        "outtmpl": str(dest / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "windowsfilenames": True,
        "restrictfilenames": False,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "overwrites": True,
        "retries": 5,
        "fragment_retries": 5,
    }
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if postprocessor_hook:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if logger:
        opts["logger"] = logger

    if fmt == "mp3":
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate),
                },
                {"key": "FFmpegMetadata"},
            ],
        })
    elif fmt == "mp4":
        h = f"[height<={quality}]" if quality else ""
        opts.update({
            # H.264 (avc1) en priorite : lisible partout sous Windows sans codec AV1
            "format": (
                f"bestvideo{h}[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"
                f"/bestvideo{h}[ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo{h}+bestaudio"
                f"/best{h}[ext=mp4]/best{h}/best"
            ),
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegMetadata"}],
        })
    else:
        raise ValueError(f"Format inconnu : {fmt}")
    return opts


def download(url: str, fmt: str, dest: Path, quality=None, bitrate="192",
             progress_hook=None, postprocessor_hook=None, logger=None) -> Path:
    """Telecharge une video et retourne le chemin du fichier final."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    opts = build_ydl_opts(fmt, dest, quality, bitrate,
                          progress_hook, postprocessor_hook, logger)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:  # playlist malgre noplaylist (ex: mix)
            info = next(e for e in info["entries"] if e)
        # Chemin final apres post-traitement
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return Path(requested[0]["filepath"])
        filename = ydl.prepare_filename(info)
        return Path(filename).with_suffix("." + fmt)


# --------------------------------------------------------------------------- #
#  Interface graphique
# --------------------------------------------------------------------------- #

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    class QueueLogger:
        """Logger yt-dlp qui transmet les erreurs a l'interface."""
        def __init__(self, q):
            self.q = q

        def debug(self, msg):
            pass

        def info(self, msg):
            pass

        def warning(self, msg):
            pass

        def error(self, msg):
            self.q.put(("log", str(msg)))

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title(f"{APP_NAME} v{APP_VERSION}")
            self.resizable(False, False)
            self.q = queue.Queue()
            self.worker = None
            self.last_file = None
            self._build_ui()
            self._center()
            self.after(100, self._poll_queue)
            if not find_ffmpeg():
                messagebox.showwarning(
                    "ffmpeg introuvable",
                    "ffmpeg n'a pas ete trouve. La conversion MP3 et la fusion "
                    "MP4 risquent d'echouer.",
                )

        # ---- construction ---------------------------------------------- #
        def _build_ui(self):
            pad = {"padx": 10, "pady": 6}
            frm = ttk.Frame(self, padding=14)
            frm.grid(sticky="nsew")

            ttk.Label(frm, text="Lien de la video YouTube :").grid(
                row=0, column=0, columnspan=3, sticky="w")
            self.url_var = tk.StringVar()
            self.url_entry = ttk.Entry(frm, textvariable=self.url_var, width=60)
            self.url_entry.grid(row=1, column=0, columnspan=2, sticky="we", **pad)
            ttk.Button(frm, text="Coller", command=self._paste, width=10).grid(
                row=1, column=2, sticky="we", **pad)

            # Format
            fmt_frame = ttk.LabelFrame(frm, text="Format", padding=8)
            fmt_frame.grid(row=2, column=0, columnspan=3, sticky="we", **pad)
            self.fmt_var = tk.StringVar(value="mp3")
            ttk.Radiobutton(fmt_frame, text="MP3 (audio)", value="mp3",
                            variable=self.fmt_var, command=self._on_fmt_change
                            ).grid(row=0, column=0, sticky="w", padx=(0, 20))
            ttk.Radiobutton(fmt_frame, text="MP4 (video)", value="mp4",
                            variable=self.fmt_var, command=self._on_fmt_change
                            ).grid(row=0, column=1, sticky="w")

            self.quality_label = ttk.Label(fmt_frame, text="Qualite audio :")
            self.quality_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
            self.quality_var = tk.StringVar()
            self.quality_box = ttk.Combobox(fmt_frame, textvariable=self.quality_var,
                                            state="readonly", width=20)
            self.quality_box.grid(row=1, column=1, sticky="w", pady=(8, 0))
            self._on_fmt_change()

            # Dossier
            ttk.Label(frm, text="Enregistrer dans :").grid(
                row=3, column=0, columnspan=3, sticky="w", padx=10)
            self.dest_var = tk.StringVar(value=str(default_download_dir()))
            ttk.Entry(frm, textvariable=self.dest_var, width=60).grid(
                row=4, column=0, columnspan=2, sticky="we", **pad)
            ttk.Button(frm, text="Parcourir...", command=self._browse, width=10).grid(
                row=4, column=2, sticky="we", **pad)

            # Bouton + progression
            self.dl_btn = ttk.Button(frm, text="Telecharger", command=self._start)
            self.dl_btn.grid(row=5, column=0, columnspan=3, sticky="we", padx=10, pady=(12, 6))

            self.progress = ttk.Progressbar(frm, mode="determinate", maximum=100)
            self.progress.grid(row=6, column=0, columnspan=3, sticky="we", padx=10, pady=4)

            self.status_var = tk.StringVar(value="Pret.")
            ttk.Label(frm, textvariable=self.status_var, wraplength=480).grid(
                row=7, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 6))

            self.open_btn = ttk.Button(frm, text="Ouvrir le dossier",
                                       command=self._open_folder, state="disabled")
            self.open_btn.grid(row=8, column=0, columnspan=3, sticky="we", padx=10)

            frm.columnconfigure(0, weight=1)
            self.url_entry.focus_set()
            self.bind("<Return>", lambda e: self._start())

        def _center(self):
            self.update_idletasks()
            w, h = self.winfo_width(), self.winfo_height()
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 2
            self.geometry(f"+{x}+{y}")

        # ---- actions ---------------------------------------------------- #
        def _on_fmt_change(self):
            if self.fmt_var.get() == "mp3":
                self.quality_label.config(text="Qualite audio :")
                self.quality_box["values"] = [f"{b} kbps" for b in MP3_BITRATES]
                self.quality_box.current(1)
            else:
                self.quality_label.config(text="Resolution :")
                self.quality_box["values"] = list(MP4_QUALITIES.keys())
                self.quality_box.current(0)

        def _paste(self):
            try:
                self.url_var.set(self.clipboard_get().strip())
            except tk.TclError:
                pass

        def _browse(self):
            d = filedialog.askdirectory(initialdir=self.dest_var.get() or str(Path.home()))
            if d:
                self.dest_var.set(d)

        def _open_folder(self):
            folder = Path(self.dest_var.get())
            if self.last_file and Path(self.last_file).exists():
                target = Path(self.last_file)
                if os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", str(target)])
                    return
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])

        def _start(self):
            if self.worker and self.worker.is_alive():
                return
            url = self.url_var.get().strip()
            if not url:
                messagebox.showwarning(APP_NAME, "Veuillez saisir un lien YouTube.")
                return
            if not is_youtube_url(url):
                if not messagebox.askyesno(
                        APP_NAME,
                        "Ce lien ne ressemble pas a un lien YouTube.\nContinuer quand meme ?"):
                    return
            dest = Path(self.dest_var.get().strip() or default_download_dir())
            fmt = self.fmt_var.get()
            if fmt == "mp3":
                quality, bitrate = None, self.quality_var.get().split()[0]
            else:
                quality, bitrate = MP4_QUALITIES[self.quality_var.get()], "192"

            self.dl_btn.config(state="disabled")
            self.open_btn.config(state="disabled")
            self.progress.config(mode="determinate", value=0)
            self.status_var.set("Recuperation des informations...")
            self.last_file = None

            self.worker = threading.Thread(
                target=self._run_download,
                args=(url, fmt, dest, quality, bitrate), daemon=True)
            self.worker.start()

        def _run_download(self, url, fmt, dest, quality, bitrate):
            def hook(d):
                st = d.get("status")
                if st == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    done = d.get("downloaded_bytes") or 0
                    pct = (done / total * 100) if total else None
                    speed = d.get("speed")
                    eta = d.get("eta")
                    parts = ["Telechargement"]
                    if pct is not None:
                        parts.append(f"{pct:.1f} %")
                    if speed:
                        parts.append(f"{speed / 1024 / 1024:.2f} Mo/s")
                    if eta is not None:
                        parts.append(f"reste {int(eta)} s")
                    self.q.put(("progress", pct, " - ".join(parts)))
                elif st == "finished":
                    self.q.put(("progress", 100, "Conversion / fusion en cours..."))

            def pp_hook(d):
                if d.get("status") == "started":
                    name = d.get("postprocessor", "")
                    if "ExtractAudio" in name:
                        self.q.put(("busy", "Conversion en MP3..."))
                    elif "Merger" in name:
                        self.q.put(("busy", "Fusion audio + video..."))

            try:
                path = download(url, fmt, dest, quality, bitrate,
                                hook, pp_hook, QueueLogger(self.q))
                self.q.put(("done", str(path)))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", _friendly_error(e)))

        def _poll_queue(self):
            try:
                while True:
                    msg = self.q.get_nowait()
                    kind = msg[0]
                    if kind == "progress":
                        _, pct, text = msg
                        if pct is None:
                            if self.progress["mode"] != "indeterminate":
                                self.progress.config(mode="indeterminate")
                                self.progress.start(15)
                        else:
                            if self.progress["mode"] != "determinate":
                                self.progress.stop()
                                self.progress.config(mode="determinate")
                            self.progress["value"] = pct
                        self.status_var.set(text)
                    elif kind == "busy":
                        self.progress.config(mode="indeterminate")
                        self.progress.start(15)
                        self.status_var.set(msg[1])
                    elif kind == "log":
                        self.status_var.set(msg[1][:200])
                    elif kind == "done":
                        self._finish()
                        self.last_file = msg[1]
                        self.status_var.set(f"Termine : {Path(msg[1]).name}")
                        self.open_btn.config(state="normal")
                    elif kind == "error":
                        self._finish(error=True)
                        self.status_var.set("Erreur : " + msg[1])
                        messagebox.showerror(APP_NAME, msg[1])
            except queue.Empty:
                pass
            self.after(100, self._poll_queue)

        def _finish(self, error=False):
            self.progress.stop()
            self.progress.config(mode="determinate", value=0 if error else 100)
            self.dl_btn.config(state="normal")

    def _friendly_error(e: Exception) -> str:
        text = str(e)
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)  # codes couleur
        text = text.replace("ERROR: ", "")
        low = text.lower()
        if "ffmpeg" in low and ("not found" in low or "not installed" in low):
            return "ffmpeg est introuvable : impossible de convertir le fichier."
        if "video unavailable" in low:
            return "Cette video n'est pas disponible."
        if "private video" in low:
            return "Cette video est privee."
        if "sign in" in low or "age" in low and "confirm" in low:
            return "Cette video necessite une connexion (restriction d'age)."
        if "unsupported url" in low or "is not a valid url" in low:
            return "Lien invalide ou non pris en charge."
        if "urlopen" in low or "getaddrinfo" in low or "network" in low:
            return "Probleme de connexion internet."
        return text[:300]

    App().mainloop()


if __name__ == "__main__":
    run_gui()
