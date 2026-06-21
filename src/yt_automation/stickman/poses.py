"""A library of named key poses.

All poses face "forward/right" by convention. Angles follow
:mod:`.skeleton` (clockwise from up: 0 up, 90 right, 180 down, 270 left).
Authoring rule of thumb for a relaxed limb: ~180 = straight down, lower than
180 leans the limb toward screen-right, higher leans toward screen-left.
"""

from __future__ import annotations

from .skeleton import Pose

STAND = Pose()

# Subtle idle breathing — two near-identical poses to ping-pong between.
BREATHE_A = Pose(squash=1.0, arm_l_upper=203, arm_r_upper=157, head=0)
BREATHE_B = Pose(squash=0.985, arm_l_upper=200, arm_r_upper=160, head=1.5,
                 pelvis_dy=0.012)

# --- Walk cycle (facing right) ---------------------------------------------
WALK_CONTACT_R = Pose(
    torso=4,
    arm_l_upper=150, arm_l_fore=140, arm_r_upper=215, arm_r_fore=225,
    leg_l_upper=205, leg_l_lower=212, leg_r_upper=158, leg_r_lower=150,
    pelvis_dy=0.02,
)
WALK_PASS = Pose(
    torso=3,
    arm_l_upper=182, arm_l_fore=178, arm_r_upper=178, arm_r_fore=182,
    leg_l_upper=178, leg_l_lower=200, leg_r_upper=184, leg_r_lower=181,
    pelvis_dy=-0.01,
)
WALK_CONTACT_L = WALK_CONTACT_R.mirrored()  # but keep facing right
WALK_CONTACT_L = Pose(
    torso=4,
    arm_l_upper=215, arm_l_fore=225, arm_r_upper=150, arm_r_fore=140,
    leg_l_upper=158, leg_l_lower=150, leg_r_upper=205, leg_r_lower=212,
    pelvis_dy=0.02,
)

# --- Run cycle (faster, leaning forward) -----------------------------------
RUN_A = Pose(
    torso=15,
    arm_l_upper=120, arm_l_fore=70, arm_r_upper=235, arm_r_fore=300,
    leg_l_upper=225, leg_l_lower=250, leg_r_upper=140, leg_r_lower=120,
    pelvis_dy=0.01,
)
RUN_B = Pose(
    torso=15,
    arm_l_upper=235, arm_l_fore=300, arm_r_upper=120, arm_r_fore=70,
    leg_l_upper=140, leg_l_lower=120, leg_r_upper=225, leg_r_lower=250,
    pelvis_dy=0.01,
)

# --- Emphatic gestures ------------------------------------------------------
POINT_FORWARD = Pose(
    torso=6,
    arm_r_upper=95, arm_r_fore=92,           # right arm straight forward
    arm_l_upper=205, arm_l_fore=200,
    leg_l_upper=196, leg_r_upper=168,
)
POINT_UP = Pose(
    torso=-3,
    arm_r_upper=18, arm_r_fore=8,            # right arm up
    arm_l_upper=200, arm_l_fore=198,
    head=-4,
)
THINK = Pose(
    torso=-2, head=10,
    arm_r_upper=55, arm_r_fore=340,          # hand up to chin
    arm_l_upper=210, arm_l_fore=160,         # other arm folded across
    leg_l_upper=193, leg_r_upper=171,
)
IDEA = Pose(                                  # eureka — both arms up in a V
    torso=0, head=-6,
    arm_l_upper=335, arm_l_fore=330,
    arm_r_upper=25, arm_r_fore=30,
    squash=1.02, pelvis_dy=-0.02,
)
SHRUG = Pose(
    torso=0, head=4,
    arm_l_upper=232, arm_l_fore=288,
    arm_r_upper=128, arm_r_fore=72,
    leg_l_upper=198, leg_r_upper=166,
)
CHEER = Pose(
    torso=-4, head=-8,
    arm_l_upper=330, arm_l_fore=338,
    arm_r_upper=30, arm_r_fore=22,
    leg_l_upper=200, leg_r_upper=160,
    squash=1.03, pelvis_dy=-0.03,
)
PANIC = Pose(
    torso=-6, head=-10,
    arm_l_upper=310, arm_l_fore=340,
    arm_r_upper=60, arm_r_fore=20,
    leg_l_upper=205, leg_l_lower=210, leg_r_upper=158, leg_r_lower=152,
)
FACEPALM = Pose(
    torso=8, head=18,
    arm_r_upper=40, arm_r_fore=330,          # hand to face
    arm_l_upper=200, arm_l_fore=205,
)
PUNCH = Pose(
    torso=14,
    arm_r_upper=92, arm_r_fore=90,           # lead arm extended
    arm_l_upper=240, arm_l_fore=300,         # rear arm cocked
    leg_l_upper=210, leg_l_lower=214, leg_r_upper=150, leg_r_lower=148,
    pelvis_dy=0.02,
)
POWER = Pose(                                 # wide power stance, fists down
    torso=0,
    arm_l_upper=222, arm_l_fore=232,
    arm_r_upper=138, arm_r_fore=128,
    leg_l_upper=205, leg_l_lower=210, leg_r_upper=155, leg_r_lower=150,
    pelvis_dy=0.02,
)

# --- Crouch / fall / jump ---------------------------------------------------
CROUCH = Pose(
    torso=10,
    arm_l_upper=200, arm_l_fore=240, arm_r_upper=160, arm_r_fore=120,
    leg_l_upper=212, leg_l_lower=250, leg_r_upper=148, leg_r_lower=110,
    pelvis_dy=0.16, squash=0.92,
)
COLLAPSE = Pose(                              # slumped, defeated
    torso=22, head=26,
    arm_l_upper=205, arm_l_fore=210, arm_r_upper=158, arm_r_fore=150,
    leg_l_upper=214, leg_l_lower=255, leg_r_upper=150, leg_r_lower=110,
    pelvis_dy=0.22, squash=0.84,
)
JUMP_TUCK = Pose(
    torso=-2,
    arm_l_upper=330, arm_l_fore=325, arm_r_upper=30, arm_r_fore=35,
    leg_l_upper=208, leg_l_lower=255, leg_r_upper=152, leg_r_lower=105,
    pelvis_dy=-0.10, squash=1.04,
)
AIRBORNE = Pose(
    torso=2,
    arm_l_upper=320, arm_l_fore=315, arm_r_upper=40, arm_r_fore=45,
    leg_l_upper=188, leg_l_lower=183, leg_r_upper=172, leg_r_lower=177,
    pelvis_dy=-0.02, squash=1.06,
)

# --- Signature / character poses -------------------------------------------
MIND_BLOWN = Pose(
    torso=0, head=-4,
    arm_l_upper=325, arm_l_fore=300,
    arm_r_upper=35, arm_r_fore=60,
    leg_l_upper=196, leg_r_upper=164,
    squash=1.03, pelvis_dy=-0.02,
)
SALUTE = Pose(
    torso=2,
    arm_r_upper=78, arm_r_fore=345,
    arm_l_upper=200, arm_l_fore=198,
    leg_l_upper=193, leg_r_upper=171,
)
FINGER_GUNS = Pose(
    torso=6,
    arm_r_upper=92, arm_r_fore=88,
    arm_l_upper=104, arm_l_fore=100,
    leg_l_upper=198, leg_r_upper=166,
)
MIC_DROP = Pose(
    torso=-8, head=-6,
    arm_r_upper=120, arm_r_fore=150,
    arm_l_upper=215, arm_l_fore=235,
    leg_l_upper=205, leg_r_upper=160,
)
LEAN = Pose(
    torso=12, head=-4,
    arm_r_upper=150, arm_r_fore=110,
    arm_l_upper=205, arm_l_fore=205,
    leg_l_upper=185, leg_l_lower=183, leg_r_upper=166, leg_r_lower=178,
)
ARMS_CROSSED = Pose(
    torso=0,
    arm_l_upper=205, arm_l_fore=86,
    arm_r_upper=155, arm_r_fore=274,
    leg_l_upper=193, leg_r_upper=171,
)

POSES: dict[str, Pose] = {
    "stand": STAND, "breathe_a": BREATHE_A, "breathe_b": BREATHE_B,
    "walk_contact_r": WALK_CONTACT_R, "walk_pass": WALK_PASS,
    "walk_contact_l": WALK_CONTACT_L, "run_a": RUN_A, "run_b": RUN_B,
    "point_forward": POINT_FORWARD, "point_up": POINT_UP, "think": THINK,
    "idea": IDEA, "shrug": SHRUG, "cheer": CHEER, "panic": PANIC,
    "facepalm": FACEPALM, "punch": PUNCH, "power": POWER, "crouch": CROUCH,
    "collapse": COLLAPSE, "jump_tuck": JUMP_TUCK, "airborne": AIRBORNE,
    "mind_blown": MIND_BLOWN, "salute": SALUTE, "finger_guns": FINGER_GUNS,
    "mic_drop": MIC_DROP, "lean": LEAN, "arms_crossed": ARMS_CROSSED,
}

# Signature poses used to add brand flavour on punchy/emphasis shots.
SIGNATURE_POSES: list[str] = [
    "mind_blown", "finger_guns", "salute", "mic_drop", "lean", "arms_crossed",
]
