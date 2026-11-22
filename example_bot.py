
"""Mech Royale V11: V9 combat/loot + threat-aware navigation and stuck recovery."""

import math
import mechfight as mf


class Bot:
    name = "survival-v11"

    def __init__(self, hello: mf.Hello):
        config = hello["config"]
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
