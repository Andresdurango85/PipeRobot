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
- **Out of scope for v1**: legs, stairs, heavy objects, voice.

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
- **Power**: a 2S Li-ion battery with BMS and fuse; a 6 V regulator for the servos and a separate
  5 V regulator for the Pi, because a voltage drop would reboot the Pi.
- **Body**: printed on a Bambu Lab X2D (256 × 256 × 260 mm build volume).
  - Chassis in PLA+/PETG; removable shell; TPU gripper tips; flexible eye stalks.
  - Cat-proof design: no small loose parts, internal cables, and gripper force limited in
    software.

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

## Gate scenarios

- Variations in lighting, object position and floor type (tile, rug).
- A push in the middle of the task.
- Docking from different starting points, with the dock partly hidden, or in low light.
- Fault injection: one eye covered, a servo that responds slowly. The robot must fail safely.

## Versions and their gates

| Version | Scope | Gate |
| --- | --- | --- |
| v0 · Digital twin | Design and simulation only; nothing bought | It moves and grasps in simulation |
| v1a · Base and eyes | Wheels, cameras, charging dock | It drives sideways and docks to charge on its own |
| v1b · Arms | Grippers, wrists, leader arms, teleoperation | 50 recorded demonstrations |
| v1c · Autonomous | Pick up, put away, return to charge | The full task on the real robot |
| v2 (future) | Eye tilt, a map of the house, maybe legs | — |

## Licensing

- The design is 100 % our own.
- Do not reuse parts of the Microduck: its models are CC BY-NC-SA.
- Check the license of LeKiwi, or of any other project, before taking anything from it.

## Priority rules

- The SO-101 Phase 0 comes first. No crab hardware is bought until the Phase 0 gate is met.
- v0 is design and simulation only, so it can run in parallel with the work that follows
  Phase 0.
- The gate code must stay generic. The crab is the second robot to use it, so everything
  specific to the SO-101 must stay isolated
  ([ADR 0015](../decisions/0015-generic-core-vs-robot-specific.md)).
