
"""Mech Royale V10: V9 with emergency retreat and regeneration."""

import math
import mechfight as mf


class Bot:
    name = "survival-v10"

    def __init__(self, hello: mf.Hello):
        config = hello["config"]
        self.reach = config["loot"]["pickup_radius"]
        self.gun_speed = config["weapons"]["gun"].get("speed", 252.0)
        self.laser_charge = config["weapons"]["laser"].get("charge", 0.75)
        self.lightning_range = config["weapons"]["lightning"].get(
            "range", 45.0
        )
        self.lightning_cone = math.radians(
            config["weapons"]["lightning"].get("cone_deg", 30.0)
        )

        self.retreating = False
        self.last_combat_time = -100.0

    @staticmethod
    def distance(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def normalize(x, y):
        length = math.hypot(x, y)
        if length < 0.00001:
            return [0.0, 0.0]
        return [x / length, y / length]

    @staticmethod
    def angle_difference(a, b):
        return (a - b + math.pi) % (2 * math.pi) - math.pi

    def predict_target(self, me, enemy, speed):
        x, y, z = me["pos"]
        ex, ey, ez = enemy["pos"]
        vx, vy, vz = enemy["vel"]

        rx = ex - x
        ry = ey - y
        rz = ez + 4.5 - (z + 7.0)

        a = vx * vx + vy * vy + vz * vz - speed * speed
        b = 2.0 * (rx * vx + ry * vy + rz * vz)
        c = rx * rx + ry * ry + rz * rz

        t = 0.0

        if abs(a) < 0.000001:
            if abs(b) > 0.000001:
                candidate = -c / b
                if candidate > 0:
                    t = candidate
        else:
            discriminant = b * b - 4 * a * c
            if discriminant >= 0:
                root = math.sqrt(discriminant)
                candidates = [
                    value for value in (
                        (-b - root) / (2 * a),
                        (-b + root) / (2 * a)
                    ) if value > 0
                ]
                if candidates:
                    t = min(candidates)

        t = min(t, 1.0)

        return [
            ex + vx * t,
            ey + vy * t,
            ez + 4.5 + vz * t
        ]

    def secondary_fire(self, me, enemies):
        weapon = me["weapons"][1]

        if weapon is None or not enemies:
            return False

        kind = weapon["kind"]

        if kind == "laser":
            if weapon["cooldown"] > 0:
                return False

            required = weapon["stats"].get(
                "charge", self.laser_charge
            )
            return weapon.get("charge", 0.0) < required

        if kind == "lightning":
            x, y, _ = me["pos"]
            current_yaw = me["aim"][0]

            weapon_range = weapon["stats"].get(
                "range", self.lightning_range
            )
            cone = math.radians(
                weapon["stats"].get(
                    "cone_deg",
                    math.degrees(self.lightning_cone)
                )
            )

            for enemy in enemies:
                ex, ey, _ = enemy["pos"]

                if self.distance((x, y), (ex, ey)) > weapon_range:
                    continue

                enemy_yaw = math.atan2(ey - y, ex - x)

                if abs(self.angle_difference(
                    enemy_yaw, current_yaw
                )) <= cone / 2:
                    return True

            return False

        if kind == "mortar":
            return True

        return False

    def safe_destination(self, pos, zone, enemies, minimum):
        if self.distance(
            pos, zone["center"]
        ) > zone["radius"] - 8:
            return False

        if self.distance(
            pos, zone["next_center"]
        ) > zone["next_radius"] - 8:
            return False

        for enemy in enemies:
            if self.distance(pos, enemy["pos"]) < minimum:
                return False

        return True

    def find_cube_goal(self, obs, enemies):
        me = obs["self"]
        pos = me["pos"]
        zone = obs["zone"]

        if not me["in_zone"] or me["cubes"] >= 10:
            return None

        candidates = []

        for cube in obs["cubes"]:
            d = self.distance(pos, cube["pos"])

            if d > 28:
                continue

            if abs(cube["pos"][2] - pos[2]) > 5:
                continue

            if not self.safe_destination(
                cube["pos"], zone, enemies, 30
            ):
                continue

            candidates.append((d, cube["pos"], "cube"))

        for drop in obs["drops"]:
            if drop["lands_in"] > 0:
                continue

            if (
                drop["holder"] is not None
                and drop["holder"] != me["id"]
            ):
                continue

            d = self.distance(pos, drop["pos"])

            if d > 35:
                continue

            if abs(drop["pos"][2] - pos[2]) > 5:
                continue

            if not self.safe_destination(
                drop["pos"], zone, enemies, 45
            ):
                continue

            bonus = 8.0

            if me["hp"] < me["max_hp"] * 0.65:
                bonus += 8.0

            candidates.append(
                (max(0.0, d - bonus), drop["pos"], "drop")
            )

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][2]

    def retreat_direction(self, me, enemies, zone):
        """Move away from nearby enemies while respecting the zone."""

        x, y, _ = me["pos"]

        ax, ay = 0.0, 0.0

        for enemy in enemies:
            ex, ey, _ = enemy["pos"]
            dx, dy = x - ex, y - ey
            distance = math.hypot(dx, dy)

            if distance < 0.1 or distance > 110:
                continue

            # Nearby enemies exert stronger repulsion.
            weight = (110 - distance) / 110
            weight = weight * weight

            ax += (dx / distance) * weight
            ay += (dy / distance) * weight

        cx, cy = zone["next_center"]
        radius = zone["next_radius"]

        distance_to_next = self.distance(
            (x, y), (cx, cy)
        )

        # Strongly favor moving inward near the next boundary.
        if distance_to_next > radius - 35:
            inward = self.normalize(cx - x, cy - y)
            ax += inward[0] * 2.5
            ay += inward[1] * 2.5

        # Also avoid leaving the current zone.
        current_cx, current_cy = zone["center"]
        current_radius = zone["radius"]

        if self.distance(
            (x, y), (current_cx, current_cy)
        ) > current_radius - 30:
            inward = self.normalize(
                current_cx - x, current_cy - y
            )
            ax += inward[0] * 3.0
            ay += inward[1] * 3.0

        if abs(ax) + abs(ay) < 0.0001:
            # No visible threat: hold position to regenerate.
            return [0.0, 0.0]

        direction = self.normalize(ax, ay)

        # Check that the next few meters remain inside
        # the current zone.
        future = [
            x + direction[0] * 12,
            y + direction[1] * 12
        ]

        if self.distance(
            future, (current_cx, current_cy)
        ) > current_radius - 5:
            direction = self.normalize(
                current_cx - x,
                current_cy - y
            )

        return direction

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        now = obs["t"]
        zone = obs["zone"]

        act: mf.Action = {"tick": obs["tick"]}

        if obs["offer"]:
            act["pick"] = 0

        enemies = sorted(
            (
                m for m in obs["mechs"]
                if m["kind"] == "mech"
            ),
            key=lambda m: math.dist(
                m["pos"], me["pos"]
            )
        )

        # Track recent combat to estimate regeneration timing.
        for event in obs["events"]:
            if event["type"] in ("damaged", "hit"):
                self.last_combat_time = now

        hp_ratio = me["hp"] / max(me["max_hp"], 1)

        # Enter retreat below 40% HP.
        if hp_ratio < 0.40:
            self.retreating = True

        # Leave retreat after recovering to 80% HP.
        if hp_ratio >= 0.80:
            self.retreating = False

        # Do not continue hiding when the zone is damaging us.
        # Instead prioritize moving back inside.
        if self.retreating:
            movement = self.retreat_direction(
                me, enemies, zone
            )

            # When outside the current zone, prioritize
            # the center over enemy avoidance.
            if not me["in_zone"]:
                movement = self.normalize(
                    zone["center"][0] - x,
                    zone["center"][1] - y
                )

            nearest_distance = (
                self.distance(
                    me["pos"], enemies[0]["pos"]
                ) if enemies else float("inf")
            )

            boost = (
                me["energy"] > 25
                and me["grounded"]
                and nearest_distance < 65
                and math.hypot(*movement) > 0.1
            )

            # Face the nearest enemy to reduce rear damage,
            # even when moving in the opposite direction.
            if enemies:
                target = enemies[0]["pos"]
                aim_yaw = math.atan2(
                    target[1] - y,
                    target[0] - x
                )
            else:
                aim_yaw = me["aim"][0]

            act.update(
                move=movement,
                aim=[aim_yaw, 0.0],
                boost=boost,
                jump=(
                    me["grounded"]
                    and nearest_distance < 45
                    and obs["tick"] % 40 == 0
                ),
                fire=[False, False]
            )

            mf.draw.label(
                f"V10 RETREAT | HP {me['hp']:.0f}"
            )
            return act

        # Normal behavior: V9.
        goal = zone["next_center"]
        goal_type = "zone"

        near = [
            p for p in obs["pickups"]
            if self.distance(
                p["pos"], (x, y)
            ) < self.reach
        ]

        if (
            me["weapons"][1] is None
            and near
            and near[0]["kind"] != "gun"
        ):
            act["take"] = near[0]["id"]

        if me["weapons"][1] is None and me["in_zone"]:
            available = [
                p for p in obs["pickups"]
                if p["kind"] != "gun"
            ]

            if available:
                closest = min(
                    available,
                    key=lambda p: self.distance(
                        p["pos"], (x, y)
                    )
                )

                loot_distance = self.distance(
                    closest["pos"], (x, y)
                )

                enemy_close = (
                    enemies
                    and self.distance(
                        enemies[0]["pos"], (x, y)
                    ) < 60
                )

                if loot_distance < 35 and not enemy_close:
                    goal = closest["pos"]
                    goal_type = "weapon"

        if goal_type == "zone":
            cube_goal = self.find_cube_goal(
                obs, enemies
            )

            if cube_goal is not None:
                goal, goal_type = cube_goal

        yaw = math.atan2(
            goal[1] - y,
            goal[0] - x
        )

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
                aim_y - y,
                aim_x - x
            )

            aim_pitch = math.atan2(
                aim_z - (z + 7.0),
                math.hypot(
                    aim_x - x,
                    aim_y - y
                )
            )

            act.update(
                aim=[aim_yaw, aim_pitch],
                fire=[
                    True,
                    self.secondary_fire(me, enemies)
                ]
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
            f"V10 | HP {me['hp']:.0f} | "
            f"Cubes {me['cubes']} | {goal_type}"
        )

        return act


mf.run(Bot)
