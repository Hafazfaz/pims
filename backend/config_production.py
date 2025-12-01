# Production Configuration for cPanel Deployment
# IMPORTANT: Update these values with your actual cPanel database credentials

# Database Configuration
DB_HOST = 'localhost'  # Usually 'localhost' in cPanel
DB_USER = 'your_cpanel_db_username'  # Replace with actual username
DB_PASSWORD = 'your_cpanel_db_password'  # Replace with actual password
DB_NAME = 'your_cpanel_db_name'  # Replace with actual database name

# Security Keys (ALREADY GENERATED - DO NOT CHANGE)
SECRET_KEY = 'efb0c1f16da143fd664fc9706b6270deea9a'
JWT_SECRET_KEY = 'efb0c1f16da143fd664fc9706b6270deea9a'

# Production Settings
DEBUG = False
TESTING = False
