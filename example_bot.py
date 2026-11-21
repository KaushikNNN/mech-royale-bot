"""Example bot: walk to the zone, grab a weapon, shoot the nearest mech, draw what it's thinking."""
import math
import mechfight as mf


class Bot:
    name = "movementv2-py"

    def __init__(self, hello: mf.Hello):
        self.reach = hello["config"]["loot"]["pickup_radius"]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        goal = obs["zone"]["next_center"]
        act: mf.Action = {"tick": obs["tick"]}
        if obs["offer"]:
            act["pick"] = 0
        near = [p for p in obs["pickups"] if math.dist(p["pos"][:2], (x, y)) < self.reach]
        if me["weapons"][1] is None and near and near[0]["kind"] != "gun":
            act["take"] = near[0]["id"]
        enemies = sorted((m for m in obs["mechs"] if m["kind"] == "mech"), key=lambda m: math.dist(m["pos"], me["pos"]))
        # Default: move toward the next safe-zone center.
        move_x = goal[0] - x
        move_y = goal[1] - y

        # When safely inside the zone, try to maintain distance
        # from nearby enemies without changing combat behavior.
        if me["in_zone"] and enemies:
            closest = enemies[0]
            ex, ey = closest["pos"][:2]

            dx = x - ex
            dy = y - ey
            distance = math.hypot(dx, dy)

            if 0.001 < distance < 45:
                move_x += (dx / distance) * 35
                move_y += (dy / distance) * 35

        length = math.hypot(move_x, move_y)

        if length > 0.001:
            move_x /= length
            move_y /= length
        else:
            move_x = 0.0
            move_y = 0.0

        yaw = math.atan2(goal[1] - y, goal[0] - x)

        act.update(
            move=[move_x, move_y],
            aim=[yaw, 0.0],
            boost=not me["in_zone"],
            jump=obs["tick"] % 40 == 0
        )
        if enemies:
            t = enemies[0]["pos"]
            aim = [math.atan2(t[1] - y, t[0] - x), math.atan2(t[2] - z - 2.5, math.dist(t[:2], (x, y)))]
            act.update(aim=aim, fire=[True, True])
            mf.draw.line([x, y, z + 7], [t[0], t[1], t[2] + 4.5], "#ff5040")
        mf.draw.point([goal[0], goal[1], z], "#40c0ff", 6)
        mf.draw.label(f"hp {me['hp']:.0f} · {len(enemies)} in sight")
        return act


mf.run(Bot)
