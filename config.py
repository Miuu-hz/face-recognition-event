"""
Configuration Management for Face Recognition Event System

This module handles all configuration settings using environment variables
for security and flexibility across different deployment environments.

Environment Variables:
    SECRET_KEY: Flask secret key for session encryption
    DATABASE_URL: Database connection string (SQLite or PostgreSQL)
    FLASK_ENV: Application environment (development/production)
    GOOGLE_CLIENT_SECRETS: Path to Google OAuth credentials file
    MAX_CONTENT_LENGTH: Maximum upload file size in bytes
    FACE_TOLERANCE: Face recognition tolerance (0.0-1.0)
    FACE_MODEL: Face recognition model ('hog' or 'cnn')
    BATCH_SIZE: Number of images to process per batch
"""

import os
import secrets
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ConfigError(Exception):
    """Raised when configuration validation fails"""
    pass


class Config:
    """Base configuration class"""

    # Flask Settings
    SECRET_KEY: str = os.getenv('SECRET_KEY', secrets.token_hex(32))
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'

    # Server Settings
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '10000'))

    # Database Settings
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///database.db')
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'database.db')

    # Google OAuth Settings
    GOOGLE_CLIENT_SECRETS: str = os.getenv(
        'GOOGLE_CLIENT_SECRETS',
        'client_secrets.json'
    )
    OAUTHLIB_INSECURE_TRANSPORT: str = os.getenv(
        'OAUTHLIB_INSECURE_TRANSPORT',
        '1'  # Allow HTTP for local development
    )

    # Upload Settings
    MAX_CONTENT_LENGTH: int = int(os.getenv(
        'MAX_CONTENT_LENGTH',
        str(16 * 1024 * 1024)  # 16MB default
    ))
    ALLOWED_EXTENSIONS: set = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_SELFIE_UPLOADS: int = int(os.getenv('MAX_SELFIE_UPLOADS', '3'))

    # Face Recognition Settings
    FACE_TOLERANCE: float = float(os.getenv('FACE_TOLERANCE', '0.5'))
    FACE_MODEL: str = os.getenv('FACE_MODEL', 'auto')  # 'auto', 'hog', or 'cnn'
    BATCH_SIZE: int = int(os.getenv('BATCH_SIZE', '20'))
    NUM_JITTERS: int = int(os.getenv('NUM_JITTERS', '1'))

    # Static Files
    STATIC_FOLDER: str = 'static'
    QR_CODE_FOLDER: str = os.path.join(STATIC_FOLDER, 'qr')

    # Logging Settings
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'app.log')
    LOG_MAX_BYTES: int = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))

    @classmethod
    def validate(cls) -> None:
        """
        Validate critical configuration settings

        Raises:
            ConfigError: If validation fails
        """
        errors = []

        # Validate SECRET_KEY in production
        if cls.FLASK_ENV == 'production':
            if cls.SECRET_KEY == secrets.token_hex(32) or len(cls.SECRET_KEY) < 32:
                errors.append(
                    "SECRET_KEY must be set in production environment "
                    "(min 32 characters)"
                )

        # Validate Google OAuth credentials file
        if not os.path.exists(cls.GOOGLE_CLIENT_SECRETS):
            errors.append(
                f"Google OAuth credentials file not found: "
                f"{cls.GOOGLE_CLIENT_SECRETS}. "
                f"Please download from Google Cloud Console."
            )

        # Validate Face Recognition settings
        if not 0.0 <= cls.FACE_TOLERANCE <= 1.0:
            errors.append(
                f"FACE_TOLERANCE must be between 0.0 and 1.0, "
                f"got {cls.FACE_TOLERANCE}"
            )

        if cls.FACE_MODEL not in ['auto', 'hog', 'cnn']:
            errors.append(
                f"FACE_MODEL must be 'auto', 'hog', or 'cnn', "
                f"got {cls.FACE_MODEL}"
            )

        if cls.BATCH_SIZE < 1:
            errors.append(f"BATCH_SIZE must be >= 1, got {cls.BATCH_SIZE}")

        # Raise exception if any errors
        if errors:
            raise ConfigError(
                "Configuration validation failed:\n" +
                "\n".join(f"  - {error}" for error in errors)
            )

    @classmethod
    def display(cls) -> None:
        """Display current configuration (without secrets)"""
        print("\n" + "="*60)
        print("Application Configuration")
        print("="*60)
        print(f"Environment:           {cls.FLASK_ENV}")
        print(f"Debug Mode:            {cls.DEBUG}")
        print(f"Host:Port:             {cls.HOST}:{cls.PORT}")
        print(f"Database:              {cls.DATABASE_PATH}")
        print(f"Max Upload Size:       {cls.MAX_CONTENT_LENGTH / (1024*1024):.1f} MB")
        print(f"Max Selfie Uploads:    {cls.MAX_SELFIE_UPLOADS}")
        print(f"\nFace Recognition:")
        print(f"  Model:               {cls.FACE_MODEL}")
        print(f"  Tolerance:           {cls.FACE_TOLERANCE}")
        print(f"  Batch Size:          {cls.BATCH_SIZE}")
        print(f"  Num Jitters:         {cls.NUM_JITTERS}")
        print(f"\nLogging:")
        print(f"  Level:               {cls.LOG_LEVEL}")
        print(f"  File:                {cls.LOG_FILE}")
        print("="*60 + "\n")

    @classmethod
    def init_app(cls, app) -> None:
        """
        Initialize Flask app with configuration

        Args:
            app: Flask application instance
        """
        # Validate configuration first
        cls.validate()

        # Set Flask config
        app.config['SECRET_KEY'] = cls.SECRET_KEY
        app.config['MAX_CONTENT_LENGTH'] = cls.MAX_CONTENT_LENGTH
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        # Set environment variables
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = cls.OAUTHLIB_INSECURE_TRANSPORT

        # Create necessary directories
        os.makedirs(cls.QR_CODE_FOLDER, exist_ok=True)

        # Display configuration
        if cls.DEBUG or cls.FLASK_ENV == 'development':
            cls.display()


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    FLASK_ENV = 'development'


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    FLASK_ENV = 'production'

    @classmethod
    def validate(cls) -> None:
        """Additional production validations"""
        super().validate()

        # Ensure SECRET_KEY is explicitly set in production
        if not os.getenv('SECRET_KEY'):
            raise ConfigError(
                "SECRET_KEY environment variable must be explicitly set "
                "in production"
            )


class TestingConfig(Config):
    """Testing environment configuration"""
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ':memory:'  # Use in-memory database for tests


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env: Optional[str] = None) -> type[Config]:
    """
    Get configuration class based on environment

    Args:
        env: Environment name ('development', 'production', 'testing')
             If None, uses FLASK_ENV environment variable

    Returns:
        Configuration class
    """
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    return config.get(env, config['default'])
