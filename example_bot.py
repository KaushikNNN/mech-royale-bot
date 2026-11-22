
"""Mech Royale V6: V4 looting with predictive gun aiming."""

import math
import mechfight as mf


class Bot:
    name = "predictive-v6"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]
        self.gun_speed = hello["config"]["weapons"]["gun"].get(
            "speed", 252.0
        )

    def predict_target(self, me, enemy, speed):
        """Calculate a constant-velocity intercept point."""

        x, y, z = me["pos"]
        ex, ey, ez = enemy["pos"]
        vx, vy, vz = enemy["vel"]

        # Gun muzzle and approximate enemy center.
        sx, sy, sz = x, y, z + 7.0
        tx, ty, tz = ex, ey, ez + 4.5

        rx = tx - sx
        ry = ty - sy
        rz = tz - sz

        a = vx * vx + vy * vy + vz * vz - speed * speed
        b = 2.0 * (rx * vx + ry * vy + rz * vz)
        c = rx * rx + ry * ry + rz * rz

        intercept_time = None

        if abs(a) < 0.000001:
            if abs(b) > 0.000001:
                t = -c / b
                if t > 0:
                    intercept_time = t
        else:
            discriminant = b * b - 4.0 * a * c

            if discriminant >= 0:
                root = math.sqrt(discriminant)

                t1 = (-b - root) / (2.0 * a)
                t2 = (-b + root) / (2.0 * a)

                valid = [t for t in (t1, t2) if t > 0]

                if valid:
                    intercept_time = min(valid)

        if intercept_time is None:
            return [tx, ty, tz]

        # Limit extrapolation to avoid extreme predictions.
        intercept_time = min(intercept_time, 1.0)

        return [
            tx + vx * intercept_time,
            ty + vy * intercept_time,
            tz + vz * intercept_time
        ]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        goal = obs["zone"]["next_center"]

        act: mf.Action = {"tick": obs["tick"]}

        # Original upgrade behavior.
        if obs["offer"]:
            act["pick"] = 0

        # Original enemy detection.
        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: math.dist(m["pos"], me["pos"])
        )

        # V4 weapon pickup logic.
        near = [
            p for p in obs["pickups"]
            if math.dist(p["pos"][:2], (x, y)) < self.reach
        ]

        if (
            me["weapons"][1] is None
            and near
            and near[0]["kind"] != "gun"
        ):
            act["take"] = near[0]["id"]

        # V4 weapon acquisition.
        if me["weapons"][1] is None and me["in_zone"]:
            available = [
                p for p in obs["pickups"]
                if p["kind"] != "gun"
            ]

            if available:
                closest = min(
                    available,
                    key=lambda p: math.dist(
                        p["pos"][:2], (x, y)
                    )
                )

                loot_distance = math.dist(
                    closest["pos"][:2], (x, y)
                )

                enemy_close = (
                    enemies
                    and math.dist(
                        enemies[0]["pos"][:2], (x, y)
                    ) < 60
                )

                if loot_distance < 35 and not enemy_close:
                    goal = closest["pos"]

        # Original movement.
        yaw = math.atan2(goal[1] - y, goal[0] - x)

        act.update(
            move=[math.cos(yaw), math.sin(yaw)],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0
        )

        # Improved combat aiming.
        if enemies:
            target = enemies[0]
            ex, ey, ez = target["pos"]

            distance = math.dist(
                target["pos"][:2], (x, y)
            )

            # Original direct aim.
            aim_x, aim_y, aim_z = ex, ey, ez + 4.5

            secondary = me["weapons"][1]

            # Prioritize the secondary weapon's direct
            # aim when it has different firing mechanics.
            use_prediction = (
                secondary is None
                or secondary["kind"] == "laser"
            )

            if use_prediction:
                gun = me["weapons"][0]

                speed = self.gun_speed

                if gun is not None and gun["kind"] == "gun":
                    speed = gun["stats"].get(
                        "speed", self.gun_speed
                    )

                aim_x, aim_y, aim_z = self.predict_target(
                    me, target, speed
                )

            aim_yaw = math.atan2(
                aim_y - y, aim_x - x
            )

            aim_pitch = math.atan2(
                aim_z - (z + 7.0),
                math.hypot(aim_x - x, aim_y - y)
            )

            act.update(
                aim=[aim_yaw, aim_pitch],
                fire=[True, True]
            )

            mf.draw.line(
                [x, y, z + 7],
                [aim_x, aim_y, aim_z],
                "#ff5040"
            )

        mf.draw.point(
            [goal[0], goal[1], z],
            "#40c0ff",
            6
        )

        mf.draw.label(
            f"V6 | hp {me['hp']:.0f} | "
            f"{len(enemies)} enemies"
        )

        return act


mf.run(Bot)
