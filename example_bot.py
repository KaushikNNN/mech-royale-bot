
"""Mech Royale V3: multi-threat avoidance and zone survival."""

import math
import mechfight as mf


class Bot:
    name = "tactical-v3"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        goal = obs["zone"]["next_center"]

        act: mf.Action = {"tick": obs["tick"]}

        # Keep the starter's upgrade selection.
        if obs["offer"]:
            act["pick"] = 0

        # Pick up nearby weapons.
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

        # Identify visible enemies.
        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: math.dist(m["pos"], me["pos"])
        )

        # Zone direction.
        gx = goal[0] - x
        gy = goal[1] - y
        gd = math.hypot(gx, gy)

        if gd > 0.001:
            gx /= gd
            gy /= gd
        else:
            gx = 0.0
            gy = 0.0

        # Multi-enemy avoidance.
        avoid_x = 0.0
        avoid_y = 0.0

        for enemy in enemies:
            ex, ey = enemy["pos"][:2]

            dx = x - ex
            dy = y - ey
            dist = math.hypot(dx, dy)

            if 0.001 < dist < 90:
                strength = (90 - dist) / 90
                strength = strength * strength

                avoid_x += (dx / dist) * strength
                avoid_y += (dy / dist) * strength

        # Limit avoidance strength.
        avoid_length = math.hypot(avoid_x, avoid_y)

        if avoid_length > 1:
            avoid_x /= avoid_length
            avoid_y /= avoid_length

        # Zone safety takes priority when outside.
        if me["in_zone"]:
            zone_weight = 0.65
            avoid_weight = 1.5
        else:
            zone_weight = 2.5
            avoid_weight = 0.4

        move_x = gx * zone_weight + avoid_x * avoid_weight
        move_y = gy * zone_weight + avoid_y * avoid_weight

        length = math.hypot(move_x, move_y)

        if length > 0.001:
            move_x /= length
            move_y /= length
        else:
            move_x = gx
            move_y = gy

        yaw = math.atan2(goal[1] - y, goal[0] - x)

        act.update(
            move=[move_x, move_y],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0
        )

        # Preserve original combat behavior.
        if enemies:
            t = enemies[0]["pos"]

            aim = [
                math.atan2(t[1] - y, t[0] - x),
                math.atan2(
                    t[2] - z - 2.5,
                    math.dist(t[:2], (x, y))
                )
            ]

            act.update(
                aim=aim,
                fire=[True, True]
            )

            mf.draw.line(
                [x, y, z + 7],
                [t[0], t[1], t[2] + 4.5],
                "#ff5040"
            )

        mf.draw.point(
            [goal[0], goal[1], z],
            "#40c0ff",
            6
        )

        mf.draw.label(
            f"V3 | hp {me['hp']:.0f} | "
            f"{len(enemies)} enemies"
        )

        return act


mf.run(Bot)
