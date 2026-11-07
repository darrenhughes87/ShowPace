# ShowPace

A running order and show caller for live events. Free, and it runs on almost anything.

You build the running order. On the day, you press **Complete** as each segment ends, and every screen keeps up: your laptop, the crew's phones, and the speaker's clock on stage.

**What it does**

- **Edit:** build the running order, with sections, cues, people, and audio, lighting and video notes.
- **Call:** run the show. Countdown, Complete, ±1 minute, jump to any row, and an adhoc timer for when it all goes wrong.
- **Crew:** a private link for the crew. They see what's on now and what's next, live.
- **Clock:** a big countdown for the speaker. It goes green, then orange, then red.
- **Upload:** turn a spreadsheet (CSV or Excel) into a show.
- **Caller remote:** run the show from your phone.
- **Speaker messages:** send a short note to the speaker's clock, like Wrap up or Speak up. It shows where the title was, so the countdown never moves.

There's nothing to install apart from Python. No database. Your shows are saved as files.

---

## Pick one

- **Just trying it, or using it at one venue?** [Run it on your computer](#run-it-on-your-computer). Takes 2 minutes.
- **Want a web address that works from anywhere?** [Put it on a server](#put-it-on-a-server-vps). Takes about 15 minutes.

---

## Run it on your computer

Phones and iPads on the same Wi-Fi can connect to it too.

### Mac

1. **Get ShowPace.** On this page, press the green **Code** button, then **Download ZIP**. Double-click the ZIP to unzip it.
2. **Open Terminal.** Press `Cmd + Space`, type `Terminal`, press Enter.
3. **Go into the folder.** Type `cd ` (with a space after it), drag the ShowPace folder into the Terminal window, then press Enter.
4. **Start it:**

   ```bash
   python3 server.py
   ```

5. **Open it.** Go to http://localhost:4320 in your browser.

If your Mac says `python3` isn't found, or pops up asking to install developer tools: install Python from [python.org/downloads](https://www.python.org/downloads/), then try step 4 again.

### Windows

1. **Get Python.** Download it from [python.org/downloads](https://www.python.org/downloads/) and run the installer. On the first screen, tick **Add python.exe to PATH**.
2. **Get ShowPace.** On this page, press the green **Code** button, then **Download ZIP**. Right-click the ZIP, choose **Extract All**.
3. **Open a command window in the folder.** Open the ShowPace folder, click in the address bar at the top, type `cmd`, press Enter.
4. **Start it:**

   ```bash
   py server.py
   ```

5. **If Windows asks about the firewall,** click **Allow**. That lets phones and iPads on your Wi-Fi connect.
6. **Open it.** Go to http://localhost:4320 in your browser.

If `py` isn't found, try `python server.py` instead.

### Linux

```bash
git clone https://github.com/darrenhughes87/ShowPace.git
```

```bash
cd ShowPace
```

```bash
python3 server.py
```

Then open http://localhost:4320.

### Good to know

- **The first time you open it,** it asks you to make an admin login. That's you.
- **Phones and iPads:** when it starts, it prints a second address, like `http://192.168.1.20:4320`. Type that on any device on the same Wi-Fi.
- **To stop it:** press `Ctrl + C` in the window. To start it again, run the same command.
- **Your shows** are saved in the `data` folder, inside the ShowPace folder. Copy that folder to back them up.
- **Port already in use?** Run it on another one: `python3 server.py --port 4321` (on Windows, `py server.py --port 4321`).

---

## Put it on a server (VPS)

This gives you a proper web address with HTTPS (the padlock), so it works from anywhere. The install script does the hard bits for you.

### What you need

- **A VPS** running Ubuntu 22.04 or 24.04, or Debian 12. The smallest size is fine (1 CPU, 1GB memory).
- **A web address you control,** like `shows.yourcompany.com`.
- **Nothing else running on the server's web ports** (80 and 443). A fresh server is perfect.

### Step 1: Point your address at the server

In your domain's DNS settings (wherever you bought the domain), add an **A record**:

- **Name:** `shows` (or whatever you want before your domain)
- **Value:** your server's IP address

Then wait 5 to 10 minutes for it to take effect.

### Step 2: Log in to your server

On your computer, open Terminal (or Command Prompt on Windows) and type this, with your server's IP address:

```bash
ssh root@YOUR-SERVER-IP
```

### Step 3: Download ShowPace onto the server

```bash
sudo apt update && sudo apt install -y git
```

```bash
git clone https://github.com/darrenhughes87/ShowPace.git
```

```bash
cd ShowPace
```

### Step 4: Install it

```bash
sudo bash install.sh
```

It installs Docker if it's missing, asks for your web address, and starts ShowPace. When it says **Done!**, you're ready.

### Step 5: Open it

Go to your address, like `https://shows.yourcompany.com`, and make your admin login.

**If you logged in as root,** you can leave out the word `sudo` in all of these commands.

### Looking after it

Run these from inside the ShowPace folder on the server (`cd ShowPace` first).

**Update to the latest version:**

```bash
git pull && sudo docker compose up -d --build
```

**Back up your shows** (makes a `showpace-backup` folder):

```bash
sudo docker compose cp showpace:/data ./showpace-backup
```

**Forgot your password?** This sets a new password for that login (and makes it an admin):

```bash
sudo docker compose exec showpace python3 server.py adduser YOURNAME
```

**Something not working?** See what it's saying:

```bash
sudo docker compose logs
```

**The address won't load after installing?** Nine times out of ten, the A record from step 1 isn't pointing at the server yet. Check it, wait a few minutes, then run `sudo bash install.sh` again. Some hosts also have their own firewall in their dashboard: make sure ports 80 and 443 are open there.

---

## Using it

1. **Make your admin login** the first time you open it.
2. **Add your team.** On the Shows page, press **Admin** (top right). Add a login for each person. Tick **Admin** for anyone who should be able to add people and change settings.
3. **Make it yours.** Also on the Admin page: the app's name, your company name, the main colour, and how long people stay logged in.
4. **Make a show.** Press **New show**. Or press **Download template**, fill it in (Excel is fine), then **Upload running order**.
5. **Run it.** Open the show and press **Call**. Press **Start show**, then **Complete** as each segment ends.
6. **Share it.** From the **Crew** menu: a crew link, the speaker **Clock**, and the **caller remote** for your phone.
   Crew links only show the show while it's live: press **Push live** in the Crew menu. Before that they say "This show isn't open yet". When you take it off (or archive it), every crew screen says "This show has finished". Push it live again and they come straight back.
7. **Talk to the speaker.** In the **Crew** menu, press **Message the speaker**. Pick one or type your own, then **Send**. It clears itself when you press Complete, or press ✕.

**On a stage iPad:** in the iPad's Settings, set Auto-Lock to Never. In Safari, Share, then Add to Home Screen, opens ShowPace full screen.

**Colours on the clock:** green while it runs, orange in the last couple of minutes, red when it's over. The speaker's clock stops at 0:00 and goes red, so they never see how far over they are. You still do.

---

## For tinkerers

**Settings you can set before starting it:**

| Setting | What it does | Default |
|---|---|---|
| `SHOWPACE_PORT` | The port it runs on | `4320` |
| `SHOWPACE_DATA` | Where shows and logins are saved | the `data` folder |
| `SHOWPACE_SECURE` | Set to `1` when it's behind HTTPS | off |
| `SHOWPACE_PROXY` | Set to `1` when it's behind a proxy like Caddy | off |

**From the command line:**

```bash
python3 server.py adduser NAME
```

```bash
python3 server.py deluser NAME
```

**Run the tests:**

```bash
python3 test_server.py
```

Then open http://localhost:4320/?selftest and look in the browser console for `selftest passed`.

**What's inside:** `server.py` (the whole server, Python standard library only), `index.html` (the whole app), and `docker-compose.yml` with `Caddyfile` for the server setup.

---

## Licence

MIT, so you can use it, change it and share it for free. See [LICENSE](LICENSE).

The QR codes come from [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) by Kazuhiko Arase, also MIT.
