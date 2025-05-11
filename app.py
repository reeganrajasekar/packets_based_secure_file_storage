import os
import base64
import sqlite3
import uuid
import smtplib
import random
import numpy as np
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'supersecretkey'

DB_NAME = 'database.db'

def guess_mime_type(filename):
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    # viewer History
    c.execute('''
        CREATE TABLE IF NOT EXISTS views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            user_id INTEGER,
            file_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Files table
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            filename TEXT,
            pin TEXT,
            segment_number INTEGER,
            data TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- SMTP CONFIG ------------------
SMTP_EMAIL = "stephenrajprime@gmail.com"
SMTP_PASSWORD = "gbcq ravy huqx raod"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
# -----------------------------------------------

def send_otp_email(receiver_email, otp_code):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "Your OTP for file access"
        body = f"Your OTP is: {otp_code}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Email sending failed:", e)
        return False

def generate_otp():
    return str(random.randint(100000, 999999))

# --- Helper Functions ---
def get_user(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()
    return user

def save_file_segments(user_id, filename, file_data, pin):
    file_id = str(uuid.uuid4())
    segment_size = 512  # bytes
    total_segments = (len(file_data) + segment_size - 1) // segment_size

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for i in range(total_segments):
        segment = file_data[i*segment_size:(i+1)*segment_size]
        encoded_segment = base64.b64encode(segment).decode('utf-8')
        c.execute('''
            INSERT INTO files (user_id, file_id, filename, pin, segment_number, data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, file_id, filename, pin, i, encoded_segment))
    conn.commit()
    conn.close()

    return file_id

def get_file_segments(file_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT segment_number, data FROM files
        WHERE file_id = ?
        ORDER BY segment_number ASC
    ''', (file_id,))
    segments = c.fetchall()
    conn.close()
    return segments

# --- Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('upload'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists!', 'danger')
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/img')
def random_image():
    # Create a 2D image of size 256x256 with random RGB values
    width, height = 256, 256
    array = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)

    # Convert to an image
    image = Image.fromarray(array, 'RGB')

    # Save image to a BytesIO buffer
    img_io = BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)

    # Return the image as a response
    return send_file(img_io, mimetype='image/png')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('my_files'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files['file']
        pin = request.form['pin']

        if file and pin:
            file_data = file.read()
            file_id = save_file_segments(session['user_id'], file.filename, file_data, pin)
            flash(f'File uploaded successfully! Access it here: {request.url_root}file/{file_id}', 'success')
            return redirect(url_for('upload'))
        else:
            flash('File and PIN required.', 'danger')

    return render_template('upload.html')

@app.route('/delete-file/<file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Ensure the file belongs to the logged-in user
    c.execute('SELECT 1 FROM files WHERE file_id = ? AND user_id = ?', (file_id, session['user_id']))
    if not c.fetchone():
        conn.close()
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_files'))

    # Delete all segments of the file
    c.execute('DELETE FROM files WHERE file_id = ? AND user_id = ?', (file_id, session['user_id']))
    conn.commit()
    conn.close()

    flash('File deleted successfully.', 'success')
    return redirect(url_for('my_files'))


@app.route('/my-files')
def my_files():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Group by file_id to get one file per uploaded file
    c.execute('''
        SELECT file_id, filename, MIN(id) as first_id
        FROM files
        WHERE user_id = ?
        GROUP BY file_id
        ORDER BY first_id DESC
    ''', (session['user_id'],))

    files = c.fetchall()
    conn.close()

    return render_template('file_list.html', files=files)

@app.route('/file-history/<file_id>')
def file_history(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('SELECT filename FROM files WHERE file_id = ? LIMIT 1', (file_id,))
    file_row = c.fetchone()
    file_name = file_row[0] if file_row else 'Unknown File'

    # Join views with users table to get username
    c.execute('''
        SELECT users.username, views.type, views.created_at
        FROM views
        JOIN users ON users.id = views.user_id
        WHERE views.file_id = ?
        ORDER BY views.created_at DESC
    ''', (file_id,))
    
    history = c.fetchall()
    conn.close()

    return render_template('file_history.html', history=history,file_name=file_name)

@app.route('/view_file/<file_id>', methods=['GET', 'POST'])
def view_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Check file exists
    c.execute('SELECT filename FROM files WHERE file_id = ? LIMIT 1', (file_id,))
    file_row = c.fetchone()

    if not file_row:
        conn.close()
        flash('File not found.', 'danger')
        return redirect(url_for('my_files'))

    filename = file_row[0]
    file_data_url = None

    if request.method == 'POST':
        pin = request.form.get('pin')

        c.execute('INSERT INTO views (type,user_id, file_id) VALUES (?, ?,?)', ("File View",session['user_id'],file_id ))
        conn.commit()

        # VERY IMPORTANT - Order by segment_number
        c.execute('''
            SELECT data
            FROM files
            WHERE file_id = ? AND pin = ?
            ORDER BY segment_number ASC
        ''', (file_id, pin))

        segments = c.fetchall()
        conn.close()

        if not segments:
            flash('Incorrect PIN or no data found.', 'danger')
            return redirect(request.url)

        # Build full base64 correctly
        full_base64 = ''.join([segment[0] for segment in segments])

        mime_type = guess_mime_type(filename)

        # Create valid Data URL
        file_data_url = f"data:{mime_type};base64,{full_base64}"

    else:
        pin = generate_otp()
        send_otp_email(session['username'], pin)
        c.execute('UPDATE files SET pin=? WHERE file_id = ?', (pin,file_id ))
        conn.commit()
        conn.close()

    return render_template('file_view_pin.html', file_id=file_id, filename=filename, file_data_url=file_data_url)


@app.route('/file/<file_id>', methods=['GET', 'POST'])
def file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        pin = request.form['pin']
        
        c.execute('INSERT INTO views (type,user_id, file_id) VALUES (?, ?,?)', ("Packets View",session['user_id'],file_id ))
        conn.commit()

        c.execute('SELECT DISTINCT pin FROM files WHERE file_id = ?', (file_id,))
        result = c.fetchone()
        conn.close()

        if result and result[0] == pin:
            segments = get_file_segments(file_id)
            return render_template('view_packets.html', segments=segments, file_id=file_id)
        else:
            flash('Invalid PIN!', 'danger')

    else:
        pin = generate_otp()
        send_otp_email(session['username'], pin)
        c.execute('UPDATE files SET pin=? WHERE file_id = ?', (pin,file_id ))
        conn.commit()
        conn.close()

    return render_template('enter_pin.html', file_id=file_id)

@app.route('/file/<file_id>/download')
def download(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    segments = get_file_segments(file_id)
    file_data = b''.join([base64.b64decode(seg[1]) for seg in segments])

    # Get filename
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('INSERT INTO views (type,user_id, file_id) VALUES (?, ?,?)', ("download",session['user_id'],file_id ))
    conn.commit()

    c.execute('SELECT DISTINCT filename FROM files WHERE file_id = ?', (file_id,))
    filename = c.fetchone()[0]
    conn.close()

    return send_file(BytesIO(file_data), download_name=filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
