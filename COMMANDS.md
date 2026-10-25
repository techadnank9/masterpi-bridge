# Robot day cheat sheet

Run these from `~/Documents/masterpi_bridge` (or use the full path `~/Documents/masterpi_bridge/net.sh`).

## Once

| Command | What it does |
|---|---|
| `./net.sh fix-order` | Put the iPhone cable ahead of Wi-Fi so you stay online on the robot's Wi-Fi (asks for your Mac password) |

Phone: plugged in by cable, Personal Hotspot on, "Allow Others to Join" on.

## Network

| Command | What it does |
|---|---|
| `./net.sh robot` | Join the robot's Wi-Fi `HW-676EB762` |
| `./net.sh phone` | Join the iPhone hotspot |
| `./net.sh status` | Where am I, is the robot reachable, is there internet |

## Robot

| Command | What it does |
|---|---|
| `./net.sh up` | Join robot Wi-Fi, start its control service, check battery and camera |
| `./net.sh start` | Start the control service (needed after every robot boot) |
| `./net.sh check` | Battery, control server, camera |
| `./net.sh ssh` | Shell on the robot |

## Drive it

| Command | What it does |
|---|---|
| `python3 agent/web.py --sim` | Web app at http://localhost:3000, starts in the simulation (switch to Real robot in the header) |
| `python3 agent/web.py` | Web app, starts on the real robot |
| `python3 cli.py stop` | Stop the motors |
| `python3 cli.py battery` | Battery in mV |
| `python3 cli.py arm-home` | Arm to home |
| `python3 cli.py drive --dir 90 --sec 1 --speed 30` | Drive: 90 forward, 270 back, 0 right, 180 left |
| `python3 cli.py gripper --pulse 1500` | Gripper: 1500 open, ~2000 closed |
| `python3 cli.py pose low` | Arm poses: home, right, reach_r, reach_l, low |

## If something is off

| Symptom | Fix |
|---|---|
| Robot Wi-Fi not in the list | Robot off or restarting. One beep + steady lights = ready. Hold KEY1 to force its own Wi-Fi |
| Robot keeps beeping and restarting | Batteries low: fresh 18650s, or a USB-C supply into the Pi |
| `robot: reachable, control server off` | `./net.sh start` |
| No internet on robot Wi-Fi | `./net.sh fix-order`, phone cable in, Personal Hotspot on |
| Anything moves wrong | STOP button, Esc, or `python3 cli.py stop`. Hand on the power switch |
