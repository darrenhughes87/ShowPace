"""ShowPace as a double-click app. It starts the server, opens the browser and shows one small window with the
addresses. Closing the window stops ShowPace. PyInstaller turns this into ShowPace.app and ShowPace.exe
(see .github/workflows/release.yml); `python3 app.py` runs the same thing from the folder."""
import os, subprocess, sys, threading, tkinter as tk, urllib.request, webbrowser
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
        subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
    elif os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on a high-resolution screen
        except (AttributeError, OSError):
            pass


def main():
    os.makedirs(server.DATA, exist_ok=True)
    server.load()
    srv, port = start()
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
             + ('\nIf Windows asks about the firewall, choose Allow.' if os.name == 'nt' else '')).pack(anchor='w', pady=(14, 16))
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
        root.after(5000, refresh)
    refresh()
    webbrowser.open(url)
    root.mainloop()


if __name__ == '__main__':
    main()
