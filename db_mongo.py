from pymongo import MongoClient
import os

# Configure your MongoDB connection here (adjust URI if needed)
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

db = client['community_db']
users_col = db['users']
issues_col = db['issues']
votes_col = db['votes']
help_col = db['help_requests']
notifications_col = db['notifications']
devices_col = db['devices']

# Indexes can be created here if desired
# Example: users_col.create_index('mobile', unique=True)
