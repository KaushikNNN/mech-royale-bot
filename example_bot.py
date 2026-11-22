
"""Mech Royale V15: V12 plus placement-focused zone positioning."""

import math
import json
import os
import mechfight as mf


class Bot:
    name = "zone-survival-v15"

    def __init__(self, hello: mf.Hello):
        config = hello["config"]
        self.obstacles = {}
        self._load_map(hello)
        self.reach = config["loot"]["pickup_radius"]
        self.cube_reach = config["cubes"].get(
            "pickup_radius", 3.5
        )
        self.gun_speed = config["weapons"]["gun"].get(
            "speed", 252.0
        )
        self.laser_charge = config["weapons"]["laser"].get(
            "charge", 0.75
        )
        self.lightning_range = config["weapons"]["lightning"].get(
            "range", 45.0
        )
        self.last_position = None
        self.last_check_tick = 0
        self.unstuck_until = 0
        self.unstuck_side = 1
        self.lightning_cone = math.radians(
            config["weapons"]["lightning"].get(
                "cone_deg", 30.0
            )
        )

    def _load_map(self, hello):
        """Map data is optional: keep working if files are not mounted."""
        root = hello.get("map", {}).get("dir", "/arena")
        paths = [os.path.join(root, "v2", "world.json"),
                 os.path.join(root, "world.json"),
                 "arena/v2/world.json", "arena/world.json"]
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    world = json.load(f)
                break
            except (OSError, ValueError):
                continue
        else:
            return
        for prism in world.get("prisms", []):
            ring = prism.get("ring", [])
            if len(ring) < 6:
                continue
            # Bridges above the mech can be passed beneath; retain
            # only solids whose vertical span overlaps ground travel.
            base = prism.get("base", 0)
            top = prism.get("top", 0)
            if top - base < 1:
                continue
            coords = list(zip(ring[::2], ring[1::2]))
            xs, ys = zip(*coords)
            box = (min(xs), min(ys), max(xs), max(ys), coords, base, top)
            ix0, ix1 = int(min(xs) // 40), int(max(xs) // 40)
            iy0, iy1 = int(min(ys) // 40), int(max(ys) // 40)
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    self.obstacles.setdefault((ix, iy), []).append(box)

    @staticmethod
    def _inside_poly(x, y, points):
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            if (yi > y) != (yj > y):
                if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
            j = i
        return inside

    def _blocked(self, x, y, z):
        # Mech radius is 2.5m; keep 3.5m clearance.
        nearby = self.obstacles.get((int(x // 40), int(y // 40)), ())
        for left, bottom, right, top, points, base, roof in nearby:
            if z + 2 > roof or z + 8 < base:
                continue
            if x < left - 3.5 or x > right + 3.5 or y < bottom - 3.5 or y > top + 3.5:
                continue
            if self._inside_poly(x, y, points):
                return True
            for i, (ax, ay) in enumerate(points):
                bx, by = points[(i + 1) % len(points)]
                vx, vy = bx - ax, by - ay
                denom = vx * vx + vy * vy
                t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / denom)) if denom else 0.0
                if (x - ax - t * vx) ** 2 + (y - ay - t * vy) ** 2 < 3.5 ** 2:
                    return True
        return False

    def _map_steer(self, me, desired, goal, enemies, zone):
        if not self.obstacles:
            return desired
        x, y, z = me["pos"]
        base = math.atan2(desired[1], desired[0])
        # Evaluate several headings and short lookahead positions.
        offsets = [0, -0.35, 0.35, -0.7, 0.7, -1.1, 1.1, -1.55, 1.55, 3.14]
        best_score, best_vec = -1e12, desired
        for offset in offsets:
            a = base + offset
            dx, dy = math.cos(a), math.sin(a)
            if any(self._blocked(x + dx * step, y + dy * step, z)
                   for step in (5, 10, 17)):
                continue
            nx, ny = x + dx * 17, y + dy * 17
            if math.hypot(nx - zone["center"][0], ny - zone["center"][1]) > zone["radius"] - 5:
                continue
            danger = sum(max(0, 70 - math.hypot(nx - e["pos"][0], ny - e["pos"][1])) / 70
                         for e in enemies)
            score = 2.5 * (dx * desired[0] + dy * desired[1]) - 0.55 * danger
            score -= 0.25 * abs(offset)
            if score > best_score:
                best_score, best_vec = score, (dx, dy)
        return best_vec

    def survival_zone_goal(self, me, enemies, zone):
        """Choose a conservative point within the next safe zone, not its center.

        Keep a meaningful safety buffer. Only reposition when the current
        location is too close to the next boundary or visible enemies.
        """
        x, y = me["pos"][:2]
        cx, cy = zone["next_center"]
        radius = zone["next_radius"]
        # Small endgame zones need a smaller safety buffer.
        buffer = min(24.0, max(5.0, radius * 0.18))
        safe_radius = max(0.0, radius - buffer)
        current_dist = math.hypot(x - cx, y - cy)
        nearest = min((math.hypot(x-e["pos"][0], y-e["pos"][1])
                       for e in enemies), default=1e6)
        # Avoid unnecessary trips to the center when already safe.
        if current_dist <= safe_radius and nearest > 65.0:
            return (x, y)

        # Candidate points spread through the safe area, including the center.
        candidates = [(cx, cy)]
        for fraction in (0.48, 0.82):
            r = safe_radius * fraction
            for i in range(12):
                a = (2 * math.pi * i / 12)
                candidates.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        best = (cx, cy)
        best_score = -1e20
        for px, py in candidates:
            travel = math.hypot(px-x, py-y)
            # Distance is costly: avoid traversing the map to escape a
            # hypothetical threat; visible enemies are the only evidence.
            score = -0.035 * travel
            for enemy in enemies:
                d = math.hypot(px-enemy["pos"][0], py-enemy["pos"][1])
                score -= 2.0 * max(0.0, 80.0-d) / 80.0
            # Keep a little extra space from the shrinking edge.
            score -= 0.12 * (math.hypot(px-cx, py-cy) / max(radius, 1.0))
            if score > best_score:
                best_score, best = score, (px, py)
        return best

    def movement_direction(self, me, goal, enemies, zone, tick):
        """Steer toward goal while avoiding nearby mechs and recovering from stalls."""
        x, y = me["pos"][:2]
        gx, gy = goal[:2]
        dx, dy = gx - x, gy - y
        d = math.hypot(dx, dy)
        if d > 1.0:
            dx, dy = dx / d, dy / d
        else:
            dx, dy = 0.0, 0.0

        # Retreat from nearby enemies. This changes only movement, not combat.
        # Capped contributions prevent huge forces when an enemy overlaps us.
        threat_count = 0
        for enemy in enemies:
            ex, ey = enemy["pos"][:2]
            vx, vy = x - ex, y - ey
            distance = math.hypot(vx, vy)
            if distance >= 85.0:
                continue
            threat_count += 1
            strength = min(2.4, (85.0 - distance) / 45.0)
            if distance > 0.001:
                dx += strength * vx / distance
                dy += strength * vy / distance

        # Don't retreat out of the playable zone. When outside, head inward.
        zx, zy = zone["center"][:2]
        inward_x, inward_y = zx - x, zy - y
        center_distance = math.hypot(inward_x, inward_y)
        margin = zone["radius"] - center_distance
        if center_distance > 0.001:
            if margin < 35.0:
                inward_weight = 4.0 if margin < 8.0 else 1.5
                dx += inward_weight * inward_x / center_distance
                dy += inward_weight * inward_y / center_distance

        # Also anticipate the next zone when near its boundary.
        nx, ny = zone["next_center"][:2]
        nd = math.hypot(nx - x, ny - y)
        if nd > 0.001 and nd > zone["next_radius"] - 22.0:
            dx += 0.85 * (nx - x) / nd
            dy += 0.85 * (ny - y) / nd

        # Persistent stalled position: sidestep for a short interval.
        if self.last_position is not None and tick > self.last_check_tick:
            elapsed = tick - self.last_check_tick
            if elapsed >= 15:
                traveled = math.hypot(x - self.last_position[0], y - self.last_position[1])
                if traveled < 1.5 and d > 8.0:
                    self.unstuck_until = tick + 22
                    self.unstuck_side *= -1
                self.last_position = (x, y)
                self.last_check_tick = tick
        if self.last_position is None:
            self.last_position = (x, y)
            self.last_check_tick = tick

        magnitude = math.hypot(dx, dy)
        if magnitude < 0.001:
            dx, dy = 1.0, 0.0
        else:
            dx, dy = dx / magnitude, dy / magnitude

        if tick < self.unstuck_until and margin > 12.0:
            dx, dy = -dy * self.unstuck_side, dx * self.unstuck_side

        return dx, dy, threat_count

    @staticmethod
    def distance(a, b):
        return math.hypot(
            a[0] - b[0], a[1] - b[1]
        )

    @staticmethod
    def angle_difference(a, b):
        return (a - b + math.pi) % (
            2 * math.pi
        ) - math.pi

    def predict_target(self, me, enemy, speed):
        x, y, z = me["pos"]
        ex, ey, ez = enemy["pos"]
        vx, vy, vz = enemy["vel"]

        rx = ex - x
        ry = ey - y
        rz = ez + 4.5 - (z + 7.0)

        a = (
            vx * vx + vy * vy + vz * vz
            - speed * speed
        )
        b = 2.0 * (
            rx * vx + ry * vy + rz * vz
        )
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
                    value
                    for value in (
                        (-b - root) / (2 * a),
                        (-b + root) / (2 * a)
                    )
                    if value > 0
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

        if weapon is None:
            return False

        kind = weapon["kind"]

        if kind == "laser":
            if not enemies:
                return False

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

                enemy_yaw = math.atan2(
                    ey - y, ex - x
                )

                if abs(self.angle_difference(
                    enemy_yaw, current_yaw
                )) <= cone / 2:
                    return True

            return False

        if kind == "mortar":
            return bool(enemies)

        return False

    def is_safe_destination(
        self, position, zone, enemies, min_enemy_distance
    ):
        # Keep destinations within the current zone
        # and within the next zone when practical.
        if self.distance(
            position, zone["center"]
        ) > zone["radius"] - 8:
            return False

        if self.distance(
            position, zone["next_center"]
        ) > zone["next_radius"] - 8:
            return False

        for enemy in enemies:
            if self.distance(
                position, enemy["pos"]
            ) < min_enemy_distance:
                return False

        return True

    def find_cube_goal(self, obs, enemies):
        me = obs["self"]
        position = me["pos"]
        zone = obs["zone"]

        # Do not chase cubes while outside the zone.
        if not me["in_zone"]:
            return None

        # Prefer collecting cubes before reaching
        # the default 10-cube stat cap.
        config_cap = 10
        if me["cubes"] >= config_cap:
            return None

        candidates = []

        for cube in obs["cubes"]:
            distance = self.distance(
                position, cube["pos"]
            )

            if distance > 28:
                continue

            if abs(
                cube["pos"][2] - position[2]
            ) > 5:
                continue

            if not self.is_safe_destination(
                cube["pos"], zone, enemies, 30
            ):
                continue

            candidates.append(
                (distance, cube["pos"], "cube")
            )

        # Supply drops are valuable but risky.
        # Only approach close, landed drops.
        for drop in obs["drops"]:
            if drop["lands_in"] > 0:
                continue

            if (
                drop["holder"] is not None
                and drop["holder"] != me["id"]
            ):
                continue

            distance = self.distance(
                position, drop["pos"]
            )

            if distance > 35:
                continue

            if abs(
                drop["pos"][2] - position[2]
            ) > 5:
                continue

            if not self.is_safe_destination(
                drop["pos"], zone, enemies, 45
            ):
                continue

            # Reward drops for providing cubes
            # and restoring HP and energy.
            value_bonus = 8.0

            if me["hp"] < me["max_hp"] * 0.65:
                value_bonus += 8.0

            candidates.append(
                (
                    max(0.0, distance - value_bonus),
                    drop["pos"],
                    "drop"
                )
            )

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][2]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]

        goal = obs["zone"]["next_center"]
        goal_type = "zone"

        act: mf.Action = {"tick": obs["tick"]}

        # V8 upgrades.
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

        # V8 pickup behavior.
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

        # V8 weapon acquisition.
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

        # NEW: Collect cubes and nearby supply drops.
        # Do not interrupt weapon acquisition.
        if goal_type == "zone":
            cube_goal = self.find_cube_goal(
                obs, enemies
            )

            if cube_goal is not None:
                goal, goal_type = cube_goal

        if goal_type == "zone":
            goal = self.survival_zone_goal(me, enemies, obs["zone"])

        move_x, move_y, threat_count = self.movement_direction(
            me, goal, enemies, obs["zone"], obs["tick"]
        )
        move_x, move_y = self._map_steer(
            me, (move_x, move_y), goal, enemies, obs["zone"]
        )
        yaw = math.atan2(move_y, move_x)

        act.update(
            move=[move_x, move_y],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0 or obs["tick"] < self.unstuck_until
        )

        # Preserve V8 combat.
        if enemies:
            target = enemies[0]
            ex, ey, ez = target["pos"]

            aim_x, aim_y, aim_z = (
                ex, ey, ez + 4.5
            )

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
                aim_y - y, aim_x - x
            )

            aim_pitch = math.atan2(
                aim_z - (z + 7.0),
                math.hypot(
                    aim_x - x, aim_y - y
                )
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

        mf.draw.label(
            f"V15 | HP {me['hp']:.0f} | "
            f"Cubes {me['cubes']} | {goal_type}"
        )

        return act


mf.run(Bot)
