#!/usr/bin/env python3
"""chromiumcacheprobe GUI: a tkinter window over chromiumcacheprobe.py.

Standard library only, like the tool it drives. The window runs the command line
tool as a subprocess with the same options it takes, so what it shows is what the
command line prints:

  List entries     runs ``entries`` on the cache folder and shows one row per entry
                   file: URL, HTTP status, content type and the three times.
  Rebuild videos   runs ``recover --progress`` into a new run folder under the output
                   folder, drives the progress bar from the JSON lines on stderr, and
                   lists the rebuilt clips from the run's provenance.json. Double-click
                   a clip to open it.

The cache folder is only read. Output goes to a new folder under the output folder,
which must be outside the cache folder.

    python3 chromiumcacheprobe_gui.py                  open the window
    python3 chromiumcacheprobe_gui.py CACHE_FOLDER     open it with the folder chosen
    python3 chromiumcacheprobe_gui.py --cli ...        run the command line tool; this
                                                       is how the window starts it, and
                                                       what makes one frozen executable
                                                       work
    python3 chromiumcacheprobe_gui.py --smoke CACHE OUTPUT
                                                       no visible window: build it, run
                                                       a rebuild through it, print what
                                                       it listed, and exit
"""

import json
import os
import queue
import runpy
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chromiumcacheprobe as ccp  # noqa: E402  pylint: disable=wrong-import-position

TITLE = "chromiumcacheprobe"
ENTRY_COLUMNS = ("file", "url", "status", "content_type", "request_time", "response_time", "last_used")
CLIP_COLUMNS = ("file", "kind", "frames", "seconds", "size", "audio", "warnings", "sha256")


def probe_command():
    """How to start the command line tool as a subprocess.

    Frozen into one executable there is no chromiumcacheprobe.py beside us and
    sys.executable is this program, so the window re-enters itself with --cli.
    The unfrozen case takes the same route so it is the path that gets tested.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cli"]
    return [sys.executable, os.path.abspath(__file__), "--cli"]


def run_cli(argv):
    """Run chromiumcacheprobe's command line with these arguments, in this process."""
    sys.argv = ["chromiumcacheprobe.py"] + list(argv)
    try:
        runpy.run_module("chromiumcacheprobe", run_name="__main__", alter_sys=False)
    except SystemExit as done:
        return done.code if isinstance(done.code, int) else 0
    return 0


def open_path(path):
    """Open a file or folder with the system's default application."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # pylint: disable=no-member
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # pylint: disable=consider-using-with
    else:
        subprocess.Popen(["xdg-open", path])  # pylint: disable=consider-using-with


def clip_rows(run_folder):
    """Rows for the clip table, read from a run's provenance.json."""
    with open(os.path.join(run_folder, "provenance.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    rows = []
    for clip in manifest.get("clips", []):
        copied = clip.get("kind") == "complete_mp4_carved"
        rows.append((
            clip["file"],
            "byte copy" if copied else "rebuilt",
            clip.get("video_frames", ""),
            round(clip["video_seconds"], 3) if "video_seconds" in clip else "",
            f"{clip['width']}x{clip['height']}" if clip.get("width") else "",
            "" if copied else ("yes" if clip.get("audio") else "no"),
            ", ".join(clip.get("warnings", [])),
            clip["sha256"],
        ))
    return manifest.get("status", ""), rows


def build_window(initial_folder="", smoke=None):
    """Build the window. With ``smoke`` = (cache, output) it runs one rebuild hidden."""
    import tkinter as tk  # pylint: disable=import-outside-toplevel
    from tkinter import filedialog, messagebox, ttk  # pylint: disable=import-outside-toplevel
    import tkinter.font as tkfont  # pylint: disable=import-outside-toplevel

    root = tk.Tk()
    root.title(f"{TITLE} {ccp.__version__}")
    root.geometry("1000x640")
    root.minsize(760, 480)
    if smoke:
        root.attributes("-alpha", 0.0)
    state = {"proc": None, "streams": 0, "mode": None, "run": "", "result": None}
    lines = queue.Queue()

    # ---- inputs -------------------------------------------------------------
    form = ttk.Frame(root, padding=8)
    form.pack(fill="x")
    v_cache = tk.StringVar(value=initial_folder)
    v_output = tk.StringVar()
    for row, (label, var, hint) in enumerate((
            ("Cache folder", v_cache, "the Cache or Cache_Data folder inside com.android.chrome/cache"),
            ("Output folder", v_output, "a new run folder is created here; must be outside the cache folder"))):
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", pady=2)
        ttk.Button(form, text="Browse...",
                   command=lambda v=var, t=label: v.set(filedialog.askdirectory(title=t) or v.get())
                   ).grid(row=row, column=2, padx=(6, 0), pady=2)
        ttk.Label(form, text=hint, foreground="gray").grid(row=row, column=3, sticky="w", padx=(8, 0))
    form.columnconfigure(1, weight=1)

    buttons = ttk.Frame(root, padding=(8, 0))
    buttons.pack(fill="x")
    b_entries = ttk.Button(buttons, text="List entries")
    b_recover = ttk.Button(buttons, text="Rebuild videos")
    b_cancel = ttk.Button(buttons, text="Cancel", state="disabled")
    b_open = ttk.Button(buttons, text="Open output", state="disabled")
    for button in (b_entries, b_recover, b_cancel, b_open):
        button.pack(side="left", padx=(0, 6))

    status_bar = ttk.Frame(root, padding=(8, 6))
    status_bar.pack(fill="x")
    progress = ttk.Progressbar(status_bar, mode="determinate", maximum=100)
    progress.pack(side="left", fill="x", expand=True)
    status = ttk.Label(status_bar, text="Choose a cache folder.", width=48)
    status.pack(side="left", padx=(8, 0))

    # ---- results ------------------------------------------------------------
    panes = ttk.PanedWindow(root, orient="vertical")
    panes.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    table_frame = ttk.Frame(panes)
    table = ttk.Treeview(table_frame, show="headings")
    scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
    table.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    table.grid(row=0, column=0, sticky="nsew")
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x.grid(row=1, column=0, sticky="ew")
    table_frame.rowconfigure(0, weight=1)
    table_frame.columnconfigure(0, weight=1)
    log = tk.Text(panes, height=8, wrap="word", state="disabled")
    panes.add(table_frame, weight=3)
    panes.add(log, weight=1)

    def write(text):
        log.configure(state="normal")
        log.insert("end", text)
        log.see("end")
        log.configure(state="disabled")

    def font_of(style, fallback):
        name = ttk.Style().lookup(style, "font") or fallback
        try:
            return tkfont.nametofont(name)
        except tk.TclError:
            return tkfont.Font(font=name)

    cell_font = font_of("Treeview", "TkDefaultFont")
    heading_font = font_of("Treeview.Heading", "TkHeadingFont")

    # Columns do not stretch: each grows to fit the longest value added, and the
    # horizontal scrollbar reaches whatever is wider than the window. A stretching
    # column is shrunk to fit the window instead, which hides the end of its values.
    def set_columns(columns):
        table.delete(*table.get_children())
        table["columns"] = columns
        for column in columns:
            text = column.replace("_", " ")
            table.heading(column, text=text)
            table.column(column, width=heading_font.measure(text) + 16, minwidth=40, stretch=False)

    def add_row(values):
        table.insert("", "end", values=values)
        for column, value in zip(table["columns"], values):
            need = cell_font.measure(str(value)) + 16
            if need > int(table.column(column, "width")):
                table.column(column, width=need)

    # ---- running the command line ---------------------------------------------
    def pump(stream, tag):
        for line in iter(stream.readline, b""):
            lines.put((tag, line.decode("utf-8", "replace")))
        lines.put((tag, None))

    def start(mode):
        cache = v_cache.get().strip()
        if not os.path.isdir(cache):
            messagebox.showinfo(TITLE, "Choose the cache folder first.")
            return
        args = probe_command()
        if mode == "entries":
            args += ["entries", cache]
            set_columns(ENTRY_COLUMNS)
        else:
            output = v_output.get().strip()
            if not output:
                messagebox.showinfo(TITLE, "Choose an output folder first.")
                return
            args += ["recover", cache, "-o", output, "--progress"]
            set_columns(CLIP_COLUMNS)
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        shown = ["chromiumcacheprobe.py"] + args[args.index("--cli") + 1:]
        write("$ " + " ".join(a if " " not in a else f'"{a}"' for a in shown) + "\n")
        state.update(mode=mode, run="", stdout=[], header=True)
        progress["value"] = 0
        status["text"] = "running..."
        for button in (b_entries, b_recover, b_open):
            button["state"] = "disabled"
        b_cancel["state"] = "normal"
        try:
            state["proc"] = subprocess.Popen(  # pylint: disable=consider-using-with
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        except OSError as error:
            messagebox.showerror(TITLE, f"Could not start chromiumcacheprobe: {error}")
            finish(None)
            return
        state["streams"] = 2
        threading.Thread(target=pump, args=(state["proc"].stdout, "out"), daemon=True).start()
        threading.Thread(target=pump, args=(state["proc"].stderr, "err"), daemon=True).start()
        root.after(50, poll)

    def on_stdout(line):
        if state["mode"] == "entries":
            if state["header"]:
                state["header"] = False
                return
            values = line.rstrip("\n").split("\t")
            add_row(values + [""] * (len(ENTRY_COLUMNS) - len(values)))
        else:
            state["stdout"].append(line)

    def on_stderr(line):
        try:
            record = json.loads(line)
        except ValueError:
            write(line)
            return
        if not isinstance(record, dict) or "stage" not in record:
            write(line)
            return
        total = record.get("total_files") or 0
        if record["stage"] == "scanning" and total and "files" in record:
            progress["value"] = 80.0 * record["files"] / total
            status["text"] = f"reading {record['files']:,} of {total:,} files"
        elif record["stage"] == "parsing_fragments":
            progress["value"] = 80
            status["text"] = f"rebuilding from {record.get('fragments', 0):,} fragments"
        elif record["stage"] in ("video_recovered", "mp4_carved"):
            status["text"] = f"{record.get('clips', 0):,} clips"

    def poll():
        try:
            while True:
                tag, line = lines.get_nowait()
                if line is None:
                    state["streams"] -= 1
                elif tag == "out":
                    on_stdout(line)
                else:
                    on_stderr(line)
        except queue.Empty:
            pass
        proc = state["proc"]
        if proc is not None and (proc.poll() is None or state["streams"] > 0):
            root.after(50, poll)
            return
        finish(proc.returncode if proc is not None else None)

    def finish(code):
        for button in (b_entries, b_recover):
            button["state"] = "normal"
        b_cancel["state"] = "disabled"
        state["proc"] = None
        if state["mode"] == "recover" and state.get("stdout"):
            try:
                summary = json.loads("".join(state["stdout"]))
                state["run"] = summary["output"]
                run_status, rows = clip_rows(state["run"])
                for row in rows:
                    add_row(row)
                write(f"\nRun folder: {state['run']}\nStatus: {run_status}\n")
                b_open["state"] = "normal"
            except (ValueError, KeyError, OSError) as error:
                write(f"\nCould not read the run's results: {error}\n")
        count = len(table.get_children())
        if code == 0:
            progress["value"] = 100
            noun = "entries" if state["mode"] == "entries" else "clips"
            status["text"] = f"done: {count:,} {noun}"
        elif code is None:
            status["text"] = "not started"
        elif code < 0:
            status["text"] = "cancelled"
        else:
            status["text"] = f"chromiumcacheprobe exited {code}"
        state["result"] = (code, count)
        if smoke:
            root.after(10, root.destroy)

    def cancel():
        proc = state["proc"]
        if proc is not None and proc.poll() is None:
            proc.terminate()
            write("\n[cancelled: a cancelled run removes the clips it had not finished]\n")

    def open_selected(_event=None):
        selection = table.selection()
        if state["mode"] != "recover" or not selection or not state["run"]:
            return
        open_path(os.path.join(state["run"], table.item(selection[0], "values")[0]))

    b_entries.configure(command=lambda: start("entries"))
    b_recover.configure(command=lambda: start("recover"))
    b_cancel.configure(command=cancel)
    b_open.configure(command=lambda: state["run"] and open_path(state["run"]))
    table.bind("<Double-1>", open_selected)

    def on_close():
        cancel()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    if smoke:
        v_cache.set(smoke[0])
        v_output.set(smoke[1])
        root.after(100, lambda: start("recover"))
    root.mainloop()
    return state["result"]


def main(argv):
    if argv and argv[0] == "--cli":
        return run_cli(argv[1:])
    if argv and argv[0] == "--smoke":
        if len(argv) != 3:
            print("usage: chromiumcacheprobe_gui.py --smoke CACHE_FOLDER OUTPUT_FOLDER", file=sys.stderr)
            return 2
        code, rows = build_window(smoke=(os.path.abspath(argv[1]), os.path.abspath(argv[2]))) or (None, 0)
        print(json.dumps({"exit": code, "rows": rows}))
        return 0 if code == 0 else 1
    build_window(os.path.abspath(argv[0]) if argv and os.path.isdir(argv[0]) else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
