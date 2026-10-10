import math
import unittest

from wafer_cart_keyboard_drive.simulation_plant import SimulationPlant, Pose


class PlantTest(unittest.TestCase):
    def plant(self):
        model = dict(simulation_only=True, calibration_verified=False,
                     motor_order=['FL','FR','RL','RR'], max_wheel_speed_m_s=1.,
                     wheel_radius_m=.05, rotation_lever_m=.45, counts_per_wheel_rev=1000)
        booth = dict(home=[0.,0.,0.], half_extent=4., obstacles=[
            dict(name='wall',x=1.,y=0.,width=.1,depth=3.)])
        return SimulationPlant(model,booth,[[-.2,-.3],[.2,-.3],[.2,.3],[-.2,.3]],duty_scale=200)

    def test_firmware_mix_reconstructs_three_independent_axes(self):
        for outputs,axis,sign in (([20,20,20,20],'x',1),([-20,20,20,-20],'y',1),
                                  ([-20,20,-20,20],'yaw',1)):
            p=self.plant()
            p.advance(outputs,.1)
            self.assertGreater(getattr(p.pose,axis)*sign,0)
            for other in {'x','y','yaw'}-{axis}:
                self.assertAlmostEqual(getattr(p.pose,other),0)

    def test_motion_comes_from_outputs_and_stops_at_zero(self):
        p=self.plant()
        p.advance([20]*4,.1)
        before=(p.pose.x,p.pose.y,p.pose.yaw)
        p.advance([0]*4,.1)
        self.assertEqual(before,(p.pose.x,p.pose.y,p.pose.yaw))
        self.assertGreater(p.counts[0],0)

    def test_rotated_body_moves_in_world_frame(self):
        p=self.plant()
        p.pose=Pose(0,0,math.pi/2)
        p.advance([20]*4,.1)
        self.assertAlmostEqual(p.pose.x,0)
        self.assertGreater(p.pose.y,0)

    def test_footprint_cannot_pass_through_thin_wall(self):
        p=self.plant()
        for _ in range(50):
            if not p.advance([200]*4,.1):break
        self.assertEqual(p.collision,'wall')
        self.assertLess(p.pose.x,.75)
        self.assertIsNone(p.collision_at(p.pose))

    def test_large_elapsed_gap_does_not_jump_map(self):
        p=self.plant()
        p.advance([20]*4,10.)
        self.assertLessEqual(p.pose.x,.011)

    def test_invalid_model_rejected(self):
        p=self.plant()
        p.model['calibration_verified']=True
        with self.assertRaises(ValueError):
            SimulationPlant(p.model,p.booth,p.footprint,duty_scale=200)
