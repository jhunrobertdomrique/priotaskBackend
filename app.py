from bson.objectid import ObjectId
from datetime import timedelta, datetime
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, redirect
from flask_bcrypt import Bcrypt
from flask_cors import CORS, cross_origin
# from models import db, User
from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient
import re

#imports sending notifications
import os
import smtplib
import random
from email.message import EmailMessage
from email.utils import formataddr
from dotenv import load_dotenv
import schedule
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cabanatuan-thesis'
# client = MongoClient('mongodb://localhost:27017')
client = MongoClient('mongodb+srv://admin:admin123@batch253-domrique.wk1bqpw.mongodb.net/')
db = client['PrioTask'] #1 db name
users_collection = db['users']
bcrypt = Bcrypt(app)
CORS(app, supports_credentials=True)

def load_dataset_from_csv():
    X_train = []
    y_train = []
    with open('tasks_dataset.csv', 'r') as file:
        file.readline() 
        for line in file:
            difficulty, deadline, duration, priority = line.strip().split(',')
            X_train.append([int(difficulty), int(duration), int(deadline)])
            y_train.append(priority)
    return X_train, y_train

def calculate_prior_probabilities(y_train):
    # Calculate the prior probabilities for each class (priority level)
    total_samples = len(y_train)
    unique_classes = set(y_train)
    prior_probs = {}
    for class_label in unique_classes:
        class_count = y_train.count(class_label)
        prior_probs[class_label] = class_count / total_samples
    return prior_probs

def calculate_likelihood_probabilities(X_train, y_train):
    # Calculate the likelihood probabilities for each feature value and class
    num_features = len(X_train[0])
    likelihood_probs = {}
    for feature_idx in range(num_features):
        feature_values = set(x[feature_idx] for x in X_train)
        for feature_value in feature_values:
            likelihood_probs[(feature_idx, feature_value)] = {}
            for class_label in set(y_train):
                feature_class_count = sum(1 for i, label in enumerate(y_train) if label == class_label and X_train[i][feature_idx] == feature_value)
                class_count = y_train.count(class_label)
                likelihood_probs[(feature_idx, feature_value)][class_label] = (feature_class_count + 1) / (class_count + len(feature_values))
    return likelihood_probs

def predict_priority(X_train, y_train, new_task):
    prior_probs = calculate_prior_probabilities(y_train)
    likelihood_probs = calculate_likelihood_probabilities(X_train, y_train)

    predicted_probs = {}
    for class_label in prior_probs:
        class_prob = prior_probs[class_label]
        for feature_idx, feature_value in enumerate(new_task):
            if (feature_idx, feature_value) in likelihood_probs:  # Check if key exists in the dictionary
                feature_class_prob = likelihood_probs[(feature_idx, feature_value)][class_label]
                class_prob *= feature_class_prob
        predicted_probs[class_label] = class_prob

    # Get the predicted priority with the highest probability
    predicted_priority = max(predicted_probs, key=predicted_probs.get)
    return predicted_priority

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/signup", methods=["POST"])
def signup():
    email = request.json["email"]
    password = request.json["password"]
    user_exists = users_collection.find_one({"email": email}) is not None

    if user_exists:
        return jsonify({"error": "Email already exists"}), 409

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = {
        "email": email,
        "password": hashed_password,
        "isOnline": False
    }
    users_collection.insert_one(new_user)

    return jsonify({
        "email": new_user["email"]
    })

@app.route("/login", methods=["POST"])
def login_user():
    email = request.json["email"]
    password = request.json["password"]
    user = users_collection.find_one({"email": email})

    if user is None:
        return jsonify({"error": "Unauthorized Access"}), 401

    if not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"error": "Unauthorized"}), 401
    
    users_collection.update_one({"_id": user["_id"]}, {"$set": {"isOnline": True}})

    session['user_email'] = email

    return jsonify({
        "email": user["email"],
        "isOnline": True
    })

def logout():
    # Get the current host and port from the request object
    host = request.host
    port = request.port

    # Construct the dynamic URL
    dynamic_url = f"http://{host}:{port}/"

    return redirect(dynamic_url)

@app.route("/logout_users", methods=["GET"])
def logout_users():
    result = users_collection.update_many({"isOnline": True}, {"$set": {"isOnline": False}})
    logged_out_users = list(users_collection.find({"isOnline": False}))
    online_user_list = [{"email": user["email"], "isOnline": False} for user in logged_out_users]
    response_data = {
        "message": f"{result.modified_count} user(s) logged out successfully",
        "logged_out_users": online_user_list
    }
    return redirect(url_for("login"))

@app.route("/online_users", methods=["GET"])
def get_online_users():
    online_users = users_collection.find({"isOnline": True})
    online_user_list = []
    for user in online_users:
        online_user_list.append({
            "email": user["email"],
            "isOnline": user["isOnline"]
        })
    return jsonify(online_user_list)

@app.route('/tasks', methods=['POST', 'GET'])
def data():
    if request.method == 'POST':
        X_train, y_train = load_dataset_from_csv()
        body = request.json
        taskName = body['taskName']
        difficulty = body['difficulty']
        deadline = body['deadline']
        timeNeeded = body['timeNeeded']
        isActive = body['isActive']
        isTodo = body['isTodo']
        isProgress = body['isProgress']
        isFinished = body['isFinished']
        isCompleted = body['isCompleted']
        dateStarted = body['dateStarted']
        archived = body['archived']
        timeSpent = body['timeSpent']
        userEmail = body['userEmail']
        try:
            selected_deadline = datetime.strptime(deadline, '%Y-%m-%d').date()
            today = datetime.today().date() 
            days_diff = (selected_deadline - today).days
            if days_diff < 0:
                return render_template('error.html', message="Invalid deadline date. Deadline has already passed.")
      
        except ValueError:
            return render_template('error.html', message="Invalid date format. Please use YYYY-MM-DD.")

        new_task = [difficulty, days_diff, timeNeeded]
        prediction = predict_priority(X_train, y_train, new_task)
        
        matches = re.search(r'Level (\d+)', prediction)

        if matches:
            priority_level = int(matches.group(1))
        else:
            return render_template('error.html', message="Invalid predicted priority format.")

        if  1 <= priority_level <= 20:  # Low priority
            days_after_creation_1 = 29 - (priority_level - 1)
            days_after_creation_2 = 20 - (priority_level - 1)
        elif priority_level == 21:  # Medium priority
            days_after_creation_1 = 9 
            days_after_creation_2 = 5     
        elif priority_level == 22:  # Medium priority
            days_after_creation_1 = 8 
            days_after_creation_2 = 4     
        elif priority_level == 23:  # Medium priority
            days_after_creation_1 = 7 
            days_after_creation_2 = 4 
        elif priority_level == 24:  # Medium priority
            days_after_creation_1 = 6 
            days_after_creation_2 = 4         
        elif priority_level == 25:  # Medium priority
            days_after_creation_1 = 5 
            days_after_creation_2 = 4 
        elif priority_level == 26:  # Medium priority
            days_after_creation_1 = 4 
            days_after_creation_2 = 3 
        elif priority_level == 27:  # Medium priority
            days_after_creation_1 = 4 
            days_after_creation_2 = 3      
        elif priority_level == 28:  # High priority
            days_after_creation_1 = 2
            days_after_creation_2 = 1
        elif priority_level == 29:  # High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 1
        elif priority_level == 30:  # High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 0
        elif priority_level == 31:  # Extremely High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 0
        # 🚩🟩
        
        def send_email(subject, userEmail, message_template, name_placeholder='Recipient Name'):
            load_dotenv()
            email_address = os.getenv('EMAIL')
            email_password = os.getenv('PASSWORD')

            msg = EmailMessage()

            msg['From'] = formataddr(('PrioTask', email_address))
            msg['To'] = userEmail
            msg['Subject'] = subject
            message = message_template.format(name=name_placeholder)
            msg.set_content(message, subtype='html')

            smtp_server = 'smtp.gmail.com'
            smtp_port = 587

            try:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()  # Enable TLS encryption
                server.login(email_address, email_password)  # Log in to your email account
                server.send_message(msg)  # Send the email
                server.quit()  # Quit the server

                print("Email sent successfully!")

            except Exception as e:
                print(f"Error: {e}")
        def send_delayed_email(subject, userEmail, message_template, name_placeholder='Recipient Name'):
                # Delay the email by 45 minutes
                time.sleep(2700)
                subject = f"PrioTask due: {taskName}"
   
                message = message_template.format(
                    taskName=name_placeholder,
                    deadline=datetime.today().strftime('%Y-%m-%d')
                )
               
                # Send the email
                send_email(subject, userEmail, message)
        def send_email_at_deadline(subject, userEmail, message_template, deadline_date, name_placeholder='Recipient Name'):
            # Calculate the time difference between today and the deadline
            today = datetime.today().date()
            days_until_deadline = (deadline_date - today).days

            # Schedule the email to be sent on the day before the deadline
            if days_until_deadline == 1:  # Send the email one day before the deadline
                msg_thread = threading.Thread(target=send_email, args=(subject, userEmail, message_template, name_placeholder))
                msg_thread.start()

            elif days_until_deadline == 0:  # Send the email after 10 seconds
                delayed_thread = threading.Thread(target=send_delayed_email, args=(subject, userEmail, message_template, name_placeholder))
                delayed_thread.start()
            
        

        subject = f"PrioTask due: {taskName}"

        message_templates = [
            f"""
            <html>
            <body>
                <p>Hey there, partner!</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br>
                Check it now! You've got this! Your hard work always shines through. Finish strong!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>
            """,

            f"""
            <html>
            <body>
                <p>What's up, pal?</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br> 
                Check it now! Just a friendly reminder that our deadline is approaching. Keep up the great work, and let's finish strong!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>

            """,

        f"""
            <html>
            <body>
                <p>Howdy, head honcho!</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br> 
                Check it now! I want to express my confidence in your abilities. Your commitment and diligence are unmatched. Finish strong and make us proud!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>

        """
        ,

            f"""
            <html>
            <body>
                <p>Hey, buddy!</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br> 
                Check it now! Your dedication and hard work are truly impressive. Let's give our best to meet the deadline!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>

            """,

            f"""
            <html>
            <body>
                <p>Sup, champ?</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br> 
                Check it now! I want to remind you of your incredible capability. Keep going, and let's deliver outstanding results together!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>

            """,
            f"""
            <html>
            <body>
                <p>Yo, dude!</p>
                <p>Your task "{taskName}" in PrioTask is going to end soon (deadline: {deadline}).<br><br> 
                Check it now! Let's bring this task to a successful conclusion. I believe in your abilities!</p>
                <p>Virtually Yours,</p>
                <p><strong>PrioTask</strong></p>
            </body>
            </html>
            """,
        ]

        random_message_template = random.choice(message_templates)
        # 🚩🚫
        days_after_creation_1 = days_after_creation_1
        days_after_creation_2 = days_after_creation_2

        recommendation_part1 = (datetime.today() + timedelta(days=days_after_creation_1)).strftime('%Y-%m-%d')
        recommendation_part2 = (datetime.today() + timedelta(days=days_after_creation_2)).strftime('%Y-%m-%d')

        selected_deadline = datetime.strptime(deadline, '%Y-%m-%d').date()

        send_email_at_deadline(subject, userEmail, random_message_template, name_placeholder='Recipient Name', deadline_date=selected_deadline)

        db['tasks'].insert_one({
            "taskName": taskName,
            "difficulty" : difficulty,
            "deadline" :deadline,
            "timeNeeded" :timeNeeded,
            "isActive" :isActive,
            "prediction" :prediction,
            "recommendation_part1":recommendation_part1,
            "recommendation_part2":recommendation_part2,
            "isTodo":isTodo,
            "isProgress":isProgress,
            "isFinished":isFinished,
            "isCompleted":isCompleted,
            "dateStarted":dateStarted,
            "archived":archived,
            "timeSpent":timeSpent,
            "userEmail":userEmail
        })

        return jsonify({
            "status" : "Task is posted to MongoDB",
            "taskName": taskName,
            "difficulty" : difficulty,
            "deadline" :deadline,
            "timeNeeded" :timeNeeded,
            "isActive" :isActive,
            "prediction" :prediction,
            "recommendation_part1":recommendation_part1,
            "recommendation_part2":recommendation_part2,
            "isTodo":isTodo,
            "isProgress":isProgress,
            "isFinished":isFinished,
            "isCompleted":isCompleted,
            "dateStarted":dateStarted,
            "archived":archived,
            "timeSpent":timeSpent,
            "userEmail":userEmail
        })

    if request.method == 'GET':
        allData = db['tasks'].find()
        dataJson = []
        for data in allData:
            id = data['_id']
            taskName = data['taskName']
            difficulty = data['difficulty']
            deadline = data['deadline']
            timeNeeded = data['timeNeeded']
            isActive = data['isActive']
            prediction = data['prediction']
            recommendation_part1 = data['recommendation_part1']
            recommendation_part2 = data['recommendation_part2'] 
            isTodo = data['isTodo']
            isProgress = data['isProgress']
            isFinished = data['isFinished']
            isCompleted = data['isCompleted']
            dateStarted = data['dateStarted']
            archived = data['archived']
            timeSpent = data['timeSpent']
            userEmail = data['userEmail']

            dataDict = {
                "id" : str(id),
                "taskName" : taskName,
                "difficulty" : difficulty,
                "deadline" :deadline,
                "timeNeeded" :timeNeeded,
                "isActive" :isActive,
                "prediction" :prediction,
                "recommendation_part1" :recommendation_part1,
                "recommendation_part2" :recommendation_part2,
                "isTodo" :isTodo,
                "isProgress":isProgress,
                "isFinished":isFinished,
                "isCompleted":isCompleted,
                "dateStarted":dateStarted,
                "archived":archived,
                "timeSpent":timeSpent,
                "userEmail":userEmail,
            }
            dataJson.append(dataDict)
        return jsonify(dataJson)

@app.route('/tasks/<string:id>', methods=['GET','PUT','DELETE'])
def onedata(id):
    if request.method == 'GET':
        data = db['tasks'].find_one({"_id":ObjectId(id)})
        id = data['_id']
        taskName = data['taskName']
        difficulty = data['difficulty']
        deadline = data['deadline']
        timeNeeded = data['timeNeeded']
        isActive = data['isActive']
        prediction = data['prediction']
        recommendation_part1 = data['recommendation_part1']
        recommendation_part2 = data['recommendation_part2']
        isTodo = data['isTodo']
        isProgress = data['isProgress']
        isFinished = data['isFinished']
        isCompleted = data['isCompleted']
        dateStarted = data['dateStarted']
        archived = data['archived']
        timeSpent = data['timeSpent']
        userEmail = data['userEmail']

        dataDict = {
                "id" : str(id),
                "taskName" : taskName,
                "difficulty" : difficulty,
                "deadline" :deadline,
                "timeNeeded" :timeNeeded,
                "isActive" :isActive,
                "prediction" :prediction,
                "recommendation_part1" :recommendation_part1,
                "recommendation_part2" :recommendation_part2,
                "isTodo" :isTodo,
                "isProgress":isProgress,
                "isFinished":isFinished,
                "isCompleted":isCompleted,
                "dateStarted":dateStarted,
                "archived":archived,
                "timeSpent":timeSpent,
                "userEmail":userEmail,
            }
        return jsonify(dataDict)
    
    if request.method == 'DELETE':
        data = db['tasks'].find_one({"_id":ObjectId(id)})
        name = data['taskName']
        db['tasks'].delete_many({"_id":ObjectId(id)})
        return jsonify({
            "status" : "Data id:" + id + ", " + (name) + " " + "is deleted."
        })

    # if request.method == 'DELETE':
    #     data = db['tasks'].find_one({"_id": ObjectId(id)})
    #     if data:
    #         name = data['taskName']
         
    #         db['tasks'].update_one({"_id": ObjectId(id)}, {"$set": {"archived": True}})
    #         return jsonify({
    #             "status": "Data id:" + id + ", " + name + " is archived."
    #         })
    #     else:
    #         return jsonify({"status": "Record not found."}), 404

    if request.method == 'PUT':
        X_train, y_train = load_dataset_from_csv()
        body = request.json
        taskName = body['taskName']
        difficulty = body['difficulty']
        deadline = body['deadline']
        timeNeeded = body['timeNeeded']
        isActive = body['isActive']
        prediction = body['prediction']
        recommendation_part1 = body['recommendation_part1']
        recommendation_part2 = body['recommendation_part2']
        
        try:
            selected_deadline = datetime.strptime(deadline, '%Y-%m-%d').date()
            today = datetime.today().date() 
            days_diff = (selected_deadline - today).days
            if days_diff < 0:
                return render_template('error.html', message="Invalid deadline date. Deadline has already passed.")
            
        except ValueError:
            return render_template('error.html', message="Invalid date format. Please use YYYY-MM-DD.")

        new_task = [difficulty, days_diff, timeNeeded]
        prediction = predict_priority(X_train, y_train, new_task)
        
        matches = re.search(r'Level (\d+)', prediction)
        if matches:
            priority_level = int(matches.group(1))
        else:
            return render_template('error.html', message="Invalid predicted priority format.")

        if  1 <= priority_level <= 20:  # Low priority
            days_after_creation_1 = 29 - (priority_level - 1)
            days_after_creation_2 = 20 - (priority_level - 1)
        elif priority_level == 21:  # Medium priority
            days_after_creation_1 = 9 
            days_after_creation_2 = 5     
        elif priority_level == 22:  # Medium priority
            days_after_creation_1 = 8 
            days_after_creation_2 = 4     
        elif priority_level == 23:  # Medium priority
            days_after_creation_1 = 7 
            days_after_creation_2 = 4 
        elif priority_level == 24:  # Medium priority
            days_after_creation_1 = 6 
            days_after_creation_2 = 4         
        elif priority_level == 25:  # Medium priority
            days_after_creation_1 = 5 
            days_after_creation_2 = 4 
        elif priority_level == 26:  # Medium priority
            days_after_creation_1 = 4 
            days_after_creation_2 = 3 
        elif priority_level == 27:  # Medium priority
            days_after_creation_1 = 4 
            days_after_creation_2 = 3      
        elif priority_level == 28:  # High priority
            days_after_creation_1 = 2
            days_after_creation_2 = 1
        elif priority_level == 29:  # High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 1
        elif priority_level == 30:  # High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 0
        elif priority_level == 31:  # Extremely High priority
            days_after_creation_1 = 0
            days_after_creation_2 = 0
       
        days_after_creation_1 = days_after_creation_1
        days_after_creation_2 = days_after_creation_2

        recommendation_part1 = (datetime.today() + timedelta(days=days_after_creation_1)).strftime('%Y-%m-%d')
        recommendation_part2 = (datetime.today() + timedelta(days=days_after_creation_2)).strftime('%Y-%m-%d')
        

        result = db['tasks'].update_one(
            {'_id': ObjectId(id)},
            {
                "$set": {
                    "taskName": taskName,
                    "difficulty": difficulty,
                    "deadline": deadline,
                    "timeNeeded": timeNeeded,
                    "isActive" :isActive,
                    "prediction" :prediction,
                    "recommendation_part1" :recommendation_part1,
                    "recommendation_part2" :recommendation_part2
                
                }
            }
        )
        if result.modified_count > 0:
            return jsonify({"status": "Task updated successfully."})
        else:
            return jsonify({"status": "No task updated."})


@app.route('/tasks/stack/<string:id>', methods=['GET','PUT','DELETE'])
def stackData(id):
    if request.method == 'PUT':
        body = request.json
        isActive = body['isActive']
        isTodo = body['isTodo']
     
        result = db['tasks'].update_one(
            {'_id': ObjectId(id)},
            {
                "$set": {
                    "isActive" :isActive,
                    "isTodo" :isTodo
                }
            }
        )
        if result.modified_count > 0:
            return jsonify({"status": "Task updated successfully."})
        else:
            return jsonify({"status": "No task updated."})

@app.route('/tasks/isTodo/<string:id>', methods=['PUT'])
def todoData(id):
    if request.method == 'PUT':
        body = request.json
        isTodo = body['isTodo']
        isProgress = body['isProgress']
        dateStarted = body['dateStarted']
     
        result = db['tasks'].update_one(
            {'_id': ObjectId(id)},
            {
                "$set": {
                    "isTodo" :isTodo,
                    "isProgress" :isProgress,
                    "dateStarted" :dateStarted
                }
            }
        )
        if result.modified_count > 0:
            return jsonify({"status": "Task updated successfully."})
        else:
            return jsonify({"status": "No task updated."})

@app.route('/tasks/isProgress/<string:id>', methods=['PUT'])
def progressData(id):
    if request.method == 'PUT':
        body = request.json
        isProgress = body['isProgress']
        isCompleted = body['isCompleted']
        isFinished = body['isFinished']
        timeSpent = body['timeSpent']

       
     
        result = db['tasks'].update_one(
            {'_id': ObjectId(id)},
            {
                "$set": {
                    "isProgress" :isProgress,
                    "isCompleted" :isCompleted,
                    "isFinished" :isFinished,
                    "timeSpent" :timeSpent
                }
            }
        )
        if result.modified_count > 0:
            return jsonify({"status": "Task updated successfully."})
        else:
            return jsonify({"status": "No task updated."})
        


if __name__ == '__main__':
    app.debug = True
    app.run()