from pymongo import MongoClient
from uuid import uuid4

# Define your MongoDB connection details here
MONGO_URI = 'mongodb://localhost:27017'  # Update with your MongoDB URI

# Create and configure the MongoDB client
client = MongoClient(MONGO_URI)
db = client['PrioTask']  # Use your MongoDB database

def get_uuid():
    return uuid4().hex

class User:
    def __init__(self, email, password, isOnline):
        self.id = get_uuid()
        self.email = email
        self.password = password
        self.isOnline = isOnline

    def save(self):
        db.users.insert_one({
            'id': self.id,
            'email': self.email,
            'password': self.password,
            'isOnline': self.isOnline
        })

    @staticmethod
    def find_by_email(email):
        return db.users.find_one({'email': email})

    @staticmethod
    def find_by_id(user_id):
        return db.users.find_one({'id': user_id})
