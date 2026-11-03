"""Independent implementation of the three-parameter model in Li et al. (2015).

This benchmark uses human-marked head/foot points, not YOLO boxes or LLM output.
The calibration person's height is never used as a held-out test person's truth.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Camera:
    focal_px:float
    tilt_radians:float
    camera_height_cm:float
    image_height:int=720


def head_from_foot(foot_y,height_cm,camera):
    f=camera.focal_px;c=camera.camera_height_cm;t=math.tan(camera.tilt_radians)
    y=camera.image_height/2-foot_y
    denominator=t*y*height_cm+f*(t*t*height_cm-c*t*t-c)
    if abs(denominator)<1e-8:raise ValueError('Degenerate camera geometry')
    up=(f*(-c*t*t+height_cm-c)*y+f*f*t*height_cm)/denominator
    return camera.image_height/2-up


def estimate_height(head_y,foot_y,camera):
    if not all(math.isfinite(v) for v in (head_y,foot_y)) or not 0<=head_y<foot_y<=camera.image_height:
        raise ValueError('Invalid visible head/foot pair')
    f=camera.focal_px;c=camera.camera_height_cm;t=math.tan(camera.tilt_radians)
    yh=camera.image_height/2-head_y;yf=camera.image_height/2-foot_y
    denominator=t*yf*yh-f*yf+f*t*t*yh-f*f*t
    if abs(denominator)<1e-8:raise ValueError('Degenerate camera geometry')
    result=-f*c*(1+t*t)*(yf-yh)/denominator
    if not math.isfinite(result) or result<=0:raise ValueError('Nonphysical stature estimate')
    return result


def calibrate(points,image_height=720):
    """points: calibration-only (head_y, foot_y, known_height_cm)."""
    import numpy as np
    from scipy.optimize import least_squares
    if len(points)<5:raise ValueError('At least five calibration observations are required')
    if any(not 0<=head<foot<=image_height or not 50<=height<=250 for head,foot,height in points):
        raise ValueError('Invalid calibration observation')
    if max(p[1] for p in points)-min(p[1] for p in points)<30:raise ValueError('Calibration must span depth positions')
    heights={p[2] for p in points}
    if len(heights)!=1:raise ValueError('Use only one known reference person for this benchmark')
    def residual(parameters):
        camera=Camera(*parameters,image_height=image_height)
        return np.array([head_from_foot(foot,height,camera)-head for head,foot,height in points])
    fitted=least_squares(residual,[720,-.5,300],bounds=([100,-1.45,80],[5000,.0,1000]),max_nfev=4000,
                         ftol=1e-10,xtol=1e-10,gtol=1e-10)
    if not fitted.success:raise ValueError('Calibration did not converge')
    return Camera(*map(float,fitted.x),image_height=image_height),float(np.sqrt(np.mean(fitted.fun**2)))
