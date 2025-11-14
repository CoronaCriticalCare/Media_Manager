"""
Cross-platform main GUI for Media Tools (Linux, macOS, Windows)
"""

import os
import threading
import urllib.parse
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.simpledialog import askstring

# Optional: tkinterdnd2 may not be available everywhere; fallback to plain Tk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = tk.Tk
    DND_FILES = None
    DND_AVAILABLE = False

# PIL only used for loading a logo (non-critical)
try:
    from PIL import Image, ImageTk  # type: ignore
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

import time
import json

# Project modules (must exist in same package/folder)
import photo_scan
import cross_pic_organizer
import scanned_album
import clean_upload
import recognition


class PhotoToolsApp(TkinterDnD.Tk if DND_AVAILABLE else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Tools")
        self.geometry("1100x750")
        self.configure(bg="lightgray")

        self.logo_photos = {}
        self.dropped_paths = {}  # tab_name -> path
        self._create_widgets()

    # -------- UI --------
    def _create_widgets(self):
        # Notebook / tabs
        self.tab_control = ttk.Notebook(self)
        self.tabs = {}
        for name in ["Media Discovery", "Media Organizer", "Scanned Albums", "Clean Upload"]:
            frame = tk.Frame(self.tab_control, bg="lightgray")
            self.tabs[name] = frame
            self.tab_control.add(frame, text=name)
        self.tab_control.pack(fill="both", expand=True)

        # Add drop area + logo for each tab
        for tab_name, tab in self.tabs.items():
            drop_frame = tk.Frame(tab, bg="lightgray", pady=10)
            drop_frame.pack(pady=10)

            drop_label = tk.Label(drop_frame, text="Drop folder here\n(or click to select)",
                                   relief="groove", width=40, height=3, bg="white")
            drop_label.pack()

            # Bind DnD if available, else only fallback click
            if DND_AVAILABLE and tab_name in ["Media Discovery", "Scanned Albums", "Clean Upload"]:
                try:
                    drop_label.drop_target_register(DND_FILES)
                    # wrap handler to capture tab_name correctly
                    drop_label.dnd_bind("<<Drop>>", lambda e, tn=tab_name: self._on_drop_event(e, tn))
                except Exception:
                    # binding may fail on some platforms/wayland
                    pass

            # Always provide a fallback click-to-select
            drop_label.bind("<Button-1>", lambda evt, tn=tab_name: self._open_select_folder(tn))

            # Logo
            logo_frame = tk.Frame(tab, bg="lightgray")
            logo_frame.pack()
            logo_path = os.path.join("assets", "logo.png")
            if PIL_AVAILABLE and os.path.exists(logo_path):
                try:
                    logo_img = Image.open(logo_path)
                    logo_img = logo_img.resize((600, 300), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(logo_img)
                    self.logo_photos[tab_name] = photo
                    logo_label = tk.Label(logo_frame, image=photo, bg="lightgray")
                    logo_label.pack(pady=10)
                except Exception:
                    logo_label = tk.Label(logo_frame, text="[Logo error]", bg="lightgray")
                    logo_label.pack(pady=10)
            else:
                logo_label = tk.Label(logo_frame, text="[Logo not loaded]", bg="lightgray")
                logo_label.pack(pady=10)

        # Right-side control panel
        self.control_panel = tk.Frame(self, width=600, bg="white", relief="sunken", borderwidth=1)
        self.control_panel.place(relx=1.0, y=40, anchor="ne", relheight=0.85)
        self.update_controls("Media Discovery")
        self.tab_control.bind("<<NotebookTabChanged>>", self._on_tab_change)

        # Console
        self.console = tk.Text(self, height=25, bg="black", fg="lime", insertbackground="white")
        self.console.pack(fill="x", side="bottom")
        self._log_console("[Console Ready]")

        # Progress bar
        self.progress_frame = tk.Frame(self, bg="lightgray")
        self.progress_frame.pack(fill="x", pady=(2, 5))
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", padx=10)
        self.progress_label = tk.Label(self.progress_frame, text="0%", bg="lightgray")
        self.progress_label.pack(pady=5)

    def update_controls(self, tab_name):
        # clear existing
        for w in self.control_panel.winfo_children():
            w.destroy()

        if tab_name == "Clean Upload":
            tk.Label(self.control_panel, text="No JSON loaded.", bg="white").pack(pady=5)
            tk.Button(self.control_panel, text="Load JSON", command=self.load_json).pack(pady=5)
            tk.Button(self.control_panel, text="Run Clean Upload", command=self.run_upload).pack(pady=5)
        
        elif tab_name == "Media Discovery":
            tk.Button(self.control_panel, text="Scan Media", command=self.scan_media).pack(pady=5)
        
        elif tab_name == "Media Organizer":
            tk.Button(self.control_panel, text="Organize Media", command=self.organize_media).pack(pady=5)
            tk.Button(self.control_panel, text="Face Match Mode", command=self.face_match_mode).pack(pady=5)
        
        elif tab_name == "Scanned Albums":
            tk.Button(self.control_panel, text="Load Scanned", command=self.load_scanned).pack(pady=5)
            tk.Button(self.control_panel, text="Move Albums", command=self.move_albums).pack(pady=5)


    def face_match_mode(self):
        """Ask for target photos, source, and output, then run matching."""
        targets = filedialog.askopenfilenames(
            title="Select target face photos",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp *.tiff")]
        )

        if not targets:
            self._log_console("[FaceMatch] No target photos selected.")
            return
        
        source = filedialog.askdirectory(title="Select folder to scan")
        if not source:
            self._log_console("[FaceMatch] No source folder selected.")
            return
        
        dest = filedialog.askdirectory(title="Select destination for matched output.")
        if not dest:
            self._log_console("[FaceMatch] No destination selected.")
            return
        
        matched_folder = os.path.join(dest, "Matched")
        os.makedirs(matched_folder, exist_ok=True)

        self._log_console("[FaceMatch] Starting face rfecognition...")

        threading.Thread(
            target=self._face_match_thread,
            args=(list(targets), source, matched_folder),
            daemon=True
        ).start()

    def _face_match_thread(self, targets, source_folder, matched_folder, threshold=0.6):
        """Thread: use recognition.py cleanly."""
        try:
            # Load target encodings
            encs = recognition.build_target_encodings(
                targets,
                model="hog",
                log=self._log_console
            )

            if not encs:
                self._log_console("[FaceMatch] No valid targets faces found.")
                return
            
            # Run scan
            recognition.scan_and_copy_matches(
                encs,
                source_folder,
                matched_folder,
                threshold=threshold,
                model="hog",
                log=self._log_console,
                progress_callback=self.update_progress
            )

            self.update_progress(100)
            self._log_console("[FaceMatch] Completed.")

        except Exception as e:
            self._log_console(f"[FaceMatch] Fatal error: {e}")


    # -------- Events / Helpers --------
    def _on_tab_change(self, event):
        tab_name = event.widget.tab(event.widget.select(), "text")
        self.update_controls(tab_name)

    def _on_drop_event(self, event, tab_name):
        """
        Entry point for DnD events from tkinterdnd2.
        event.data can be many formats; normalize robustly.
        """
        # event.data often has braces, multiple paths, URL encoded, etc.
        raw = getattr(event, "data", "")
        self._log_console("RAW DROP EVENT: " + repr(raw))
        # Clean and extract candidate paths
        candidates = self._parse_drop_data(raw)
        self._log_console("Parsed candidates: " + ", ".join(repr(c) for c in candidates))
        # pick first existing directory
        for p in candidates:
            if os.path.isdir(p):
                self.dropped_paths[tab_name] = p
                self._log_console("[{}] Folder dropped: {}".format(tab_name, p))
                return
        self._log_console("[{}] No valid folder found in drop.".format(tab_name))

    def _parse_drop_data(self, raw):
        """
        Return list of cleaned paths from raw drop payload.
        Handles:
         - file:///... URL encoding
         - braces {}
         - quoted strings
         - multiple space-separated paths
         - Windows paths in braces
        """
        if not raw:
            return []

        # normalize line endings and trim
        s = raw.replace("\r", " ").replace("\n", " ").strip()

        # Sometimes input is like: {"/path/one" "/path/two"} or {C:\Path\One}
        # Remove leading/trailing braces if present, but keep splitting
        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1].strip()

        # Split on space but keep spaces within quoted paths
        parts = []
        cur = []
        in_quote = False
        quote_char = None
        for ch in s:
            if ch in ('"', "'"):
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                    continue
                elif quote_char == ch:
                    in_quote = False
                    quote_char = None
                    continue
            if ch.isspace() and not in_quote:
                if cur:
                    parts.append("".join(cur))
                    cur = []
                continue
            cur.append(ch)
        if cur:
            parts.append("".join(cur))

        cleaned = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            # handle file:// urls
            if p.startswith("file://"):
                # remove file:// and url-decode. macOS sometimes gives file:/// or file://localhost/
                # keep leading / when present
                url = p
                # If there is a host (file://localhost/...), remove it
                if url.startswith("file://localhost"):
                    url = url.replace("file://localhost", "file://")
                # strip scheme
                url_path = url[len("file://"):]
                # url decode
                url_path = urllib.parse.unquote(url_path)
                # On Windows file:///C:/... => path starts with /C:/ ; strip leading slash if necessary
                if os.name == "nt" and url_path.startswith("/") and len(url_path) > 2 and url_path[2] == ":":
                    url_path = url_path[1:]
                candidate = url_path
            else:
                candidate = urllib.parse.unquote(p)

            # final trim of quotes/braces
            candidate = candidate.strip().strip('"').strip("'").strip("{}")

            # On Windows-style paths coming through on *nix, convert backslashes
            candidate = candidate.replace("\\\\", "\\").replace("\\", os.sep)

            cleaned.append(candidate)
        return cleaned

    def _open_select_folder(self, tab_name):
        """Fallback: open dialog and store selected folder for tab."""
        folder = filedialog.askdirectory(title="Select folder for: " + tab_name)
        if folder:
            self.dropped_paths[tab_name] = folder
            self._log_console(f"[{tab_name}] Folder selected: {folder}")
        else:
            self._log_console(f"[{tab_name}] No folder selected.")

    # -------- Thread-safe logging / progress --------
    def _log_console(self, message):
        """Thread-safe append to console."""
        def append():
            try:
                self.console.insert(tk.END, message + "\n")
                self.console.see(tk.END)
            except Exception:
                # if console widget isn't ready, print to stdout as a fallback
                print(message)
        try:
            self.after(0, append)
        except Exception:
            print(message)
                  
    def update_progress(self, percent):
        """Thread-safe update of progress bar & label."""
        def update():
            try:
                p = max(0.0, min(100.0, float(percent)))
                self.progress_var.set(p)
                self.progress_label.config(text=f"{p:.1f}%")
                self.progress_frame.update_idletasks()
            except Exception as e:
                # Log safely via after to prevent recursion
                try:
                    self.after(0, lambda: self._log_console(f"[Progress Error] {e}"))
                except Exception:
                    print(f"[Progress Error] {e}")
            
            try:
                # percent may be a float or int
                self.after(0, update)
            except Exception:
                # Fallback
                try:
                    update()
                except Exception:
                    pass

    # ------------------- Actions wired to controls -------------------
    def load_json(self):
        self._log_console("Load JSON")

    def run_upload(self):
        source_folder = self.dropped_paths.get("Clean Upload")
        if not source_folder:
            self._log_console("[Clean Upload] No folder dropped.")
            return
        
        dest = filedialog.askdirectory(title="Select destination folder")
        if not dest:
            self._log_console("[Clean Upload] No destination selected.")
            return
        
        self._log_console(f"[Clean Upload] Copying from: {source_folder} -> {dest}")
        threading.Thread(target=self._run_upload_thread, args=(source_folder, dest), daemon=True).start()
    
    def _run_upload_thread(self, source_folder, dest):
        try:
            clean_upload.batch_clean_upload([source_folder], dest, log=self._log_console)
            self._log_console("[Clean Upload] Upload complete.")
        except Exception as e:
            self._log_console(f"[Clean Upload] Error: {e}")
    
    def scan_media(self):
        folder = self.dropped_paths.get("Media Discovery")
        if not folder:
            self._log_console("No folder dropped for Media Discovery.")
            return
        self._log_console(f"Scanning media in: {folder}")
        threading.Thread(target=self._scan_media_thread, args=(folder,), daemon=True).start()
    
    def _scan_media_thread(self, folder):
        try:
            # photo_scan.run_photo_scan supports log and progress_callback
            photo_scan.run_photo_scan(folder, log=self._log_console, progress_callback=self.update_progress)
            self.update_progress(100)
            self._log_console("[Media Discovery] Scan finished.")
        except Exception as e:
            self._log_console(f"[Media Discovery] Error: {e}")

    def organize_media(self):
        self._log_console("[Media Organizer] Starting input collection...")
        self.after(0, self._collect_organize_inputs)

    def _collect_organize_inputs(self):
        json_path = filedialog.askopenfilename(title="Select media JSON file", filetypes=[("JSON files", ".json")])
        if not json_path:
            self._log_console("[Media Organizer] No JSON selected.")
            return
        
        base_path = filedialog.askdirectory(title="Select destination base folder.")
        if not base_path:
            self._log_console("[Media Organizer] No destination folder selected.")
            return
        
        folder_name = askstring("Organized Album", "Enter a name for the organized folder (e.g., 'Family_ALbum'):")
        if not folder_name:
            self._log_console("[Media Organizer] Folder name required.")
            return
        
        threading.Thread(target=self._organize_media_thread, args=(json_path, base_path, folder_name), daemon=True).start()

    def _organize_media_thread(self, json_path, base_path, folder_name):
        try:
            media_dict = cross_pic_organizer.load_media_json(json_path, log=self._log_console)
            if not media_dict:
                self._log_console("[Media Organizer] Empty or failed to load JSON.")
                return
            cross_pic_organizer.organize_media(media_dict, base_path, folder_name, log=self._log_console, progress_callback=self.update_progress)
            self.update_progress(100)
            self._log_console(f"[Media Organizer] Done: {os.path.join(base_path, folder_name)}")
        except Exception as e:
            self._log_console(f"[Media Organizer] Error: {e}")

    def load_scanned(self):
        folder = self.dropped_paths.get("Scanned Albums")
        if not folder:
            self._log_console("[Scanned Albums] No scanned folders dropped.")
            return
        album_name = askstring("Default Album", "Enter default album name:")
        if not album_name:
            self._log_console("[Scanned Albums] No album name provided.")
            return
        tags_input = askstring("Tags", "Enter tags (comma separated):")
        tags = [t.strip() for t in (tags_input or "").split(",") if t.strip()]

        date_start = askstring("Start Date", "Enter start date (e.g., 8-4-25 or Aug 4 2025):")
        date_end = askstring("End Date", "Enter end date (e.g., 8-9-25 or AUg 9 2025):")
        if not date_start or not date_end:
            self._log_console("[Scanned Albums] Start and end dates are required.")
            return
        
        self._log_console(f"[Scanned Albums] Filtering by date: {date_start} to {date_end}")
        threading.Thread(
            target=scanned_album.scan_scanned_photos,
            args=(folder,),
            kwargs={"batch_mode": True, "default_album": album_name, "default_tags": tags, "date_start": date_start, "date_end": date_end, "log": self._log_console},
            daemon=True
        ).start()

    def move_albums(self):
        self._log_console("Moving scanned albums...")

if __name__ == "__main__":
    app = PhotoToolsApp()
    app.mainloop()