
"""Mech Royale V4: original bot with targeted weapon acquisition."""

import math
import mechfight as mf


class Bot:
    name = "loot-v4"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]

        goal = obs["zone"]["next_center"]

        act: mf.Action = {"tick": obs["tick"]}

        # Original upgrade selection.
        if obs["offer"]:
            act["pick"] = 0

        # Original pickup logic.
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

        # Original enemy detection.
        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: math.dist(m["pos"], me["pos"])
        )

        # NEW: Look for nearby weapons when unequipped.
        if me["weapons"][1] is None and me["in_zone"]:
            available = [
                p for p in obs["pickups"]
                if p["kind"] != "gun"
            ]

            if available:
                closest = min(
                    available,
                    key=lambda p: math.dist(p["pos"][:2], (x, y))
                )

                loot_distance = math.dist(
                    closest["pos"][:2],
                    (x, y)
                )

                # Only take short detours when no enemy is close.
                enemy_close = (
                    enemies
                    and math.dist(
                        enemies[0]["pos"][:2],
                        (x, y)
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

        # Original combat.
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
            f"V4 | hp {me['hp']:.0f} | "
            f"{len(enemies)} enemies"
        )

        return act


mf.run(Bot)
