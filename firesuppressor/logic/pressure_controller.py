"""
logic/pressure_controller.py
=============================
Maps fire intensity and type to suppression pressure and agent.
"""

class PressureController:
    # Agent Mapping (Requirement Phase 17)
    AGENT_MAP = {
        "a" : "WATER",      # Class A: Solids
        "b" : "FOAM/CO2",   # Class B: Bio-Gas/Liquids
        "c" : "CO2/DRY",    # Class C: Electrical
        "d" : "SPECIAL_DRY" # Class D: Metal
    }
    
    # Pressure Mapping
    PRESSURE_MAP = {
        "LOW"      : "LOW",
        "MEDIUM"   : "MEDIUM",
        "HIGH"     : "HIGH",
        "CRITICAL" : "MAX"
    }

    @staticmethod
    def get_suppression_config(fire_type: str, intensity_level: str) -> dict:
        """
        Returns pressure, agent, and recommended mode.
        """
        # Normalize fire_type to single char key (e.g. "(B)" -> "b")
        raw_type = fire_type or "a"
        key = raw_type.strip("()").lower()[0]
        agent    = PressureController.AGENT_MAP.get(key, "WATER")
        pressure = PressureController.PRESSURE_MAP.get(intensity_level, "MEDIUM")
        
        # Mode logic: industrial precision (Requirement Phase 17)
        mode = "DIRECT"
        if key == "c":
            mode = "PRECISE"
        elif key == "b":
            mode = "SURROUND"
        elif key == "d":
            mode = "RAIN" # Gentle application for metal fires to avoid splashing
            
        return {
            "pressure" : pressure,
            "agent"    : agent,
            "mode"     : mode
        }
