# Project Cangrejo

A home robot of our own, designed from scratch, shaped like a crab. It is the second robot the
gate validates after the SO-101: the use case that shows the pipeline works for any robot, not
just one arm. "Cangrejo" is Spanish for crab.

## Concept (v1)

- **Base** with 3 hidden omnidirectional wheels: it moves sideways like a real crab and turns on
  the spot.
- **Two arms with grippers**, each with shoulder yaw, shoulder pitch, elbow, wrist roll and
  gripper. Target payload: about 100 g.
- **Two camera eyes on stalks**, each with its own yaw servo (about ±90°). Three modes:
  - explore: each eye looks to one side;
  - stereo: both eyes on the same point, to compute depth;
  - watch the gripper.
- **Automatic charging dock**, like a robot vacuum. When the battery drops below a threshold, the
  robot:
  - looks for the dock with its eyes (an AprilTag-style marker);
  - lines up using the omni wheels;
  - connects through spring contacts;
  - checks that the voltage rises, and retries if it does not.
- **Wide, low base**: it hardly ever tips over, so v1 does not need to learn to get up.
- **Sound**: a speaker and a microphone, so it can play sounds (status, low battery, a "found it"
  chirp) and listen (detect a sound and turn its eyes towards it).
- **Wi-Fi**: it joins the home network; the laptop streams the cameras and sends commands over it.
- **Out of scope for v1**: legs, stairs, heavy objects, and understanding speech (voice commands
  or conversation).

## Proposed hardware

- **Servos**: 15 Feetech servos on a single bus at 6 V.
  - 9 × STS3215, 7.4 V version (1/345): 3 wheels in wheel mode, 2 shoulder yaw, 2 shoulder
    pitch, 2 elbows.
  - 6 × STS3032 (20 g, 4.5 kg·cm peak at 6 V): 2 wrists, 2 grippers, 2 eyes.
  - Do not use the 12 V STS3215 servos of the SO-101 follower: they cannot share a supply voltage
    with the STS3032.
- **Brain**: an on-board Raspberry Pi 5 running LeRobot, with a LeKiwi-style architecture. The Pi
  drives the robot; the laptop receives the cameras and sends commands over Wi-Fi.
- **Cameras**: 2 × Arducam OV5647 "spy" cameras (6 mm head, 300 mm ribbon cable), one per CSI
  connector on the Pi 5. Still to confirm: the 15-to-22-pin adapter.
- **Wi-Fi**: built into the Raspberry Pi 5 (dual-band 802.11ac); no extra hardware.
- **Audio**: the Pi 5 has no analog audio jack, so sound needs one of these (to choose):
  - an I2S amplifier and speaker plus an I2S MEMS microphone, on the Pi's GPIO header;
  - or a small USB audio adapter or USB speakerphone (simpler, takes a USB port).

  The speaker amplifier draws from the 5 V rail, so size the Pi's regulator for it. Servo noise
  will reach the microphone: mount it away from the wheels and shoulders.
- **Power**: a 2S2P Li-ion pack of 21700 cells (about 7.2 V, 10 Ah, 72 Wh) with BMS and fuse; a
  6 V regulator for the servos and a separate 5 V regulator for the Pi, because a voltage drop
  would reboot the Pi. Details and estimates in [Energy](#energy).
- **Body**: printed on a Bambu Lab X2D (256 × 256 × 260 mm build volume).
  - Chassis in PLA+/PETG; removable shell; TPU gripper tips; flexible eye stalks.
  - Cat-proof design: no small loose parts, internal cables, and gripper force limited in
    software.

## Energy

All figures are estimates to check against measurements (development flow, step 4).

**Power budget**

| Part | Resting | Working |
| --- | ---: | ---: |
| Raspberry Pi 5 (Wi-Fi, two cameras streaming to the laptop) | ~3–4 W | ~5–7 W |
| 3 wheel servos | ~0 | ~5–9 W while driving |
| 6 large arm servos (holding a pose) | ~0 (torque off) | ~3–6 W |
| 6 small servos (wrists, grippers, eyes) | ~0.3 W | ~1–2 W |
| Audio | ~0.1 W | ~0.5–1 W |
| Regulator losses (~10–15 %) | ~0.5 W | ~2 W |
| **Total** | **~4–5 W** | **~15–25 W average, 30–40 W peaks** |

The policy runs on the laptop (LeKiwi-style), so the Pi does not pay for inference.

**Battery: 2S2P 21700 Li-ion, ~72 Wh, ~280 g of cells**

- Estimated runtime with ~70 % usable (it returns to the dock with a reserve): **~2.5–3.5 h
  working**, much longer resting.
- Under 100 Wh on purpose: above that, lithium batteries are restricted on flights and in parcel
  shipping.
- Cylindrical cells in a rigid holder, not LiPo pouches: safer with a cat in the house.
- Cells rated for high discharge: several servos starting or stalling at once can draw over 10 A;
  the BMS and the fuse are sized for it.
- The 6 V buck regulator needs headroom above its output, and a 2S pack falls to ~6.0 V when
  empty. Returning to the dock at ~20–25 % (~3.6 V per cell) keeps that headroom; the threshold is
  measured as voltage under load, not only as a percentage.

**Charging**

- The BMS protects the pack but does not charge it. The robot carries a 2S charger (constant
  current, then constant voltage to 8.4 V, with cell balancing); the dock only supplies DC through
  the spring contacts, whose current rating limits the charge rate.
- At 2 A a full charge takes about 5 h; at the 20–25 % return threshold, about 4 h.

**Spending less (often 30–50 % more runtime)**

- A rest pose: the arms fold onto the chassis and the servos release their torque. Holding the
  arms up is the biggest idle cost.
- Light arms: low infill, servos close to the shoulder.
- Cameras by mode: lower resolution and frame rate while exploring or waiting; full quality only
  when grasping.
- The Pi powers down on the dock: the Pi 5 has a real-time clock and a low-power off state with a
  scheduled wake-up.
- Synchronous buck regulators (~90–95 % efficient), never linear regulators.

**Charging between tasks**

What matters for a home robot is runtime per mission, not total runtime: like a robot vacuum, it
lives on the dock and leaves when there is something to do. An optional tool-free, cat-proof
battery swap would not add runtime but would make a flat battery a 10-second fix.

## Development flow

1. Design in Onshape, with every joint named.
2. Export to URDF/MJCF with onshape-to-robot (Rhoban).
3. Digital twin in MuJoCo or Isaac Lab, with a floor, objects, a box and the charging dock.
4. Measure the real motors and tune the simulation to match.
5. Integrate it into LeRobot as a new robot, following the LeKiwi model.
6. Teleoperation:
   - wheels with a keyboard or a gamepad;
   - arms with two small printed leader arms of the same shape.
7. Train with ACT, the same policy family as the SO-101.
8. Every policy goes through the gate before it touches the real robot.

## Tasks to train, in order

1. Pick an object up from the floor and drop it in a box (imitation learning).
2. Search for an object with the eyes and approach it (rules and vision first, a policy later).
3. Bring the object to a person.
4. Return to the charging dock on its own.

## Privacy and the network

- Microphone audio and camera images stay on the home network and the laptop. They never go into
  a public dataset, Hub repo or CI artifact; recorded demonstrations are reviewed before sharing.
- Listening is visible: an LED (or the eyes' pose) shows when the microphone is on.
- Speaker volume has a software cap (the cat).
- The robot keeps working when Wi-Fi drops: it stops the current motion safely and waits, and it
  can still return to the dock on its own.

## Gate scenarios

- Variations in lighting, object position and floor type (tile, rug).
- A push in the middle of the task.
- Docking from different starting points, with the dock partly hidden, or in low light.
- Battery: it finishes a task and reaches the dock with at least 20 % left, from the farthest
  point of the home; if the battery runs low mid-task, it drops the task and goes to charge.
  First in simulation with a power model, then measured on the real robot.
- Fault injection: one eye covered, a servo that responds slowly, the Wi-Fi link dropping, the
  microphone muted. The robot must fail safely.
- Sound: turning towards a sound with background noise (TV, music, its own servos).

## Versions and their gates

| Version | Scope | Gate |
| --- | --- | --- |
| v0 · Digital twin | Design and simulation only; nothing bought | It moves and grasps in simulation |
| v1a · Base, eyes and sound | Wheels, cameras, speaker, microphone, Wi-Fi, charging dock | It drives sideways, docks to charge on its own, and turns towards a sound |
| v1b · Arms | Grippers, wrists, leader arms, teleoperation | 50 recorded demonstrations |
| v1c · Autonomous | Pick up, put away, return to charge | The full task on the real robot |
| v2 (future) | Eye tilt, a map of the house, maybe legs | — |

## Licensing

- The design is 100 % our own.
- Do not reuse parts of the Microduck: its models are CC BY-NC-SA.
- Check the license of LeKiwi, or of any other project, before taking anything from it.

## Priority rules

- The SO-101 Phase 0 comes first. No crab hardware is bought until the Phase 0 gate is met.
- v0 is design and simulation only, so it can start now, in parallel with Phase 0, as long as it
  does not delay it.
- The crab's design files (CAD exports, URDF/MJCF, meshes) and their license live in a private
  repo, not here. Its gate runs there, installing this repo's `piperobot` package
  ([ADR 0019](../decisions/0019-core-adapters-robots-layout.md)).
- The gate code must stay generic. The crab is the second robot to use it, so everything
  specific to the SO-101 must stay isolated
  ([ADR 0015](../decisions/0015-generic-core-vs-robot-specific.md)).
