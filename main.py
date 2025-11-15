"""
Cross-Platform main GUI for Media Tools (Linux, macOS, Windows)
"""

import os
import threading
import urllib.parse
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.simpledialog import askstring

# Optional:; tkinterdnd2 may not be available everywhere; fall back to plain Tk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES # type: ignore
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = tk.Tk
    DND_FILES = None
    DND_AVAILABLE = False


# PIL only used for loading a logo (non-critical)
try:
    from PIL import Image, ImageTk # type: ignore
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Project modules (must exist in same folder)
import photo_scan
import cross_pic_organizer
import scanned_album
import clean_upload
import recognition


# ----------- Main App Class ----------
class PhotoToolsApp(TkinterDnD.Tk if DND_AVAILABLE else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Tools")
        self.geometry("1100x750")
        self.configure(bg="lightgray")

        self.logo_photos = {}
        self.dropped_paths = {} # tab_name -> path

        self._create_widgets()

    # ---------- UI Setup ----------
    def _create_widgets(self):
        # Notebook (tabs)
        self.tab_control = ttk.Notebook(self)
        self.tabs = {}
        for name in ["Media Discovery", "Media Organizer", "Scanned Albums", "Clean Upload"]:
            frame = tk.Frame(self.tab_control, bg="lightgray")
            self.tabs[name]  = frame
            self.tab_control.add(frame, text=name)

        self.tab_control.pack(fill="both", expand=True)
        self.tab_control.bind("<<NotebookTabChanged>>", self._on_tab_change)

        # Drop areas + logo in each tab
        for tab_name, tab in self.tabs.items():
            drop_frame = tk.Frame(tab, bg="lightgray", pady=10)
            drop_frame.pack(pady=10)

            drop_label = tk.Label(drop_frame,
                                    text="Drop folder here\n(or click to select)",
                                    relief="groove",
                                    width=40,
                                    height=3,
                                    bg="white")
            drop_label.pack()

            # DND if available
            if DND_AVAILABLE and tab_name in ["Media Discovery", "Scanned Albums", "Clean Upload"]:
                try:
                    drop_label.drop_target_register(DND_FILES)
                    drop_label.dnd_bind("<<Drop>>",
                                        lambda e, tn=tab_name: self._on_drop_event(e, tn))
                except Exception:
                    pass

            drop_label.bind("<Button-1>",
                            lambda evt, tn=tab_name: self._open_select_folder(tn))
                
            # Logo
            logo_frame = tk.Frame(tab, bg="lightgray")
            logo_frame.pack()

            logo_path = os.path.join("assets", "logo.png")
            if PIL_AVAILABLE and os.path.exists(logo_path):
                try:
                    img = Image.open(logo_path).resize((600, 300), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.logo_photo[tab_name] = photo
                    tk.LLabel(logo_frame, image=photo, bg="lightgray").pack(pady=10)
                except Exception:
                    tk.Label(logo_frame, text="[Logo error]", bg="lightgray").pack(pady=10)
            else:
                tk.Label(logo_frame, text="[Logo not loaded]", bg="lightgray").pack()
                
        # Control panel (right side)
        self.control_panel = tk.Frame(self, width=600,
                                        bg="white",
                                        relief="sunken",
                                        borderwidth=1)
        self.control_panel.place(relx=1.0, y=40, anchor="ne", relheight=0.85)
            
        self.update_controls("Media Discovery")

        # Console box
        self.console = tk.Text(self,
                                height=25,
                                bg="black",
                                fg="lime",
                                insertbackground="white")
        self.console.pack(fill="x", side="bottom")
        self._log_console("[Console Ready]")

        # Progress bar
        self.progress_frame = tk.Frame(self, bg="lightgray")
        self.progress_frame.pack(fill="x", pady=(2, 5))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.pack(fill="x", padx=10)
            
        self.progress_label = tk.Label(self.progress_frame,
                                        text="0%",
                                        bg="lightgray")
        self.progress_label.pack(pady=5)

    # ---------- Control Panel ----------
    def update_controls(self, tab_name):
        for w in self.control_panel.winfo_children():
            w.destroy()
            
        if tab_name == "Clean Upload":
            tk.Label(self.control_panel, text="No JSON loaded.",
                        bg="white").pack(pady=5)
            tk.Button(self.control_panel,
                        text="Load JSON",
                        command=self.load_json).pack(pady=5)
                
        elif tab_name == "Media Discovery":
            tk.Button(self.control_panel,
                        text="Scan Media",
                        command=self.scan_media).pack(pady=5)
            
        elif tab_name == "Media Organizer":
            tk.Button(self.control_panel,
                        text="Scan Media",
                        command=self.scan_media).pack(pady=5)

            tk.Button(self.control_panel,
                        text="Face Match Mode",
                        command=self.face_match_mode).pack(pady=5)
            
        elif tab_name == "Scanned Albums":
            tk.Button(self.control_panel,
                        text="Load Scanned",
                        command=self.load_scanned).pack(pady=5)
                
            tk.Button(self.control_panel,
                        text="Move Albums",
                        command=self.move_albums).pack(pady=5)
                
    # ---------- Face Match Mode ----------
    def face_match_mode(self):
        targets = filedialog.askopenfilenames(
            title="Select target face photos.",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp *.tiff")]
        )
        if not targets:
            self._log_console("[FaceMatch] No target photos selected.")
            return
            
        source = filedialog.askdirectory(title="Select folder to scan")
        if not source:
            self._log_console("[FaceMatch] No source folder selected.")
            return
            
        dest = filedialog.askdirectory(title="Select destination for matched.")
        if not dest:
            self._log_console("[FaceMatch] No destination selected.")
            return
            
        matched_folder = os.path.join(dest, "Matched")
        os.makedirs(matched_folder, exist_ok=True)

        self._log_console("[FaceMatch] Starting face recognition...")

        threading.Thread(
            target=self._log_face_match_thread,
            args=(list(targets), source, matched_folder),
            daemon=True
        ).start()

    def _face_match_thread(self, targets, source_folder, matched_folder, threshold=0.6):
        try:
            # Load face embeddings
            encs = recognition.build_target_encodings(
                targets,
                model="hog",
                log=self._log_console
            )

            if not encs:
                self._log_console("[FaceMatch] No valid target faces found.")
                return

            # Scan and copy
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

    # ---------- Tab Events ----------
    def _on_tab_change(self, event):
        tab = event.widget.tab(event.widget.select(), "text")
        self.update_controls(tab)

    # ---------- Drag & Drop ----------
    def _on_drop_event(self, event, tab_name):
        raw = getattr(event, "data", "")
        self._log_console("RAW DROP EVENT: " + repr(raw))
        candidates = self._parse_drop_data(raw)
        self._log_console("Parsed candidates: " + str(candidates))

        for p in candidates:
            if os.path.isdir(p):
                self.dropped_paths[tab_name] = p
                self._log_console(f"[{tab_name}] Folder dropped: {p}")
                return
                
        self._log_console(f"[{tab_name}] No valid directory found.")

    def _parse_drop_data(self, raw):
        if not raw:
            return []
            
        s = raw.replace("\r", " ").replace("\n", " ").strip()

        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1].strip()

        parts, buf = [], []
        in_q, qchar = False, None
        for ch in s:
            if ch in ('"', "'"):
                if not in_q:
                    in_q, qchar = True, ch
                    continue
                elif qchar == ch:
                    in_q, qchar = False, None
                    continue
                
            if ch.isspace() and not in_q:
                if buf:
                    parts.append("".join(buf))
                    buf = []
                continue

            buf.append(ch)

        if buf:
            parts.append("".join(buf))

        cleaned = []

        for p in parts:
            p = urllib.parse.unquote(p.strip().strip('"').strip("'").strip("{}"))

            # ----- Windows path fix -----
            p = p.replace("\\\\", "\\").replace("\\", os.sep)

            cleaned.append(p)

        return cleaned
        
    # ---------- Folder Select ----------
    def _open_select_folder(self, tab_name):
        folder = filedialog.askdirectory(title="Select folder for: " + tab_name)
        if folder:
            self.dropped_paths[tab_name] = folder
            self._log_console(f"[{tab_name}] Folder selectged: {folder}")
        else:
            self._log_console(f"[{tab_name}] No folder selected.")

    # ---------- Logging ----------
    def _log_console(self, message):
        def append():
            try:
                self.console.insert(tk.END, message + "\n")
                self.console.see(tk.END)
            except:
                print(message)

        self.after(0, append)

    # ---------- Progress Bar ----------
    def update_progress(self, percent):
        def update():
            try:
                p = max(0.0, min(100.0, float(percent)))
                self.progress_var.set(p)
                self.progress_label.config(text=f"{p:.1f}%")
            except Exception as e:
                self._log_console(f"[Progress Error] {e}")

        self.after(0, update)

    # ---------- Clean Upload ----------
    def load_json(self):
        self._log_console("Load JSON clicked.")

    def run_upload(self):
        src = self.dropped_paths.get("Clean Upload")
        if not src:
            self._log_console("[Clean Upload] No folder dropped.")
            return
            
        dest = filedialog.askdirectory(title="Select destination folder")
        if not dest:
            self._log_console("[CLean Upload] No destination selected.")
            return

        self._log_console(f"[Clean Upload] Copy from {src} -> {dest}")

        threading.Thread(
            target=self._run_upload_thread,
            args=(src, dest),
            daemon=True
        ).start()

    def _run_upload_thread(self, src, dest):
        try:
            clean_upload.batch_clean_upload([src], dest,
                                                log=self._log_console)
            self._log_console("[Clean Upload] Upload complete.")
        except Exception as e:
            self._log_console(f"[Clean Upload] Error: {e}")

    # ---------- Media Discovery ----------
    def scan_media(self):
        folder = self.dropped_paths.get("Media Discovery")
        if not folder:
            self._log_console("No folder dropped for Media Discovery.")
            return
            
        self._log_console(f"Scanning: {folder}")

        threading.Thread(
            target=self._scan_media_thread,
             args=(folder,),
            daemon=True
        ).start()

    def _scan_media_thread(self, folder):
        try:
            photo_scan.run_photo_scan(
                folder,
                log=self._log_console,
                progress_callback=self.update_progress
            )
            self.update_progress(100)
            self._log_console("[Media Discovery] Done.")
        except Exception as e:
            self._log_console(f"[Media Discovery] Error: {e}")

    # ---------- Organizer ----------
    def organize_media(self):
        self._log_console("[Media Organizer] Starting...")
        self.after(0, self._collect_organize_iputs)

    def _collect_organize_inputs(self):
        json_path = filedialog.askopenfilename(
            title="Select media JSON file",
            filetypes=[("JSON files", ".json")]
        )
        if not json_path:
            self._log_console("[Media Organizer] No JSON selected.")
            return
            
        base_path = filedialog.askdirectory(
            title="Select destination base folder"
        )
        if not base_path:
            self._log_console("[Media Organizer] No folder selected.")
            return
            
        folder_name = askstring("Organized Album", "Enter name of organized folder: ")
        if not folder_name:
            self._log_console("[Media Organizer] Name required.")
            return
            
        threading.Thread(
            target=self._organize_media_thread,
            args=(json_path, base_path, folder_name),
            daemon=True
        ).start()
        
    def _organize_media_thread(self, json_path, base_path, folder_name):
        try:
            media_dict = cross_pic_organizer.load_media_json(
                json_path,
                log=self._log_console
            )
            if not media_dict:
                self.log_console("[Media Organizer] Empty JSON.")
                return
                
            cross_pic_organizer.organize_media(
                media_dict,
                base_path,
                folder_name,
                log=self._log_console,
                progress_callback=self.update_progress
                )

            self.update_progress(100)
            self._log_console("Media Organizer] Done.")

        except Exception as e:
            self._log_console(f"[Media Organizer] Error: {e}")

    # ---------- Scanned Albums ----------
    def load_scanned(self):
        folder = self.dropped_paths.get("Scanned Albums")
        if not folder:
            self._log_console("[Scanned Albums] No folder dropped.")
            return
            
        album_name = askstring("Default Album", "Enter default album name:")
        if not album_name:
            self._log_console("[Scanned Albums] Album name required.")
            return
            
        tags_input = askstring("Tags", "Enter tags (comma separated):")
        tags = [t.strip() for t in (tags_input or "").split(",") if t.strip()]

        date_start = askstring("Start Date", "Start date:")
        date_end = askstring("End Date", "End date:")
        if not date_start or not date_end:
            self._log_console("[Scanned Albums] Missing dates.")
            return
            
        self._log_console(f"[Scanned Albums] Date range {date_start} -> {date_end}")

        threading.Thread(
            target=scanned_album.scan_scanned_photos,
            args=(folder,),
            kwargs=dict(
                batch_mode=True,
                default_album=album_name,
                default_tags=tags,
                date_start=date_start,
                date_end=date_end,
                log=self._log_console
            ),
            daemon=True
        ).start()
        
    def move_albums(self):
        self._log_console("Moving scanned albums.. [placeholder]")

if __name__ == "__main__":
    app = PhotoToolsApp()
    app.mainloop()