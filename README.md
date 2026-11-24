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

No accounts, no subscription, no database. Your shows are saved as files on your own computer.

---

## Pick one

- **Using it at a venue?** [Download the app](#download-the-app) for Mac or Windows. Takes 2 minutes.
- **Want a web address that works from anywhere?** [Put it on a server](#put-it-on-a-server-vps). Takes about 15 minutes.
- **Rather run it from the code?** [Run it with Python](#run-it-with-python).

---

## Download the app

Go to the [latest release](https://github.com/darrenhughes87/ShowPace/releases/latest) and download the one for your computer. Everything it needs is inside. There's nothing else to install.

The apps aren't signed with Apple or Microsoft (that costs money every year), so each one asks if you're sure the first time. After that it just opens.

### Mac

1. Download **ShowPace-Mac.zip** and double-click it to unzip.
2. Drag **ShowPace** into your Applications folder, then open it.
3. **The first time, macOS refuses to open it.** Press **Done**, then go to **System Settings**, **Privacy & Security**, scroll to the bottom and press **Open Anyway**.
4. If it asks about incoming network connections, press **Allow**. That lets phones and iPads connect.

### Windows

1. Download **ShowPace-Windows.exe** and open it.
2. **If you see "Windows protected your PC",** press **More info**, then **Run anyway**.
3. **If it asks about the firewall,** press **Allow**. That lets phones and iPads connect.

### What you get

A small window that says **ShowPace is running**, and ShowPace opens in your browser. The first time, it asks you to make an admin login. That's you.

- **Keep the window open during the show.** Closing it stops ShowPace.
- **It keeps your computer and its screens awake** while it's open. Keep the lid open and the charger in.
- **Clock on second screen** puts the speaker's clock full screen on a second display. See [A stage screen plugged into your computer](#a-stage-screen-plugged-into-your-computer).
- **Show my files** opens the folder where your shows are saved. Copy that folder to back them up.
- **Forgot your password?** Press **Show my files**, delete `users.json`, then quit and reopen ShowPace. It asks you to make a new login. Your shows are kept.
- **A newer version?** Download it and replace the old app. Your shows and logins stay where they are.

### A stage screen plugged into your computer

Got a TV, monitor or projector plugged into the computer that runs ShowPace? Tick **Clock on second screen** in the ShowPace window. That screen fills with the clock. No dragging windows about.

- **It follows the show by itself.** Press **Start show** and the countdown appears. You don't need a link, and you don't need to push the show live.
- **Before the show,** and after it ends, it shows a plain holding screen.
- **Untick the box** to clear the screen.
- **It needs Chrome or Edge.** Windows already has Edge. On a Mac, install Chrome or Edge first. Safari can't do this.
- **Set the second screen to extend, not mirror.** On a Mac: System Settings, Displays. On Windows: press the Windows key and P, then pick **Extend**.

---

## On site

ShowPace runs on your computer, and every other screen connects to it over the network. So the network is the thing to get right.

**1. Put everything on the same network.** Pick one:

- **Your own travel router** (the best). Plug it in, join your laptop, iPads and phones to its Wi-Fi. It works with no internet at all.
- **Your phone's hotspot.** Join the laptop and the other devices to it.
- **The venue's Wi-Fi.** Test it first. Many venues stop devices talking to each other, and then nothing can connect. If the QR code won't load on your phone, that's why. Use a hotspot or your own router.

**2. Connect the other screens.** On the Shows page press **Open on another device** and scan the QR code. Every link in ShowPace has a QR code:

- **Crew link** and **Crew page:** for crew phones.
- **Clock link:** for the stage screen.
- **Caller remote:** to run the show from your phone.

**3. Stop screens going to sleep.**

- **On a stage iPad:** Settings, Display & Brightness, Auto-Lock, **Never**. Plug it in.
- **For a full-screen clock on an iPad:** in Safari, press Share, then **Add to Home Screen**, and open it from there.
- **On the laptop:** the app keeps it awake, and any screen plugged into it. Keep the lid open and the charger in.

**4. Do a test before doors.** Start the show, check the clock on stage moves, press Back. If a screen says it's offline, it has dropped off the Wi-Fi: it reconnects by itself when it's back.

Screens need a browser from the last few years: Safari 16.4 or newer on iPhones and iPads, or any recent Chrome, Edge or Firefox.

---

## Run it with Python

The app is just this code with Python packed in. If you already have Python 3.8 or newer, you can run it straight from the folder.

Get the code with the green **Code** button, then **Download ZIP**, and unzip it. Or:

```bash
git clone https://github.com/darrenhughes87/ShowPace.git
```

Open a terminal in the ShowPace folder and start it.

**Mac and Linux:**

```bash
python3 server.py
```

**Windows:**

```bash
py server.py
```

Then open http://localhost:4320. It prints the address for other devices too.

- **No Python?** Get it from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** on the first screen.
- **To stop it:** press `Ctrl + C`.
- **Your shows** are saved in the `data` folder inside the ShowPace folder.
- **Port already in use?** `python3 server.py --port 4321`
- **Want the little window too?** `python3 app.py` runs the same thing the app does.

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
6. **Share it.** From the **Crew & stage** menu: a crew link, the speaker **Clock** link, and the **caller remote** for your phone. Each one comes with a QR code.
   Crew links only show the show while it's live: press **Push live** in the Crew & stage menu. Before that they say "This show isn't open yet". When you take it off (or archive it), every crew screen says "This show has finished". Push it live again and they come straight back.
   Push live with a crew password and everyone has to type it, even people who already have the link. Push live again and they're asked again, so you can always shut someone out by changing the password.
7. **Talk to the speaker.** In the **Crew & stage** menu, press **Message the speaker**. Pick one or type your own, then **Send**. It clears itself when you press Complete, or press ✕.

**Colours on the clock:** green while it runs, orange in the last couple of minutes, red when it's over. The speaker's clock stops at 0:00 and goes red, so they never see how far over they are. You still do.

---

## For tinkerers

**Settings you can set before starting it:**

| Setting | What it does | Default |
|---|---|---|
| `SHOWPACE_PORT` | The port it runs on | `4320` |
| `SHOWPACE_DATA` | Where shows and logins are saved | the `data` folder (the app uses your own app-data folder) |
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

**What's inside:** `server.py` (the whole server, Python standard library only), `index.html` (the whole app), `app.py` (the little window for the Mac and Windows apps), and `docker-compose.yml` with `Caddyfile` for the server setup.

**Building the apps:** push a version tag like `v1.0.1`. GitHub builds `ShowPace-Mac.zip` and `ShowPace-Windows.exe` with PyInstaller and adds them to that release (see `.github/workflows/release.yml`). Change `VERSION` in `server.py` to match first.

---

## Licence

MIT, so you can use it, change it and share it for free. See [LICENSE](LICENSE).

The QR codes come from [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) by Kazuhiko Arase, also MIT.
