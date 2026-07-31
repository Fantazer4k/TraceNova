"""
Color constants for the application
"""

COLORS = {
    "bg_primary": "#0B0B0F",
    "bg_secondary": "#17171C",
    "bg_card": "#202026",
    "accent_primary": "#E6007A",
    "accent_secondary": "#00E676",
    "text": "#FFFFFF",
    "text_secondary": "#B5B5C3",
    "border": "#2A2A31",
}

def get_color(name: str) -> str:
    """Get color by name"""
    return COLORS.get(name, "#FFFFFF")
