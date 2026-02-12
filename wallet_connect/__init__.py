from .routes import wallet_connect_bp


def init_wallet_connect(app):
    """Register WalletConnect module routes."""
    app.register_blueprint(wallet_connect_bp)
    return True
