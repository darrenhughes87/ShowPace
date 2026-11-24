"""ShowPace as a double-click app. It starts the server, opens the browser and shows one small window with the
addresses and a tick box that puts the Clock full screen on a second display. Closing the window stops ShowPace. PyInstaller turns this into ShowPace.app and ShowPace.exe
(see .github/workflows/release.yml); `python3 app.py` runs the same thing from the folder."""
import json, os, secrets, subprocess, sys, tempfile, threading, tkinter as tk, urllib.request, webbrowser
import server


def start():
    """The server on the first free port from 4320. If ShowPace is already running, hand over to that copy instead."""
    for port in range(server.PORT, server.PORT + 20):
        try:
            return server.Server(('0.0.0.0', port), server.Handler), port
        except OSError:
            try:  # is it us? Two copies sharing one set of files would overwrite each other
                urllib.request.urlopen(f'http://localhost:{port}/api/time', timeout=2)
            except OSError:
                continue  # something else has this port: try the next
            webbrowser.open(f'http://localhost:{port}')
            sys.exit()
    sys.exit('No free port for ShowPace')


def keep_awake():
    """A sleeping laptop stops the show for everyone, so ask the computer to stay awake while ShowPace is open."""
    if sys.platform == 'darwin':
        subprocess.Popen(['caffeinate', '-di', '-w', str(os.getpid())])  # the screens too: a stage clock must not go dark
    elif os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on a high-resolution screen
        except (AttributeError, OSError):
            pass


def screens():
    """Every display as (left, top), measured from the top left corner of the main one, which is (0, 0)."""
    if sys.platform == 'darwin':
        js = ('ObjC.import("AppKit"); JSON.stringify($.NSScreen.screens.js.map(s => '
              '[s.frame.origin.x, s.frame.origin.y, s.frame.size.height]))')
        out = json.loads(subprocess.run(['osascript', '-l', 'JavaScript', '-e', js], capture_output=True, text=True, timeout=10).stdout or '[]')
        return [(int(x), int(out[0][2] - y - h)) for x, y, h in out]  # macOS measures up from the bottom of the main display
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        found = []
        each = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)
        ctypes.windll.user32.EnumDisplayMonitors(None, None, each(lambda mon, dc, r, _: found.append((r.contents.left, r.contents.top)) or 1), 0)
        return found
    return []


def browser():
    """Chrome or Edge: the browsers that can be told to open full screen on a chosen display."""
    if sys.platform == 'darwin':
        paths = [f'/Applications/{a}.app/Contents/MacOS/{a}' for a in ('Google Chrome', 'Microsoft Edge')]
    else:
        paths = [os.path.join(os.environ.get(v, ''), p) for p in (r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe')
                 for v in ('ProgramFiles(x86)', 'ProgramFiles', 'LocalAppData')]
    return next((p for p in paths if os.path.isfile(p)), None)


def stage_command(exe, at, url):
    """A browser of its own (its own profile, so it never joins one that's already open), full screen on the display at `at`.
    It starts as a small window, so it sits wholly on that display before it fills it."""
    return [exe, f'--app={url}', '--kiosk', '--edge-kiosk-type=fullscreen', f'--window-position={at[0] + 40},{at[1] + 40}', '--window-size=800,600',
            '--user-data-dir=' + os.path.join(tempfile.gettempdir(), 'showpace-stage'), '--no-first-run', '--no-default-browser-check']


def main():
    os.makedirs(server.DATA, exist_ok=True)
    server.load()
    srv, port = start()
    server.STAGE = secrets.token_urlsafe(16)  # only this app knows it, so only its own second screen gets the clock without a crew link
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    keep_awake()
    url = f'http://localhost:{port}'
    root = tk.Tk()
    root.title(f'ShowPace {server.VERSION}')
    root.resizable(False, False)
    box = tk.Frame(root, padx=24, pady=20)
    box.pack()
    tk.Label(box, text='ShowPace is running', font=('TkDefaultFont', 18, 'bold')).pack(anchor='w')
    tk.Label(box, text=f'On this computer:   {url}').pack(anchor='w', pady=(10, 0))
    lan = tk.StringVar()
    tk.Label(box, textvariable=lan).pack(anchor='w', pady=(4, 0))
    tk.Label(box, justify='left', text='Keep this window open during the show. Closing it stops ShowPace.\n'
             'Keep the computer plugged in, with its lid open.'
             + ('\nIf Windows asks about the firewall, choose Allow.' if os.name == 'nt' else '')).pack(anchor='w', pady=(14, 10))
    stage, on, note = [], tk.BooleanVar(), tk.StringVar()

    def stage_off():
        while stage:
            stage.pop().terminate()

    def stage_toggle():
        stage_off()
        note.set('')
        if not on.get():
            return
        exe, second = browser(), next((s for s in screens() if s != (0, 0)), None)
        if not exe or not second:
            on.set(False)
            return note.set('Plug in a second screen first, set to extend, not mirror.' if exe else 'The second screen needs Chrome or Edge installed.')
        stage.append(subprocess.Popen(stage_command(exe, second, f'{url}/v/{server.STAGE}?stage#timer')))
    tk.Checkbutton(box, text='Clock on second screen', variable=on, command=stage_toggle).pack(anchor='w')
    tk.Label(box, textvariable=note).pack(anchor='w', pady=(0, 10))
    row = tk.Frame(box)
    row.pack(anchor='w')
    show_files = lambda: os.startfile(server.DATA) if os.name == 'nt' else subprocess.Popen(
        ['open' if sys.platform == 'darwin' else 'xdg-open', server.DATA])
    tk.Button(row, text='Open ShowPace', command=lambda: webbrowser.open(url)).pack(side='left')
    tk.Button(row, text='Show my files', command=show_files).pack(side='left', padx=8)
    tk.Button(row, text='Quit', command=root.destroy).pack(side='left')

    def refresh():  # the network can change under a running laptop: a new Wi-Fi, a cable in or out
        ip = server.lan_address()
        lan.set(f'On other devices:   http://{ip}:{port}   (same Wi-Fi)' if ip else 'On other devices:   join a Wi-Fi network first')
        if stage and stage[0].poll() is not None:  # someone closed the clock by hand: untick the box
            stage.clear()
            on.set(False)
        root.after(5000, refresh)
    refresh()
    webbrowser.open(url)
    root.mainloop()
    stage_off()


if __name__ == '__main__':
    main()
