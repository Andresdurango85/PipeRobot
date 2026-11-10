# SO-101 build log

A dated record of assembling and setting up the real SO-101 arms: what was done, what went
wrong and how it was fixed. The steps and commands themselves live in the runbook,
[so101-bringup.md](../knowledge/so101-bringup.md). This file only records progress.

- Official guide: <https://huggingface.co/docs/lerobot/so101>. It follows LeRobot `main`, so
  check every command against the installed version first.
- Machine-specific values (COM ports, arm ids, the installed LeRobot version) go in
  `robots/so101/hardware.yaml`. That file is gitignored, so CI never sees it. Copy the
  template, [hardware.example.yaml](../../robots/so101/hardware.example.yaml).
- **Never swap the supplies: 12 V only to the follower, 5 V only to the leader.**
- Andrés runs the interactive commands (`setup-motors`, `calibrate`, `teleoperate`) himself. An
  agent never runs a command that moves a motor without saying so first.

## Hardware state (2026-11-10)

### Follower: complete

- 6× Feetech STS3215, 12 V (ST-3215-C018, 1/345). Any of them fits any joint.
- 12 V 5 A supply.
- Waveshare Bus Servo Adapter (A).

### Leader: incomplete

| Joint (ID) | Needed ratio | Needed part | In hand |
| --- | --- | --- | --- |
| `shoulder_pan` (1), base | 1/191 | C044 | **missing**, replacement ordered |
| `shoulder_lift` (2) | 1/345 | C001 | yes |
| `elbow_flex` (3) | 1/191 | C044 | **missing**, replacement ordered |
| `wrist_flex` (4) | 1/147 | C046 | yes |
| `wrist_roll` (5) | 1/147 | C046 | yes |
| `gripper` (6) | 1/147 | C046 | yes |

- 5 V 4 A supply and a Waveshare board.
- Two C018 (12 V) arrived instead of the two C044. They are **follower spares**: label them, and
  never put them in the leader.

### Other

- Printed parts ready (PLA, printed on the X2D).
- Computer: Windows. LeRobot environment: to be confirmed before step 2 (see the log).

## Checklist

Mark each step `[x]` with its date when done, and add a log entry for anything unexpected.
Command flags are checked against the installed LeRobot before each step.

- [ ] **1. Follower board**: Waveshare jumpers on channel **B** (USB), 12 V supply connected.
- [ ] **2. Follower port**: `lerobot-find-port` (it takes no arguments). Unplug the USB when
  asked; the port that disappears is the follower's. Record it in `hardware.yaml`.
- [ ] **3. Follower motor IDs**:
  `lerobot-setup-motors --robot.type=so101_follower --robot.port=<COM>`. One motor alone on
  the bus per prompt, in the order the script asks: `gripper` (6), `wrist_roll` (5),
  `wrist_flex` (4), `elbow_flex` (3), `shoulder_lift` (2), `shoulder_pan` (1). Label each
  motor with its ID as it is set.
- [ ] **4. Follower assembly**, joint by joint (joints 1 to 5, then the gripper), as in the
  official guide.
- [ ] **5. Follower calibration**:
  `lerobot-calibrate --robot.type=so101_follower --robot.port=<COM> --robot.id=<follower id>`.
  Back up the calibration file afterwards.
- [ ] **6. Leader**, once the two C044 arrive: 5 V supply, jumpers on B, then `find-port`,
  `lerobot-setup-motors --teleop.type=so101_leader --teleop.port=<COM>`, assembly, and
  `lerobot-calibrate --teleop.type=so101_leader --teleop.port=<COM> --teleop.id=<leader id>`.
- [ ] **7. Teleoperation**: `lerobot-teleoperate`, with the follower copying the leader.

## Problems and fixes

| Date | Step | Problem | Fix |
| --- | --- | --- | --- |
| 2026-11-10 | — | Two 12 V C018 servos arrived instead of the leader's two 1/191 C044 | Replacement ordered; the C018s are follower spares |

## Log

### 2026-11-10

- Build log started. Commands checked against LeRobot 0.6.1, the version pinned in `uv.lock`:
  - `lerobot-find-port` ignores `--help` and starts the interactive procedure at once, so run
    it only with the board connected;
  - `lerobot-setup-motors --help` lists `--robot.type` (`so101_follower`) and `--robot.port`, and
    `--teleop.type` (`so101_leader`) and `--teleop.port`.
- On the home PC, LeRobot 0.6.1 is installed in the CUDA venv, but without the servo
  dependencies (`pyserial`, `feetech-servo-sdk`). There is no conda there. Which machine and
  environment drive the arms is still to be decided.
