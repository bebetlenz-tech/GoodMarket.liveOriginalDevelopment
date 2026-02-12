
from .minigames_manager import minigames_manager
from .routes import minigames_bp
from .garden_routes import garden_bp
from .blockchain import minigames_blockchain

def init_minigames(app):
    """Initialize minigames system"""
    try:
        # Register blueprints
        app.register_blueprint(minigames_bp)
        app.register_blueprint(garden_bp)
        
        return True
    except Exception as e:
        print(f"❌ Minigames initialization failed: {e}")
        return False

__all__ = ['minigames_manager', 'minigames_bp', 'garden_bp', 'minigames_blockchain', 'init_minigames']
