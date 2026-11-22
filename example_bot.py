
"""Mech Royale V8: V6 with intelligent secondary weapon firing."""

import math
import mechfight as mf


class Bot:
    name = "weapon-smart-v8"

    def __init__(self, hello: mf.Hello):
        config = hello["config"]
        self.reach = config["loot"]["pickup_radius"]
        self.gun_speed = config["weapons"]["gun"].get("speed", 252.0)

        self.laser_charge = config["weapons"]["laser"].get(
            "charge", 0.75
        )
        self.lightning_range = config["weapons"]["lightning"].get(
            "range", 45.0
        )
        self.lightning_cone = math.radians(
            config["weapons"]["lightning"].get("cone_deg", 30.0)
        )

    @staticmethod
    def angle_difference(a, b):
        return (a - b + math.pi) % (2 * math.pi) - math.pi

    def predict_target(self, me, enemy, speed):
        """Predict the position of a moving enemy."""

        x, y, z = me["pos"]
        ex, ey, ez = enemy["pos"]
        vx, vy, vz = enemy["vel"]

        rx = ex - x
        ry = ey - y
        rz = (ez + 4.5) - (z + 7.0)

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

                candidates = [
                    t for t in (
                        (-b - root) / (2.0 * a),
                        (-b + root) / (2.0 * a)
                    )
                    if t > 0
                ]

                if candidates:
                    intercept_time = min(candidates)

        if intercept_time is None:
            intercept_time = 0.0

        intercept_time = min(intercept_time, 1.0)

        return [
            ex + vx * intercept_time,
            ey + vy * intercept_time,
            ez + 4.5 + vz * intercept_time
        ]

    def secondary_fire(self, me, enemies):
        """Choose whether to hold the secondary trigger."""

        secondary = me["weapons"][1]

        if secondary is None:
            return False

        kind = secondary["kind"]

        # LASER: charge fully, then release.
        if kind == "laser":
            if not enemies:
                return False

            if secondary["cooldown"] > 0:
                return False

            charge = secondary.get("charge", 0.0)
            required = secondary["stats"].get(
                "charge", self.laser_charge
            )

            # Releasing fires the charged laser.
            return charge < required

        # LIGHTNING: only fire with a nearby target
        # inside the effective aiming cone.
        if kind == "lightning":
            if not enemies:
                return False

            x, y, _ = me["pos"]
            current_yaw = me["aim"][0]

            weapon_range = secondary["stats"].get(
                "range", self.lightning_range
            )
            cone = math.radians(
                secondary["stats"].get(
                    "cone_deg",
                    math.degrees(self.lightning_cone)
                )
            )

            for enemy in enemies:
                ex, ey, _ = enemy["pos"]

                distance = math.hypot(ex - x, ey - y)

                if distance > weapon_range:
                    continue

                enemy_yaw = math.atan2(ey - y, ex - x)

                if abs(self.angle_difference(
                    enemy_yaw, current_yaw
                )) <= cone / 2:
                    return True

            return False

        # MORTAR: preserve V6 behavior for this test.
        if kind == "mortar":
            return bool(enemies)

        return False

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]

        goal = obs["zone"]["next_center"]

        act: mf.Action = {"tick": obs["tick"]}

        # V6 upgrade selection.
        if obs["offer"]:
            act["pick"] = 0

        # V6 pickup behavior.
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

        # V6 enemy detection.
        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: math.dist(m["pos"], me["pos"])
        )

        # V6 weapon acquisition.
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

        # V6 movement.
        yaw = math.atan2(goal[1] - y, goal[0] - x)

        act.update(
            move=[math.cos(yaw), math.sin(yaw)],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0
        )

        if enemies:
            target = enemies[0]
            ex, ey, ez = target["pos"]

            aim_x, aim_y, aim_z = ex, ey, ez + 4.5

            secondary = me["weapons"][1]

            # Preserve V6's predictive aiming selection.
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

            fire_secondary = self.secondary_fire(
                me, enemies
            )

            act.update(
                aim=[aim_yaw, aim_pitch],
                fire=[True, fire_secondary]
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

        secondary = me["weapons"][1]
        weapon_name = (
            secondary["kind"] if secondary else "none"
        )

        mf.draw.label(
            f"V8 | HP {me['hp']:.0f} | "
            f"Weapon {weapon_name}"
        )

        return act


mf.run(Bot)
