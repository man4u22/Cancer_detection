from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime
import os
import numpy as np
from PIL import Image
from werkzeug.utils import secure_filename
from twilio.rest import Client
import tensorflow as tf
from tensorflow.keras.preprocessing import image

# Initialize Flask appp
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# Load the trained model
model = tf.keras.models.load_model('model/model.keras')

# Define constants
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
TWILIO_SID = 'AC******************************'
TWILIO_AUTH_TOKEN = '8a516762e5af5f0c4b4184daf97c304a'
TWILIO_PHONE = '+14782494389'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class_names = ['cancer', 'healthy']

# Database connection
def get_db_connection():
    try:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="WJ28@krhps",
            database="appap"
        )
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return None

# File validation
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Validate if an image is a skin image
def is_skin_image(img_path):
    try:
        img = Image.open(img_path).resize((224, 224))
        img_array = np.array(img)
        avg_color = np.mean(img_array, axis=(0, 1))
        skin_min = np.array([45, 30, 20])
        skin_max = np.array([255, 220, 180])
        return np.all(avg_color >= skin_min) and np.all(avg_color <= skin_max)
    except Exception as e:
        print(f"Error validating image: {e}")
        return False

# Convert time to 24-hour format
def convert_to_24hr_format(time_str):
    try:
        hour = int(time_str.split()[0].split(':')[0])
        period = time_str.split()[1].upper()
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0
        return f"{hour:02}:00:00"
    except Exception as e:
        print(f"Time conversion error: {e}")
        return "00:00:00"

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM admin WHERE username = %s AND password = %s", (username, password))
            admin = cursor.fetchone()
            cursor.close()
            connection.close()
            if admin:
                session['admin'] = admin[0]
                return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid credentials")
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin'))

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM appointments")
        appointments = cursor.fetchall()
        cursor.close()
        connection.close()

        # Format appointment times
        for appointment in appointments:
            appointment['appointment_time'] = appointment['appointment_time'].strftime("%Y-%m-%d %H:%M:%S")

        return render_template('admin_dashboard.html', appointments=appointments)

    flash("Database connection error")
    return redirect(url_for('home'))

@app.route('/filter_appointments', methods=['GET'])
def filter_appointments():
    if 'admin' not in session:
        return redirect(url_for('admin'))

    filter_date = request.args.get('filter_date')
    connection = get_db_connection()

    if connection:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM appointments WHERE DATE(appointment_time) = %s"
        cursor.execute(query, (filter_date,))
        filtered_appointments = cursor.fetchall()
        cursor.close()
        connection.close()

        # Format appointment times
        for appointment in filtered_appointments:
            appointment['appointment_time'] = appointment['appointment_time'].strftime("%Y-%m-%d %H:%M:%S")

        return render_template('admin_dashboard.html', appointments=filtered_appointments)

    flash("Database connection error")
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash("Logged out successfully")
    return redirect(url_for('admin'))

@app.route('/detect_skin_cancer')
def detect_skin_cancer():
    return render_template('detect_skin_cancer.html')

@app.route('/predict', methods=['POST'])
def predict():
    if 'file' not in request.files:
        flash("No file part")
        return redirect(url_for('detect_skin_cancer'))

    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        if not is_skin_image(filepath):
            flash("Invalid image. Please upload a skin image.")
            return redirect(url_for('detect_skin_cancer'))

        image_path = f'uploads/{filename}'
        img = image.load_img(filepath, target_size=(224, 224))
        img_array = image.img_to_array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)

        prediction = model.predict(img_array)
        predicted_class = int(np.round(prediction[0][0]))
        result = class_names[predicted_class]

        return render_template('result.html', result=result, image_path=image_path, show_appointment=(result == 'cancer'))

    flash("Invalid file format")
    return redirect(url_for('detect_skin_cancer'))

@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    time_slots = [
        "9 AM to 10 AM", "10 AM to 11 AM", "11 AM to 12 PM", "12 PM to 1 PM",
        "1 PM to 2 PM", "2 PM to 3 PM", "3 PM to 4 PM", "4 PM to 5 PM",
        "5 PM to 6 PM", "6 PM to 7 PM", "7 PM to 8 PM", "8 PM to 9 PM"
    ]
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        gender = request.form['gender']
        phone = request.form['phone']
        appointment_date = request.form['appointment_date']
        appointment_time = convert_to_24hr_format(request.form['appointment_time'])

        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute(""" 
                INSERT INTO appointments (name, age, gender, phone, appointment_time) 
                VALUES (%s, %s, %s, %s, %s)
            """, (name, age, gender, phone, f"{appointment_date} {appointment_time}"))
            connection.commit()
            cursor.close()
            connection.close()

            try:
                client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=f"Appointment booked for {name}. Date: {appointment_date}, Time: {appointment_time}.",
                    from_=TWILIO_PHONE,
                    to=phone
                )
            except Exception as e:
                print(f"Twilio error: {e}")
                flash("Appointment booked, but failed to send SMS.")
            return render_template('appointment_success.html', name=name, age=age, gender=gender, phone=phone,
                                   appointment_date=appointment_date, appointment_time=appointment_time)
        flash("Database connection error")
    return render_template('book_appointment.html', time_slots=time_slots)

# Add new route for "Treatment"
@app.route('/treatment')
def treatment():
    return render_template('treatment.html')

if __name__ == '__main__':
    app.run(debug=True)
