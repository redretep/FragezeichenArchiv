import os
import re
import sys
import json
import time
import queue
import threading
import urllib.parse
import http.client
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Constants
DEFAULT_MUSIC_DIR = r"C:\Users\pidi\Music\Hörspiele und Hörbücher\DDF"
METADATA_FILE = "fileditch_tracks.json"
FILEDITCH_HOST = "new.fileditch.com"
UPLOAD_URL_PATH = "/upload.php?filename="

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

def get_natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def get_audio_files(folder_path):
    audio_files = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
        for f in files:
            if f.startswith('._'):
                continue
            if f.lower().endswith(('.mp3', '.flac', '.m4a')):
                audio_files.append(os.path.join(root, f))
    return audio_files

def extract_episode_number(folder_name):
    match = re.search(r'(?:folge|nr|no)?\.?\s*(\d{1,3})(?:\D|$)', folder_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def load_metadata_maps():
    folder_to_metadata = {}
    try:
        with open("dr3imetadata.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for ep in data["serie"]:
                folder_to_metadata[ep["folder"]] = {
                    "id": ep["id"],
                    "num": ep["nummer"],
                    "category": "dr3i",
                    "title": ep["titel"]
                }
    except:
        pass
    try:
        with open("specialsmetadata.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for ep in data["serie"]:
                folder_to_metadata[ep["folder"]] = {
                    "id": ep["id"],
                    "num": ep["nummer"],
                    "category": "special",
                    "title": ep["titel"]
                }
    except:
        pass
    return folder_to_metadata

class UploadWorker(threading.Thread):
    def __init__(self, music_dir, folders, tracks_db, gui):
        super().__init__()
        self.music_dir = music_dir
        self.folders = folders
        self.tracks_db = tracks_db
        self.gui = gui
        self._stop_event = threading.Event()
        self.daemon = True

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        total_files = 0
        uploaded_files = 0
        
        # Count total files to upload
        to_upload_list = []
        for candidate in self.folders:
            if self.stopped():
                break
                
            c_id = candidate["id"]
            folder_path = candidate["path"]
            folder_name = candidate["folder_name"]
            
            audio_files = get_audio_files(folder_path)
            
            if not audio_files:
                continue
                
            audio_files.sort(key=get_natural_sort_key)
            ep_key = c_id
            existing_tracks = self.tracks_db.get(ep_key, [])
            
            # Check what needs uploading
            ep_tracks_to_upload = []
            for idx, filepath in enumerate(audio_files):
                filename = os.path.basename(filepath)
                filesize = os.path.getsize(filepath)
                
                # Check if already in DB
                already_uploaded = False
                if idx < len(existing_tracks):
                    ex_track = existing_tracks[idx]
                    if ex_track.get("filename") == filename and ex_track.get("size") == filesize:
                        already_uploaded = True
                        
                if not already_uploaded:
                    ep_tracks_to_upload.append((idx, filepath, filename, filesize))
            
            if ep_tracks_to_upload:
                to_upload_list.append((ep_key, folder_path, folder_name, audio_files, ep_tracks_to_upload))
                total_files += len(ep_tracks_to_upload)

        if total_files == 0:
            self.gui.log("No new tracks found to upload. Everything is up to date!")
            self.gui.on_upload_complete(0)
            return

        self.gui.set_overall_max(total_files)
        self.gui.log(f"Starting upload for {len(to_upload_list)} episodes/specials ({total_files} new tracks)...")
        
        for ep_key, folder_path, folder_name, all_mp3s, ep_uploads in to_upload_list:
            if self.stopped():
                break
                
            self.gui.log(f"\nProcessing Episode {ep_key}: {folder_name}")
            
            # Retrieve or initialize tracks array
            ep_tracks = list(self.tracks_db.get(ep_key, []))
            
            # Pad or truncate to match total tracks length if needed
            if len(ep_tracks) < len(all_mp3s):
                ep_tracks += [None] * (len(all_mp3s) - len(ep_tracks))
            elif len(ep_tracks) > len(all_mp3s):
                ep_tracks = ep_tracks[:len(all_mp3s)]
                
            for idx, filepath, filename, filesize in ep_uploads:
                if self.stopped():
                    break
                    
                self.gui.log(f"  Uploading track {idx+1}/{len(all_mp3s)}: {filename}")
                self.gui.set_active_file(filename, filesize)
                
                # Set status to Uploading
                self.gui.update_track_status(ep_key, idx, "Uploading", 0)
                
                success = False
                res_data = None
                retry_count = 3
                
                for attempt in range(1, retry_count + 1):
                    if self.stopped():
                        break
                    try:
                        res_data = self.upload_file_raw_with_progress(filepath, ep_key, idx)
                        success = True
                        break
                    except Exception as e:
                        self.gui.log(f"    [Attempt {attempt}/{retry_count}] Upload failed: {e}")
                        if attempt < retry_count:
                            time.sleep(2)
                            
                if self.stopped():
                    break
                    
                if not success:
                    self.gui.log(f"FATAL ERROR: Failed to upload track {filename}. Stopping.")
                    self.gui.update_track_status(ep_key, idx, "Failed", 0)
                    self.gui.on_upload_error(filename)
                    return
                    
                direct_url = res_data.get("url")
                track_meta = {
                    "filename": filename,
                    "url": direct_url,
                    "size": filesize
                }
                
                ep_tracks[idx] = track_meta
                
                # Save intermediate database state (filter out None values)
                clean_tracks = [t for t in ep_tracks if t is not None]
                self.tracks_db[ep_key] = clean_tracks
                
                with open(METADATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.tracks_db, f, indent=2, ensure_ascii=False)
                    
                uploaded_files += 1
                self.gui.update_overall_progress(uploaded_files)
                self.gui.update_track_status(ep_key, idx, "Completed", 100)
                self.gui.log(f"    Uploaded successfully! URL: {direct_url}")
                
        # Clean up database on completion (saving finalized arrays)
        if not self.stopped():
            for k in list(self.tracks_db.keys()):
                self.tracks_db[k] = [t for t in self.tracks_db[k] if t is not None]
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tracks_db, f, indent=2, ensure_ascii=False)
                
            self.gui.log("\nUpload task complete!")
            self.gui.on_upload_complete(uploaded_files)
        else:
            self.gui.log("\nUpload task stopped by user.")
            self.gui.on_upload_stopped()

    def upload_file_raw_with_progress(self, filepath, ep_key, track_idx):
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        url_path = UPLOAD_URL_PATH + urllib.parse.quote(filename)
        
        conn = http.client.HTTPSConnection(FILEDITCH_HOST, timeout=60)
        conn.putrequest("POST", url_path)
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Content-Length", str(filesize))
        conn.endheaders()
        
        chunk_size = 256 * 1024 # Smaller chunk size for granular UI progress response
        uploaded = 0
        
        with open(filepath, "rb") as f:
            while True:
                if self.stopped():
                    conn.close()
                    raise Exception("Process terminated by user")
                    
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                conn.send(chunk)
                uploaded += len(chunk)
                
                percent = (uploaded / filesize) * 100
                self.gui.update_active_progress(uploaded, percent)
                self.gui.update_track_status(ep_key, track_idx, f"Uploading ({int(percent)}%)", percent)
                
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")
        conn.close()
        
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}: {response_data}")
            
        try:
            res_json = json.loads(response_data)
            if not res_json.get("success"):
                raise Exception(res_json.get("error", "Unknown server error"))
            return res_json
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {response_data}")


class FileDitchUploaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("??? Uploader — FileDitch GUI")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)
        
        self.music_dir = DEFAULT_MUSIC_DIR
        self.folders = []
        self.tracks_db = {}
        self.worker = None
        
        # Tree lists mapping
        self.episode_id_map = {} # Maps item_id -> ep_num
        self.track_id_map = {} # Maps ep_num -> list of item_ids
        
        self.setup_styles()
        self.build_ui()
        self.load_database()
        
        # Set default dir if exists
        if os.path.exists(self.music_dir):
            self.dir_entry.insert(0, self.music_dir)
            self.scan_directory()
        else:
            self.log(f"Warning: Default music folder not found. Please browse to: {self.music_dir}")

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Color codes
        self.bg_color = "#0e0d15"
        self.card_color = "#161424"
        self.accent_green = "#00ff9d"
        self.accent_red = "#ff2e54"
        self.text_color = "#ffffff"
        self.muted_color = "#8a8996"
        self.border_color = "#252535"
        
        # Configure window background
        self.root.configure(bg=self.bg_color)
        
        # Custom Widget Configurations
        self.style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 10))
        
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("Card.TFrame", background=self.card_color, borderwidth=1, relief="solid")
        
        self.style.configure("TLabel", background=self.bg_color, foreground=self.text_color)
        self.style.configure("Card.TLabel", background=self.card_color, foreground=self.text_color)
        self.style.configure("Header.TLabel", background=self.bg_color, foreground=self.accent_green, font=("Segoe UI", 12, "bold"))
        self.style.configure("Muted.TLabel", background=self.bg_color, foreground=self.muted_color, font=("Segoe UI", 9))
        self.style.configure("CardMuted.TLabel", background=self.card_color, foreground=self.muted_color, font=("Segoe UI", 9))
        
        # Entry
        self.style.configure("TEntry", fieldbackground="#000000", foreground="#ffffff", bordercolor=self.border_color, lightcolor=self.border_color, darkcolor=self.border_color)
        
        # Buttons
        self.style.configure("TButton", background="#252535", foreground="#ffffff", borderwidth=0, padding=6)
        self.style.map("TButton", background=[("active", "#353548"), ("disabled", "#151520")], foreground=[("disabled", "#505060")])
        
        self.style.configure("Action.TButton", background=self.accent_green, foreground="#000000", font=("Segoe UI", 10, "bold"))
        self.style.map("Action.TButton", background=[("active", "#00e08a"), ("disabled", "#153025")], foreground=[("disabled", "#406050")])
        
        self.style.configure("Stop.TButton", background=self.accent_red, foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        self.style.map("Stop.TButton", background=[("active", "#e02046")])

        # Progressbar
        self.style.configure("Horizontal.TProgressbar", background=self.accent_green, troughcolor="#252535", borderwidth=0)
        
        # Treeview Styles
        self.style.configure("Treeview", background=self.card_color, foreground=self.text_color, fieldbackground=self.card_color, borderwidth=0, rowheight=26)
        self.style.configure("Treeview.Heading", background="#252535", foreground=self.text_color, borderwidth=0, font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview", background=[("selected", "#353550")], foreground=[("selected", "#ffffff")])

    def build_ui(self):
        # Master Grid Configuration
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # 1. Header & Path Panel
        top_frame = ttk.Frame(self.root, padding=12)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.columnconfigure(1, weight=1)
        
        brand_lbl = ttk.Label(top_frame, text="??? Uploader", font=("Segoe UI", 14, "bold"), foreground=self.accent_green)
        brand_lbl.grid(row=0, column=0, padx=(0, 16), sticky="w")
        
        self.dir_entry = ttk.Entry(top_frame, font=("Segoe UI", 10))
        self.dir_entry.grid(row=0, column=1, sticky="ew", padx=5)
        
        browse_btn = ttk.Button(top_frame, text="Durchsuchen", command=self.browse_directory)
        browse_btn.grid(row=0, column=2, padx=5)
        
        scan_btn = ttk.Button(top_frame, text="Scan Ordner", command=self.scan_directory)
        scan_btn.grid(row=0, column=3, padx=(5, 0))

        # 2. Main Content Split View
        content_paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        content_paned.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        
        # Left Panel (Episodes List)
        left_frame = ttk.Frame(content_paned, padding=(0, 0, 6, 0))
        content_paned.add(left_frame, weight=2)
        
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        
        ttk.Label(left_frame, text="Hörspiele / Ordner", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        
        self.ep_tree = ttk.Treeview(left_frame, columns=("num", "folder", "status"), show="headings")
        self.ep_tree.heading("num", text="Folge")
        self.ep_tree.heading("folder", text="Ordnername")
        self.ep_tree.heading("status", text="Status")
        self.ep_tree.column("num", width=60, minwidth=50, stretch=False, anchor="center")
        self.ep_tree.column("folder", width=200, minwidth=150, stretch=True)
        self.ep_tree.column("status", width=90, minwidth=80, stretch=False, anchor="center")
        self.ep_tree.grid(row=1, column=0, sticky="nsew")
        self.ep_tree.bind("<<TreeviewSelect>>", self.on_episode_selected)
        
        ep_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.ep_tree.yview)
        self.ep_tree.configure(yscrollcommand=ep_scroll.set)
        ep_scroll.grid(row=1, column=1, sticky="ns")
        
        # Right Panel (Tracks Details)
        right_frame = ttk.Frame(content_paned, padding=(6, 0, 0, 0))
        content_paned.add(right_frame, weight=3)
        
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        ttk.Label(right_frame, text="Titel / Kapitel Details", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        
        self.track_tree = ttk.Treeview(right_frame, columns=("index", "file", "size", "status"), show="headings")
        self.track_tree.heading("index", text="#")
        self.track_tree.heading("file", text="Dateiname")
        self.track_tree.heading("size", text="Größe")
        self.track_tree.heading("status", text="Upload Status")
        self.track_tree.column("index", width=35, minwidth=30, stretch=False, anchor="center")
        self.track_tree.column("file", width=250, minwidth=180, stretch=True)
        self.track_tree.column("size", width=80, minwidth=70, stretch=False, anchor="e")
        self.track_tree.column("status", width=120, minwidth=100, stretch=False)
        self.track_tree.grid(row=1, column=0, sticky="nsew")
        
        track_scroll = ttk.Scrollbar(right_frame, orient="vertical", command=self.track_tree.yview)
        self.track_tree.configure(yscrollcommand=track_scroll.set)
        track_scroll.grid(row=1, column=1, sticky="ns")
        
        # 3. Bottom Panels (Progress controls & Log Console)
        bottom_frame = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        bottom_frame.grid(row=2, column=0, sticky="ew")
        bottom_frame.columnconfigure(0, weight=1)
        
        # Progress Card
        progress_card = ttk.Frame(bottom_frame, padding=12, style="Card.TFrame")
        progress_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        progress_card.columnconfigure(1, weight=1)
        
        # Current active file progress
        self.file_lbl = ttk.Label(progress_card, text="Kein Upload aktiv", style="Card.TLabel", font=("Segoe UI", 10, "bold"))
        self.file_lbl.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        
        self.file_bar = ttk.Progressbar(progress_card, orient="horizontal", mode="determinate", style="Horizontal.TProgressbar")
        self.file_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        
        self.file_progress_lbl = ttk.Label(progress_card, text="0.00 MB / 0.00 MB (0%)", style="CardMuted.TLabel")
        self.file_progress_lbl.grid(row=2, column=0, sticky="w")
        
        # Separator line
        sep = ttk.Separator(progress_card, orient="horizontal")
        sep.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        
        # Overall progress
        self.overall_lbl = ttk.Label(progress_card, text="Gesamtfortschritt (Folgen & Dateien)", style="Card.TLabel")
        self.overall_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
        
        self.overall_bar = ttk.Progressbar(progress_card, orient="horizontal", mode="determinate", style="Horizontal.TProgressbar")
        self.overall_bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        
        self.overall_progress_lbl = ttk.Label(progress_card, text="Datei 0 von 0 verarbeitet (0%)", style="CardMuted.TLabel")
        self.overall_progress_lbl.grid(row=6, column=0, sticky="w")
        
        # Action Buttons Pane inside Card
        btn_frame = ttk.Frame(progress_card, style="Card.TFrame")
        btn_frame.grid(row=4, column=1, rowspan=3, sticky="e", padx=(10, 0))
        
        self.start_btn = ttk.Button(btn_frame, text="Upload Starten", style="Action.TButton", command=self.start_upload)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Abbrechen", style="Stop.TButton", command=self.stop_upload)
        self.stop_btn.grid(row=0, column=1, padx=5)
        self.stop_btn.state(["disabled"])
        
        # Scrolling Logs Console at the bottom
        log_frame = ttk.Frame(bottom_frame)
        log_frame.grid(row=1, column=0, sticky="ew")
        log_frame.columnconfigure(0, weight=1)
        
        ttk.Label(log_frame, text="Protokoll & Meldungen", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        
        self.log_text = ScrolledText(log_frame, height=6, bg="#000000", fg=self.accent_green, font=("Consolas", 9), insertbackground="white", bd=0, highlightthickness=1, highlightbackground=self.border_color)
        self.log_text.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(state="disabled")

    def browse_directory(self):
        selected = filedialog.askdirectory(initialdir=self.music_dir, title="DDF Musikverzeichnis auswählen")
        if selected:
            self.music_dir = selected
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, selected)
            self.scan_directory()

    def load_database(self):
        self.tracks_db = {}
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    self.tracks_db = json.load(f)
                self.log(f"Metadaten-Datenbank geladen: {len(self.tracks_db)} Episoden eingetragen.")
            except Exception as e:
                self.log(f"Fehler beim Laden von {METADATA_FILE}: {e}")

    def scan_directory(self):
        target = self.dir_entry.get().strip()
        if not os.path.exists(target):
            messagebox.showerror("Fehler", f"Verzeichnis existiert nicht:\n{target}")
            return
            
        self.music_dir = target
        self.folders = []
        
        # Clear Left List Tree
        self.ep_tree.delete(*self.ep_tree.get_children())
        self.episode_id_map.clear()
        self.track_id_map.clear()
        
        # Load metadata maps
        folder_to_metadata = load_metadata_maps()
        
        # Check if music_dir contains subdirectories Die drei ___ and/or DiE-DR3i
        subdirs_to_scan = []
        has_sub = False
        if os.path.exists(self.music_dir):
            try:
                for name in os.listdir(self.music_dir):
                    path = os.path.join(self.music_dir, name)
                    if os.path.isdir(path) and name in ('Die drei ___', 'DiE-DR3i'):
                        subdirs_to_scan.append((path, name))
                        has_sub = True
            except:
                pass
                
        if not has_sub:
            subdirs_to_scan.append((self.music_dir, ""))
            
        for scan_path, scan_type in subdirs_to_scan:
            try:
                for entry in os.scandir(scan_path):
                    if entry.is_dir():
                        folder_name = entry.name
                        
                        # Check metadata mapping first
                        meta = folder_to_metadata.get(folder_name)
                        if meta:
                            self.folders.append({
                                "id": meta["id"],
                                "num": meta["num"],
                                "category": meta["category"],
                                "path": entry.path,
                                "folder_name": folder_name,
                                "title": meta["title"]
                            })
                        else:
                            # Check if it's an official episode (starts with 3 digits followed by underscore or space)
                            match = re.match(r'^(\d{3})_', folder_name)
                            if match:
                                num = int(match.group(1))
                                self.folders.append({
                                    "id": str(num),
                                    "num": num,
                                    "category": "official",
                                    "path": entry.path,
                                    "folder_name": folder_name,
                                    "title": folder_name[4:].replace('_', ' ')
                                })
                            else:
                                ep_num = extract_episode_number(folder_name)
                                if ep_num is not None:
                                    self.folders.append({
                                        "id": str(ep_num),
                                        "num": ep_num,
                                        "category": "official",
                                        "path": entry.path,
                                        "folder_name": folder_name,
                                        "title": folder_name
                                    })
            except Exception as e:
                self.log(f"Error scanning {scan_path}: {e}")
                
        # Sort folders
        def sort_key(x):
            cat_order = {"official": 0, "dr3i": 1, "special": 2}
            return (cat_order.get(x["category"], 3), x["num"])
            
        self.folders.sort(key=sort_key)
        
        # Insert into Left Tree
        for candidate in self.folders:
            c_id = candidate["id"]
            path = candidate["path"]
            name = candidate["folder_name"]
            
            # Scan files inside folder to check status
            audio_count = 0
            try:
                audio_count = len(get_audio_files(path))
            except:
                pass
                
            if audio_count == 0:
                continue
                
            # Status check
            existing = self.tracks_db.get(c_id, [])
            status = "Inkomplett"
            if len(existing) == audio_count:
                status = "Komplett"
            elif len(existing) == 0:
                status = "Ausstehend"
                
            # Render ID in the Tree
            num_label = c_id
            if candidate["category"] == "official":
                try:
                    num_label = f"{int(c_id):03d}"
                except:
                    pass
            item_id = self.ep_tree.insert("", tk.END, values=(num_label, name, status))
            self.episode_id_map[item_id] = candidate
            
        self.log(f"Scan abgeschlossen. {len(self.episode_id_map)} Ordner mit Hörspielen gefunden.")
        self.clear_tracks_view()

    def clear_tracks_view(self):
        self.track_tree.delete(*self.track_tree.get_children())

    def on_episode_selected(self, event):
        selected_items = self.ep_tree.selection()
        if not selected_items:
            return
            
        self.clear_tracks_view()
        item_id = selected_items[0]
        candidate = self.episode_id_map.get(item_id)
        if not candidate:
            return
            
        folder_path = candidate["path"]
        ep_key = candidate["id"]
        
        # Scan Audio Files
        try:
            audio_files = get_audio_files(folder_path)
        except Exception as e:
            self.log(f"Error reading directory {folder_path}: {e}")
            return
            
        audio_files.sort(key=get_natural_sort_key)
        existing_tracks = self.tracks_db.get(ep_key, [])
        
        # Render Right Table List
        self.track_id_map[ep_key] = []
        for idx, filepath in enumerate(audio_files):
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            
            # Status check
            status = "Ausstehend"
            if idx < len(existing_tracks):
                ex = existing_tracks[idx]
                if ex.get("filename") == filename and ex.get("size") == filesize:
                    status = "Hochgeladen"
                    
            tr_item_id = self.track_tree.insert("", tk.END, values=(idx + 1, filename, format_size(filesize), status))
            self.track_id_map[ep_key].append((idx, tr_item_id))

    def log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    # Thread-Safe UI Update Handlers scheduled on the main thread via root.after
    def update_track_status(self, ep_key, track_idx, status_text, percent):
        self.root.after(0, lambda: self._apply_track_status_update(ep_key, track_idx, status_text))

    def _apply_track_status_update(self, ep_key, track_idx, status_text):
        # Update Right Tree if displaying currently selected episode
        selected_items = self.ep_tree.selection()
        if selected_items:
            candidate = self.episode_id_map.get(selected_items[0])
            if candidate and candidate["id"] == ep_key:
                track_mappings = self.track_id_map.get(ep_key, [])
                mapped_item = next((x for x in track_mappings if x[0] == track_idx), None)
                if mapped_item:
                    item_id = mapped_item[1]
                    # Update status column (index 3)
                    vals = list(self.track_tree.item(item_id, "values"))
                    vals[3] = status_text
                    self.track_tree.item(item_id, values=vals)

    def set_overall_max(self, total):
        self.root.after(0, lambda: self._apply_overall_max(total))

    def _apply_overall_max(self, total):
        self.overall_bar.configure(maximum=total, value=0)
        self.overall_progress_lbl.configure(text=f"Datei 0 von {total} verarbeitet (0%)")

    def update_overall_progress(self, current):
        self.root.after(0, lambda: self._apply_overall_progress(current))

    def _apply_overall_progress(self, current):
        max_val = self.overall_bar.cget("maximum")
        self.overall_bar.configure(value=current)
        percent = int((current / max_val) * 100) if max_val > 0 else 0
        self.overall_progress_lbl.configure(text=f"Datei {current} von {max_val} verarbeitet ({percent}%)")

    def set_active_file(self, filename, size):
        self.root.after(0, lambda: self._apply_active_file(filename, size))

    def _apply_active_file(self, filename, size):
        self.file_lbl.configure(text=f"Übertrage: {filename}")
        self.file_bar.configure(maximum=size, value=0)
        self.file_progress_lbl.configure(text=f"0.00 B / {format_size(size)} (0%)")

    def update_active_progress(self, uploaded, percent):
        self.root.after(0, lambda: self._apply_active_progress(uploaded, percent))

    def _apply_active_progress(self, uploaded, percent):
        max_val = self.file_bar.cget("maximum")
        self.file_bar.configure(value=uploaded)
        self.file_progress_lbl.configure(text=f"{format_size(uploaded)} / {format_size(max_val)} ({int(percent)}%)")

    # Start Uploader Worker Thread
    def start_upload(self):
        if not self.folders:
            messagebox.showwarning("Achtung", "Keine Hörspiele gescannt. Bitte erst scannen.")
            return
            
        self.load_database()
        
        # Disable buttons
        self.start_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.dir_entry.state(["disabled"])
        
        self.worker = UploadWorker(self.music_dir, self.folders, self.tracks_db, self)
        self.worker.start()

    def stop_upload(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno("Abbrechen", "Möchten Sie den Upload-Prozess wirklich abbrechen?"):
                self.log("Interrupt signal sent. Stopping worker...")
                self.worker.stop()

    def on_upload_complete(self, count):
        self.root.after(0, lambda: self._apply_upload_complete(count))

    def _apply_upload_complete(self, count):
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])
        self.dir_entry.state(["!disabled"])
        self.file_lbl.configure(text="Upload abgeschlossen")
        
        # Reload everything
        self.scan_directory()
        messagebox.showinfo("Erfolg", f"Upload-Vorgang beendet.\n{count} neue Dateien erfolgreich hochgeladen!")

    def on_upload_stopped(self):
        self.root.after(0, self._apply_upload_stopped)

    def _apply_upload_stopped(self):
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])
        self.dir_entry.state(["!disabled"])
        self.file_lbl.configure(text="Upload abgebrochen")
        self.scan_directory()
        messagebox.showwarning("Abgebrochen", "Upload-Vorgang wurde vom Benutzer abgebrochen.")

    def on_upload_error(self, filename):
        self.root.after(0, lambda: self._apply_upload_error(filename))

    def _apply_upload_error(self, filename):
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])
        self.dir_entry.state(["!disabled"])
        self.file_lbl.configure(text="Fehler aufgetreten")
        self.scan_directory()
        messagebox.showerror("Fehler", f"Upload fehlgeschlagen bei Datei:\n{filename}\n\nDetails finden Sie im Protokoll.")


if __name__ == "__main__":
    root = tk.Tk()
    app = FileDitchUploaderGUI(root)
    root.mainloop()
