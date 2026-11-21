
"""Mech Royale V1: survival-focused autonomous bot."""

import math
import mechfight as mf


def distance2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 0.001:
        return [0.0, 0.0]
    return [dx / length, dy / length]


class Bot:
    name = "survival-v1"

    def __init__(self, hello: mf.Hello):
        config = hello["config"]
        self.pickup_radius = config["loot"]["pickup_radius"]
        self.cube_radius = config["cubes"]["pickup_radius"]
        self.last_goal = None

    def choose_upgrade(self, offer):
        """Prefer survivability, mobility, and regeneration."""
        priorities = {
            "armor": 100,
            "regen": 95,
            "hp": 90,
            "speed": 85,
            "energy": 75,
            "sensors": 60,
            "gun_rate": 40,
        }

        choices = offer["choices"]
        return max(
            range(len(choices)),
            key=lambda i: priorities.get(choices[i]["id"], 30)
        )

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        pos = me["pos"]
        x, y, z = pos

        hp_ratio = me["hp"] / max(1, me["max_hp"])
        energy_ratio = me["energy"] / max(1, me["max_energy"])

        zone = obs["zone"]
        goal = list(zone["next_center"])

        action: mf.Action = {
            "tick": obs["tick"],
            "move": [0.0, 0.0],
            "boost": False,
            "jump": False,
            "fire": [False, False],
        }

        # 1. Choose an upgrade whenever one is offered.
        if obs["offer"]:
            action["pick"] = self.choose_upgrade(obs["offer"])

        # 2. Identify visible enemy mechs.
        enemies = sorted(
            (m for m in obs["mechs"] if m["kind"] == "mech"),
            key=lambda m: distance2(m["pos"], pos)
        )

        nearest = enemies[0] if enemies else None
        enemy_distance = (
            distance2(nearest["pos"], pos)
            if nearest else float("inf")
        )

        # 3. Pick up nearby weapons.
        if me["weapons"][1] is None:
            for pickup in obs["pickups"]:
                if pickup["kind"] == "gun":
                    continue

                if (
                    distance2(pickup["pos"], pos) <= self.pickup_radius
                    and abs(pickup["pos"][2] - z) <= 4.0
                ):
                    action["take"] = pickup["id"]
                    break

        # 4. Decide whether to retreat.
        low_health = hp_ratio < 0.45
        close_enemy = nearest is not None and enemy_distance < 65

        retreat = low_health and close_enemy

        # 5. Select a movement destination.
        if retreat:
            away = direction(nearest["pos"], pos)

            goal = [
                x + away[0] * 65,
                y + away[1] * 65,
            ]

        elif me["in_zone"]:
            # Collect cubes when they are reasonably nearby.
            cubes = sorted(
                obs["cubes"],
                key=lambda c: distance2(c["pos"], pos)
            )

            if cubes and distance2(cubes[0]["pos"], pos) < 45:
                goal = list(cubes[0]["pos"][:2])

            # Otherwise seek a useful weapon.
            elif me["weapons"][1] is None:
                pickups = sorted(
                    (
                        p for p in obs["pickups"]
                        if p["kind"] != "gun"
                    ),
                    key=lambda p: distance2(p["pos"], pos)
                )

                if pickups and distance2(pickups[0]["pos"], pos) < 75:
                    goal = list(pickups[0]["pos"][:2])

        # 6. Move toward the selected destination.
        move = direction(pos, goal)
        action["move"] = move

        # Boost mainly when outside the zone.
        action["boost"] = (
            not me["in_zone"]
            and energy_ratio > 0.25
        )

        # 7. Aim at the nearest enemy, accounting for motion.
        if nearest:
            target = nearest["pos"]
            velocity = nearest["vel"]

            travel_time = min(enemy_distance / 252.0, 0.9)

            predicted = [
                target[0] + velocity[0] * travel_time,
                target[1] + velocity[1] * travel_time,
                target[2] + velocity[2] * travel_time,
            ]

            dx = predicted[0] - x
            dy = predicted[1] - y
            dz = predicted[2] + 4.5 - (z + 7.0)

            yaw = math.atan2(dy, dx)
            pitch = math.atan2(dz, math.hypot(dx, dy))

            action["aim"] = [yaw, pitch]

            # Avoid unnecessary fights while retreating.
            if not retreat and enemy_distance < 180:
                gun = me["weapons"][0]
                if gun is not None and gun["kind"] == "gun":
                    action["fire"][0] = True

        else:
            # Look toward the movement destination.
            action["aim"] = [
                math.atan2(goal[1] - y, goal[0] - x),
                0.0,
            ]

        # 8. Reload when appropriate.
        gun = me["weapons"][0]
        if gun is not None and gun["kind"] == "gun":
            if gun.get("ammo", 12) <= 3:
                action["reload"] = True

        mf.draw.point(
            [goal[0], goal[1], z],
            "#40c0ff",
            6
        )

        state = "RETREAT" if retreat else "SURVIVE"

        mf.draw.label(
            f"{state} | HP {me['hp']:.0f} | "
            f"Enemies {len(enemies)}"
        )

        return action


mf.run(Bot)
