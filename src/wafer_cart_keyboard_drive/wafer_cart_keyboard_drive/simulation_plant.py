"""Ideal mecanum plant driven by firmware OUTPUT snapshots, not UI key values."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class Pose:
    x: float
    y: float
    yaw: float


class SimulationPlant:
    def __init__(self, model: dict, booth: dict, footprint, *, duty_scale: int):
        if model.get("simulation_only") is not True or model.get("calibration_verified") is not False:
            raise ValueError("가상 모델 설정만 허용합니다")
        if model.get("motor_order") != ["FL", "FR", "RL", "RR"]:
            raise ValueError("firmware simulation wheel order required")
        for name in ("max_wheel_speed_m_s", "wheel_radius_m", "rotation_lever_m", "counts_per_wheel_rev"):
            if not math.isfinite(model[name]) or model[name] <= 0:
                raise ValueError("invalid simulation model: " + name)
        self.model, self.booth, self.footprint = model, booth, footprint
        self.duty_scale = duty_scale
        self.count_fractions = [0.0] * 4
        self.counts = [0] * 4
        self.outputs = [0] * 4
        self.distance = 0.0
        self.collision = None
        self.reset()

    def reset(self):
        self.pose = Pose(*self.booth["home"])
        self.trail = [(self.pose.x, self.pose.y)]
        self.distance = 0.0
        self.collision = None

    def corners(self, pose=None):
        pose = pose or self.pose
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        return [(pose.x+c*x-s*y, pose.y+s*x+c*y) for x, y in self.footprint]

    def collision_at(self, pose):
        corners = self.corners(pose)
        bound = self.booth["half_extent"]
        if any(abs(x) > bound or abs(y) > bound for x, y in corners):
            return "지도 경계"
        for obstacle in self.booth["obstacles"]:
            x, y = obstacle["x"], obstacle["y"]
            a, b = obstacle["width"]/2, obstacle["depth"]/2
            box = [(x-a,y-b),(x+a,y-b),(x+a,y+b),(x-a,y+b)]
            axes = [(1,0),(0,1),(math.cos(pose.yaw),math.sin(pose.yaw)),
                    (-math.sin(pose.yaw),math.cos(pose.yaw))]
            separated = False
            for ax, ay in axes:
                one = [px*ax+py*ay for px,py in corners]
                two = [px*ax+py*ay for px,py in box]
                if max(one) < min(two) or max(two) < min(one):
                    separated = True
                    break
            if not separated:
                return obstacle["name"]
        return None

    def advance(self, outputs, dt: float):
        if len(outputs) != 4 or not math.isfinite(dt) or dt < 0:
            raise ValueError("invalid plant sample")
        self.outputs = list(outputs)
        # No invented catch-up motion after a stalled GUI or a stale sample.
        dt = min(dt, 0.1)
        wheels = [v/self.duty_scale*self.model["max_wheel_speed_m_s"] for v in outputs]
        fl, fr, rl, rr = wheels
        vx = (fl+fr+rl+rr)/4
        vy = (-fl+fr+rl-rr)/4
        yaw_rate = (-fl+fr-rl+rr)/(4*self.model["rotation_lever_m"])
        # Subdivide sweeps to prevent jumping through thin obstacles.
        steps = max(1, math.ceil(dt/0.01))
        step = dt/steps
        for _ in range(steps):
            yaw = self.pose.yaw + yaw_rate*step/2
            candidate = Pose(self.pose.x+(vx*math.cos(yaw)-vy*math.sin(yaw))*step,
                             self.pose.y+(vx*math.sin(yaw)+vy*math.cos(yaw))*step,
                             math.atan2(math.sin(self.pose.yaw+yaw_rate*step),
                                        math.cos(self.pose.yaw+yaw_rate*step)))
            collision = self.collision_at(candidate)
            if collision:
                self.collision = collision
                return False
            self.distance += math.hypot(candidate.x-self.pose.x,candidate.y-self.pose.y)
            self.pose = candidate
        for i, speed in enumerate(wheels):
            self.count_fractions[i] += speed*dt/(2*math.pi*self.model["wheel_radius_m"])*self.model["counts_per_wheel_rev"]
            self.counts[i] = int(self.count_fractions[i])
        if math.hypot(self.pose.x-self.trail[-1][0],self.pose.y-self.trail[-1][1]) > 0.005:
            self.trail.append((self.pose.x,self.pose.y))
            del self.trail[:-2000]
        return True
