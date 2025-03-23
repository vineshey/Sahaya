from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database setup
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to convert Row objects to dictionaries
def row_to_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}

def init_db():
    conn = get_db_connection()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')
    conn.execute('''
    CREATE TABLE IF NOT EXISTS resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        quantity TEXT NOT NULL,
        location TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        urgency TEXT,
        expiry_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Home route - redirects to dashboard if logged in, otherwise to login
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Dashboard route - only accessible when logged in
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    resources = conn.execute('''
    SELECT r.id, r.name, r.category, r.quantity, r.location, r.latitude, r.longitude, r.role, r.urgency, r.expiry_date 
    FROM resources r
    ''').fetchall()
    conn.close()
    
    # Convert to list of dictionaries to avoid JSON serialization issues
    resources_list = [row_to_dict(resource) for resource in resources]
    
    return render_template('dashboard.html',
                          resources=resources_list,
                          username=session.get('username'),
                          role=session.get('role'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        quantity = request.form.get('quantity')
        location = request.form.get('location')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        role = session.get('role')
        
        # Role-specific fields
        urgency = request.form.get('urgency') if role == 'Receiver' else None
        expiry_date = request.form.get('expiry') if role == 'Donor' else None
        
        conn = get_db_connection()
        conn.execute('''
        INSERT INTO resources (name, category, quantity, location, latitude, longitude, user_id, role, urgency, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, category, quantity, location, latitude, longitude, session['user_id'], role, urgency, expiry_date))
        conn.commit()
        conn.close()
        
        flash('Resource added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_resource.html',
                         username=session.get('username'),
                         role=session.get('role'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            # Clear any existing session data first to prevent conflicts
            session.clear()
            
            # Set new session data
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            flash('You have been logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        conn = get_db_connection()
        
        # Check if username already exists
        if conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists', 'danger')
            conn.close()
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                    (username, hashed_password, role))
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    conn = get_db_connection()
    resource = conn.execute('SELECT * FROM resources WHERE id = ?', (id,)).fetchone()
    
    # Check if resource exists and belongs to the current user
    if not resource or resource['user_id'] != session['user_id']:
        conn.close()
        flash('Resource not found or you do not have permission to edit it', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        quantity = request.form.get('quantity')
        location = request.form.get('location')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        role = session.get('role')
        
        # Role-specific fields
        urgency = request.form.get('urgency') if role == 'Receiver' else resource['urgency']
        expiry_date = request.form.get('expiry') if role == 'Donor' else resource['expiry_date']
        
        conn.execute('''
        UPDATE resources 
        SET name = ?, category = ?, quantity = ?, location = ?, 
            latitude = ?, longitude = ?, urgency = ?, expiry_date = ?
        WHERE id = ?
        ''', (name, category, quantity, location, latitude, longitude, 
              urgency, expiry_date, id))
        conn.commit()
        conn.close()
        
        flash('Resource updated successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    # Convert Row to dict for template
    resource_dict = row_to_dict(resource)
    conn.close()
    
    return render_template('edit_resource.html', 
                          resource=resource_dict,
                          username=session.get('username'),
                          role=session.get('role'))

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    conn = get_db_connection()
    resource = conn.execute('SELECT * FROM resources WHERE id = ?', (id,)).fetchone()
    
    # Check if resource exists and belongs to the current user
    if not resource or resource['user_id'] != session['user_id']:
        conn.close()
        flash('Resource not found or you do not have permission to delete it', 'danger')
        return redirect(url_for('dashboard'))
    
    conn.execute('DELETE FROM resources WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Resource deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

# API endpoint to get resources as JSON
@app.route('/api/resources')
@login_required
def api_resources():
    conn = get_db_connection()
    resources = conn.execute('SELECT * FROM resources').fetchall()
    conn.close()
    
    # Convert Row objects to dictionaries
    resources_list = [row_to_dict(resource) for resource in resources]
    return jsonify(resources_list)

@app.route('/api/resources_with_location', methods=['GET'])
def resources_with_location():
    conn = get_db_connection()
    resources = conn.execute('''
        SELECT id, name, category, quantity, location, latitude, longitude 
        FROM resources 
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    ''').fetchall()
    conn.close()
    
    resources_list = [row_to_dict(resource) for resource in resources]
    return jsonify(resources_list), 200




if __name__ == '__main__':
    app.run(debug=True)