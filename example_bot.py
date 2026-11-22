
"""Mech Royale V5: smarter loot and upgrade choices."""

import math
import mechfight as mf


class Bot:
    name = "smart-loot-v5"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]

    def choose_upgrade(self, offer):
        choices = offer["choices"]

        def score(choice):
            text = (
                choice["id"] + " " +
                choice["name"] + " " +
                choice["desc"]
            ).lower()

            priorities = [
                (("regenerat", "repair", "healing"), 100),
                (("armor", "shield", "resist"), 95),
                (("max hp", "health", "hit point"), 90),
                (("speed", "mobility", "sprint"), 85),
                (("energy", "boost"), 80),
                (("damage", "fire rate", "cooldown"), 65),
                (("range", "accuracy"), 55),
            ]

            best = 30
            for keywords, value in priorities:
                if any(word in text for word in keywords):
                    best = max(best, value)

            return best

        return max(range(len(choices)), key=lambda i: score(choices[i]))

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        goal = obs["zone"]["next_center"]

        act: mf.Action = {"tick": obs["tick"]}

        # Improved upgrade selection.
        if obs["offer"] and obs["offer"]["choices"]:
            act["pick"] = self.choose_upgrade(obs["offer"])

        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: math.dist(m["pos"], me["pos"])
        )

        enemy_distance = (
            math.dist(enemies[0]["pos"][:2], (x, y))
            if enemies else float("inf")
        )

        # Equipment priorities are experimental.
        weapon_priority = {
            "laser": 0,
            "lightning": 1,
            "mortar": 2,
        }

        # Keep seeking equipment until slot 1 is filled.
        if me["weapons"][1] is None:
            available = [
                p for p in obs["pickups"]
                if p["kind"] != "gun"
            ]

            # Prefer nearby equipment, with a small
            # adjustment for weapon type.
            available.sort(
                key=lambda p: (
                    math.dist(p["pos"][:2], (x, y))
                    + weapon_priority.get(p["kind"], 3) * 4
                )
            )

            # Take any eligible nearby weapon.
            in_reach = [
                p for p in available
                if math.dist(p["pos"][:2], (x, y)) < self.reach
            ]

            if in_reach:
                act["take"] = in_reach[0]["id"]

            # V4-inspired weapon detours.
            if me["in_zone"] and available:
                closest = available[0]
                loot_distance = math.dist(
                    closest["pos"][:2], (x, y)
                )

                if enemy_distance > 75:
                    max_detour = 50
                elif enemy_distance > 60:
                    max_detour = 35
                else:
                    max_detour = 0

                if loot_distance < max_detour:
                    goal = closest["pos"]

        # Preserve original movement.
        yaw = math.atan2(goal[1] - y, goal[0] - x)

        act.update(
            move=[math.cos(yaw), math.sin(yaw)],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0
        )

        # Preserve original combat.
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
            f"V5 | HP {me['hp']:.0f} | "
            f"Enemies {len(enemies)}"
        )

        return act


mf.run(Bot)
