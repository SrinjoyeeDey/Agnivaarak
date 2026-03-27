"""
logic/angle_mapper.py
======================
Converts fire bounding box coordinates to 2DOF (pan, tilt) angles.
"""

def map_bbox_to_angles(bbox: list, 
                        frame_width: int, 
                        frame_height: int, 
                        base_pan: float = 0.0,
                        horizontal_fov: float = 90.0) -> tuple[float, float]:
    """
    Transforms [x, y, w, h] to absolute (pan, tilt) angles.
    
    Parameters:
        bbox (list): [x, y, w, h] of the fire.
        frame_width (int): Width of the image frame.
        frame_height (int): Height of the image frame.
        base_pan (float): Current horizontal angle of the camera (servo position).
        horizontal_fov (float): Horizontal field of view of the camera lens.
        
    Returns:
        tuple: (pan, tilt) where pan is absolute world angle and tilt is 0-90.
    """
    x, y, w, h = bbox
    cx = x + w / 2
    cy = y + h / 2
    
    # 1. Calculate relative offset from center of frame
    # Offset ranges from -0.5 to +0.5
    offset_x = (cx / frame_width) - 0.5
    
    # 2. Calculate relative angle based on FOV
    relative_pan = offset_x * horizontal_fov
    
    # 3. Calculate absolute world angle
    absolute_pan = base_pan + relative_pan
    
    # Tilt: 0 (top) to 90 (bottom) - still linear as laptop cams don't usually rotate tilt much in demo
    tilt = (cy / frame_height) * 90
    
    return round(absolute_pan, 2), round(tilt, 2)
