from app.services.movement.geometry import angle_at, relative_depth, torso_inclination_deg


def test_right_angle():
    a = {"x": 0.0, "y": 0.0}
    b = {"x": 0.0, "y": 1.0}
    c = {"x": 1.0, "y": 1.0}
    assert abs(angle_at(a, b, c) - 90.0) < 1e-6


def test_straight_knee():
    hip = {"x": 0.5, "y": 0.3}
    knee = {"x": 0.5, "y": 0.5}
    ankle = {"x": 0.5, "y": 0.8}
    assert abs(angle_at(hip, knee, ankle) - 180.0) < 1e-6


def test_upright_torso_near_zero():
    shoulder = {"x": 0.4, "y": 0.2}
    hip = {"x": 0.4, "y": 0.5}
    assert torso_inclination_deg(shoulder, hip) < 1.0


def test_relative_depth_bounds():
    assert relative_depth(0.4, 0.4, 0.8) == 0.0
    assert abs(relative_depth(0.8, 0.4, 0.8) - 1.0) < 1e-6
    assert relative_depth(0.9, 0.4, 0.8) <= 1.4
