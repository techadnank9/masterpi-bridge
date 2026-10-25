# masterpi_bridge

Talk to a Hiwonder MasterPi in plain English. Gemini (`gemini-4-argon`) is the brain, the laptop runs the
loop, and the same commands drive either the real robot or its MuJoCo twin.

```
browser (localhost:3000) ──> agent/web.py ──> Gemini Interactions API (tools)
                                   │
                         masterpi.MasterPi client ─┬─> MasterPiRPC  (real robot, JSON-RPC :9030)
                                                   ├─> SimRPC       (MuJoCo twin, same RPC methods)
                                                   └─> DryRunRPC    (prints calls)
```

## Run it

```
python3 agent/web.py --sim        # MuJoCo lab, Gemini acts without asking
python3 agent/web.py              # real robot, every move waits for "Do it"
python3 agent/web.py --dry-run    # no robot, prints commands
python3 agent/run.py --sim "put the red block on the yellow square"   # terminal version
python3 cli.py ping | battery | stop | drive --dir 90 --sec 1 | arm-home | pose low
pytest tests/
```

`.env` needs `GEMINI_API_KEY=...`. The sim needs `mujoco` and `pillow`, and the model from
github.com/techadnank9/masterpi-mujoco cloned to `~/Documents/masterpi-mujoco` (or set `MASTERPI_MJCF`).

## The web app

One screen, no page scroll. Camera in the middle (live MJPEG; in the sim: Lab / Robot's eye / Top),
conversation strip below it, input and STOP at the bottom. STOP and Esc stop the motors at any time.
On the real robot each physical step shows one "Okay to do this?" card with a single primary "Do it".

## Simulation (masterpi/sim.py)

* Loads `masterpi.xml` and adds a lab: red, blue, green 3 cm blocks, a yellow target square, arena tape,
  a wall for the sonar, and `lab` / `top` cameras.
* Speaks the robot's own RPC methods (`SetBrushMotor`, `SetPWMServo`, ...), so the mecanum mixing, pulse
  conversion and Gemini tools are the same code that drives the real robot.
* Physics runs in real time on a thread, cameras render at 12 fps on another.
* Extra sim-only tools for Gemini: `locate` (perfect object detector), `approach`, `pick`, `place_on`.

Honest simplifications: the base moves by velocity actuators (0.005 m/s per motor duty point, no wheel
slip), closing the gripper within 3 cm of a block pins it to the gripper, and `locate` has no real-robot
equivalent yet.

Verified: Gemini, unprompted beyond one sentence, stacked red on the yellow square and blue on red in 112 s,
and a user's "put green block on red" ran end to end in 44 s.

## Real robot facts found on 2026-10-25

* **Pi 5 image**, Debian 12, SSH `pi` / `raspberrypi`. Code in `/home/pi/MasterPi`, SDK in `masterpi_sdk`
  (`common.ros_robot_controller_sdk.Board`, serial `/dev/ttyAMA0` at 1 Mbaud).
* `masterpi.service` (MasterPi.py, RPC on 9030, MJPEG on 8080) is installed but **disabled**: start it with
  `ssh pi@192.168.149.1 sudo systemctl start masterpi.service` after every boot.
* `SetPWMServo` params are `[time_ms, id, angle, id, angle, ...]`, no servo count.
* Stock `ArmMoveIk` always fails (calls an undefined `setPitchRangeMoving`). `masterpi/ik.py` ports
  Hiwonder's IK to the laptop; it matches the robot's own pulses exactly.
* Wi-Fi `HW-676EB762`, password `hiwonder`, robot at 192.168.149.1. iPhone USB tethering gives internet at
  the same time.
* Power: the robot reset every time all four motors started on half-charged cells (7.2 V under load).
  `drive` ramps up over 0.3 s to soften this. Run on full cells, or give the Pi its own USB-C supply.
