import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, g
from config import Config
from models import db, User, Student, Course, Grade
from auth import generate_jwt, login_required, admin_required, get_current_user_from_request
from analytics import get_analytics_summary, export_analytics_file, process_csv_upload

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)

# Initialize Database
db.init_app(app)

# Method Override Middleware for HTML Forms (supporting PUT, PATCH, DELETE via _method form field)
@app.before_request
def method_override():
    if request.method == 'POST' and '_method' in request.form:
        method = request.form['_method'].upper()
        if method in ['PUT', 'PATCH', 'DELETE']:
            request.environ['REQUEST_METHOD'] = method

# Global User Injector for Jinja2 Templates
@app.context_processor
def inject_user():
    user = get_current_user_from_request()
    return dict(current_user=user)

# ==========================================
# AUTHENTICATION ROUTES (Web & API)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            token = generate_jwt(user)
            flash(f'Welcome back, {user.name}!', 'success')
            next_page = request.args.get('next') or url_for('dashboard')
            response = make_response(redirect(next_page))
            # Store JWT in cookie
            response.set_cookie('jwt_token', token, httponly=True, max_age=86400)
            return response
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'student').strip()

        if User.query.filter_by(email=email).first():
            flash('Email address already registered.', 'warning')
            return redirect(url_for('register_page'))

        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # If registered as a student, create Student entity
        if role == 'student':
            student = Student(name=name, email=email, user_id=user.id)
            db.session.add(student)

        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login_page'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('login_page')))
    response.set_cookie('jwt_token', '', expires=0)
    flash('You have been logged out.', 'info')
    return response

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        token = generate_jwt(user)
        return jsonify({'token': token, 'user': user.to_dict()})
    return jsonify({'error': 'Invalid credentials'}), 401


# ==========================================
# DASHBOARD ROUTE
# ==========================================

@app.route('/')
@login_required
def dashboard():
    total_students = Student.query.count()
    total_courses = Course.query.count()
    total_grades = Grade.query.count()

    summary = get_analytics_summary()
    return render_template('index.html',
                           total_students=total_students,
                           total_courses=total_courses,
                           total_grades=total_grades,
                           summary=summary)


# ==========================================
# STUDENTS ROUTES (Web CRUD)
# ==========================================

@app.route('/students', methods=['GET'])
@login_required
def list_students():
    search = request.args.get('search', '').strip()
    query = Student.query
    if search:
        query = query.filter(Student.name.ilike(f'%{search}%') | Student.email.ilike(f'%{search}%'))
    students = query.order_by(Student.name).all()
    return render_template('students/list.html', students=students, search=search)

@app.route('/students/new', methods=['GET'])
@admin_required
def new_student_form():
    return render_template('students/form.html', student=None)

@app.route('/students', methods=['POST'])
@admin_required
def create_student():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()

    if not name or not email:
        flash('Name and Email are required.', 'warning')
        return redirect(url_for('new_student_form'))

    if Student.query.filter_by(email=email).first():
        flash('Student with this email already exists.', 'danger')
        return redirect(url_for('new_student_form'))

    student = Student(name=name, email=email)
    db.session.add(student)
    db.session.commit()
    flash('Student added successfully!', 'success')
    return redirect(url_for('list_students'))

@app.route('/students/<int:id>/edit', methods=['GET'])
@admin_required
def edit_student_form(id):
    student = Student.query.get_or_404(id)
    return render_template('students/form.html', student=student)

@app.route('/students/<int:id>/delete', methods=['GET'])
@admin_required
def delete_student_confirm(id):
    student = Student.query.get_or_404(id)
    return render_template('students/delete_confirm.html', student=student)

@app.route('/students/<int:id>', endpoint='view_student', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@login_required
def view_student(id):
    student = Student.query.get_or_404(id)
    method = request.form.get('_method', request.method).upper()

    if method == 'DELETE':
        user = get_current_user_from_request()
        if not user or user.role != 'admin':
            flash('Access denied. Administrator rights required.', 'danger')
            return redirect(url_for('dashboard'))
        db.session.delete(student)
        db.session.commit()
        flash(f'Student "{student.name}" deleted successfully.', 'info')
        return redirect(url_for('list_students'))

    elif method in ['PUT', 'PATCH']:
        user = get_current_user_from_request()
        if not user or user.role != 'admin':
            flash('Access denied. Administrator rights required.', 'danger')
            return redirect(url_for('dashboard'))

        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()

        if method == 'PUT':
            if not name or not email:
                flash('All fields are required for full update.', 'warning')
                return redirect(url_for('edit_student_form', id=id))
            existing = Student.query.filter(Student.email == email, Student.id != id).first()
            if existing:
                flash('Email is already taken by another student.', 'danger')
                return redirect(url_for('edit_student_form', id=id))
            student.name = name
            student.email = email
            db.session.commit()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('view_student', id=id))
        else:  # PATCH
            if name:
                student.name = name
            if email:
                existing = Student.query.filter(Student.email == email, Student.id != id).first()
                if existing:
                    flash('Email is already taken by another student.', 'danger')
                    return redirect(url_for('edit_student_form', id=id))
                student.email = email
            db.session.commit()
            flash('Student updated successfully (Partial Update).', 'success')
            return redirect(url_for('view_student', id=id))

    else:  # GET
        summary = get_analytics_summary(student_id=id)
        return render_template('students/detail.html', student=student, summary=summary)

app.add_url_rule('/students/<int:id>', endpoint='update_student_full', view_func=view_student, methods=['PUT', 'POST'])
app.add_url_rule('/students/<int:id>', endpoint='update_student_partial', view_func=view_student, methods=['PATCH', 'POST'])
app.add_url_rule('/students/<int:id>', endpoint='delete_student', view_func=view_student, methods=['DELETE', 'POST'])


# ==========================================
# COURSES ROUTES (Web CRUD)
# ==========================================

@app.route('/courses', methods=['GET'])
@login_required
def list_courses():
    courses = Course.query.order_by(Course.code).all()
    return render_template('courses/list.html', courses=courses)

@app.route('/courses/new', methods=['GET'])
@admin_required
def new_course_form():
    return render_template('courses/form.html', course=None)

@app.route('/courses', methods=['POST'])
@admin_required
def create_course():
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    credits = request.form.get('credits', 3, type=int)
    description = request.form.get('description', '').strip()

    if not code or not name:
        flash('Course Code and Name are required.', 'warning')
        return redirect(url_for('new_course_form'))

    if Course.query.filter_by(code=code).first():
        flash('Course code already exists.', 'danger')
        return redirect(url_for('new_course_form'))

    course = Course(code=code, name=name, credits=credits, description=description)
    db.session.add(course)
    db.session.commit()
    flash('Course created successfully!', 'success')
    return redirect(url_for('list_courses'))

@app.route('/courses/<int:id>/edit', methods=['GET'])
@admin_required
def edit_course_form(id):
    course = Course.query.get_or_404(id)
    return render_template('courses/form.html', course=course)

@app.route('/courses/<int:id>/delete', methods=['GET'])
@admin_required
def delete_course_confirm(id):
    course = Course.query.get_or_404(id)
    return render_template('courses/delete_confirm.html', course=course)

@app.route('/courses/<int:id>', endpoint='view_course', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@login_required
def view_course(id):
    course = Course.query.get_or_404(id)
    method = request.form.get('_method', request.method).upper()

    if method == 'DELETE':
        user = get_current_user_from_request()
        if not user or user.role != 'admin':
            flash('Access denied. Administrator rights required.', 'danger')
            return redirect(url_for('dashboard'))
        db.session.delete(course)
        db.session.commit()
        flash(f'Course "{course.name}" deleted.', 'info')
        return redirect(url_for('list_courses'))

    elif method in ['PUT', 'PATCH']:
        user = get_current_user_from_request()
        if not user or user.role != 'admin':
            flash('Access denied. Administrator rights required.', 'danger')
            return redirect(url_for('dashboard'))

        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        credits = request.form.get('credits', type=int)
        description = request.form.get('description', '').strip()

        if method == 'PUT':
            existing = Course.query.filter(Course.code == code, Course.id != id).first()
            if existing:
                flash('Course code is already used by another course.', 'danger')
                return redirect(url_for('edit_course_form', id=id))
            course.code = code
            course.name = name
            if credits: course.credits = credits
            course.description = description
            db.session.commit()
            flash('Course updated successfully!', 'success')
            return redirect(url_for('view_course', id=id))
        else:  # PATCH
            if name: course.name = name
            if code:
                existing = Course.query.filter(Course.code == code, Course.id != id).first()
                if existing:
                    flash('Course code taken.', 'danger')
                    return redirect(url_for('edit_course_form', id=id))
                course.code = code
            if credits: course.credits = credits
            if description: course.description = description
            db.session.commit()
            flash('Course partially updated.', 'success')
            return redirect(url_for('view_course', id=id))

    else:  # GET
        summary = get_analytics_summary(course_id=id)
        return render_template('courses/detail.html', course=course, summary=summary)

app.add_url_rule('/courses/<int:id>', endpoint='update_course_full', view_func=view_course, methods=['PUT', 'POST'])
app.add_url_rule('/courses/<int:id>', endpoint='update_course_partial', view_func=view_course, methods=['PATCH', 'POST'])
app.add_url_rule('/courses/<int:id>', endpoint='delete_course', view_func=view_course, methods=['DELETE', 'POST'])


# ==========================================
# GRADES ROUTES (Web CRUD & Bulk Upload)
# ==========================================

@app.route('/grades', methods=['GET'])
@login_required
def list_grades():
    course_id = request.args.get('course_id', type=int)
    student_id = request.args.get('student_id', type=int)

    query = Grade.query
    if course_id:
        query = query.filter_by(course_id=course_id)
    if student_id:
        query = query.filter_by(student_id=student_id)

    grades = query.order_by(Grade.date.desc()).all()
    courses = Course.query.order_by(Course.code).all()
    students = Student.query.order_by(Student.name).all()

    return render_template('grades/list.html', grades=grades, courses=courses, students=students,
                           selected_course=course_id, selected_student=student_id)

@app.route('/grades/new', methods=['GET'])
@admin_required
def new_grade_form():
    students = Student.query.order_by(Student.name).all()
    courses = Course.query.order_by(Course.code).all()
    return render_template('grades/form.html', grade=None, students=students, courses=courses)

@app.route('/grades', methods=['POST'])
@admin_required
def create_grade():
    student_id = request.form.get('student_id', type=int)
    course_id = request.form.get('course_id', type=int)
    score = request.form.get('score', type=float)
    date_str = request.form.get('date')

    if not student_id or not course_id or score is None:
        flash('Student, Course, and Score are required.', 'warning')
        return redirect(url_for('new_grade_form'))

    grade_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
    grade = Grade(student_id=student_id, course_id=course_id, score=score, date=grade_date)
    db.session.add(grade)
    db.session.commit()
    flash('Grade recorded successfully!', 'success')
    return redirect(url_for('list_grades'))

@app.route('/grades/<int:id>/edit', methods=['GET'])
@admin_required
def edit_grade_form(id):
    grade = Grade.query.get_or_404(id)
    students = Student.query.order_by(Student.name).all()
    courses = Course.query.order_by(Course.code).all()
    return render_template('grades/form.html', grade=grade, students=students, courses=courses)

@app.route('/grades/<int:id>', methods=['PUT', 'POST'])
@admin_required
def update_grade(id):
    grade = Grade.query.get_or_404(id)
    score = request.form.get('score', type=float)
    date_str = request.form.get('date')

    if score is not None:
        grade.score = score
    if date_str:
        grade.date = datetime.strptime(date_str, '%Y-%m-%d').date()

    db.session.commit()
    flash('Grade record updated!', 'success')
    return redirect(url_for('list_grades'))

@app.route('/grades/<int:id>', methods=['DELETE'])
@admin_required
def delete_grade(id):
    grade = Grade.query.get_or_404(id)
    db.session.delete(grade)
    db.session.commit()
    flash('Grade entry removed.', 'info')
    return redirect(url_for('list_grades'))

@app.route('/grades/upload', methods=['GET'])
@admin_required
def upload_grades_form():
    return render_template('grades/upload.html')

@app.route('/grades/upload-csv', methods=['POST'])
@admin_required
def upload_grades_csv():
    if 'file' not in request.files:
        flash('No file uploaded.', 'warning')
        return redirect(url_for('upload_grades_form'))

    file = request.files['file']
    if file.filename == '':
        flash('Please select a valid CSV file.', 'warning')
        return redirect(url_for('upload_grades_form'))

    try:
        count, errors = process_csv_upload(file)
        if count > 0:
            flash(f'Successfully imported {count} grade records!', 'success')
        if errors:
            for err in errors[:5]:
                flash(err, 'danger')
            if len(errors) > 5:
                flash(f'And {len(errors)-5} more errors.', 'warning')
        return redirect(url_for('list_grades'))
    except Exception as e:
        flash(f'Failed to process CSV file: {str(e)}', 'danger')
        return redirect(url_for('upload_grades_form'))


# ==========================================
# ANALYTICS DASHBOARD & EXPORT ROUTES
# ==========================================

@app.route('/analytics', methods=['GET'])
@login_required
def analytics_dashboard():
    course_id = request.args.get('course_id', type=int)
    student_id = request.args.get('student_id', type=int)

    courses = Course.query.order_by(Course.code).all()
    students = Student.query.order_by(Student.name).all()
    summary = get_analytics_summary(course_id=course_id, student_id=student_id)

    return render_template('analytics/dashboard.html',
                           summary=summary,
                           courses=courses,
                           students=students,
                           selected_course=course_id,
                           selected_student=student_id)

@app.route('/analytics/export', methods=['GET'])
@login_required
def export_analytics():
    file_format = request.args.get('format', 'csv')
    course_id = request.args.get('course_id', type=int)
    student_id = request.args.get('student_id', type=int)

    buffer, mimetype, filename = export_analytics_file(file_format=file_format, course_id=course_id, student_id=student_id)
    return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)


# ==========================================
# RESTful API ENDPOINTS (JSON API)
# ==========================================

@app.route('/api/students', methods=['GET'])
@login_required
def api_get_students():
    students = Student.query.all()
    return jsonify([s.to_dict() for s in students])

@app.route('/api/students', methods=['POST'])
@admin_required
def api_create_student():
    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    if not name or not email:
        return jsonify({'error': 'Name and Email are required'}), 400

    if Student.query.filter_by(email=email).first():
        return jsonify({'error': 'Student email already exists'}), 400

    student = Student(name=name, email=email)
    db.session.add(student)
    db.session.commit()
    return jsonify(student.to_dict()), 201

@app.route('/api/students/<int:id>', methods=['GET'])
@login_required
def api_get_student(id):
    student = Student.query.get_or_404(id)
    return jsonify(student.to_dict())

@app.route('/api/students/<int:id>', methods=['PUT'])
@admin_required
def api_update_student_put(id):
    student = Student.query.get_or_404(id)
    data = request.get_json() or {}
    if 'name' not in data or 'email' not in data:
        return jsonify({'error': 'Name and Email are required for full update'}), 400

    student.name = data['name']
    student.email = data['email']
    db.session.commit()
    return jsonify(student.to_dict())

@app.route('/api/students/<int:id>', methods=['PATCH'])
@admin_required
def api_update_student_patch(id):
    student = Student.query.get_or_404(id)
    data = request.get_json() or {}
    if 'name' in data:
        student.name = data['name']
    if 'email' in data:
        student.email = data['email']
    db.session.commit()
    return jsonify(student.to_dict())

@app.route('/api/students/<int:id>', methods=['DELETE'])
@admin_required
def api_delete_student(id):
    student = Student.query.get_or_404(id)
    db.session.delete(student)
    db.session.commit()
    return jsonify({'message': 'Student deleted successfully'})

# Course API
@app.route('/api/courses', methods=['GET'])
@login_required
def api_get_courses():
    courses = Course.query.all()
    return jsonify([c.to_dict() for c in courses])

@app.route('/api/courses', methods=['POST'])
@admin_required
def api_create_course():
    data = request.get_json() or {}
    code = data.get('code')
    name = data.get('name')
    if not code or not name:
        return jsonify({'error': 'Code and Name required'}), 400

    course = Course(code=code.upper(), name=name, credits=data.get('credits', 3), description=data.get('description'))
    db.session.add(course)
    db.session.commit()
    return jsonify(course.to_dict()), 201

@app.route('/api/courses/<int:id>', methods=['GET'])
@login_required
def api_get_course(id):
    course = Course.query.get_or_404(id)
    return jsonify(course.to_dict())

@app.route('/api/courses/<int:id>', methods=['DELETE'])
@admin_required
def api_delete_course(id):
    course = Course.query.get_or_404(id)
    db.session.delete(course)
    db.session.commit()
    return jsonify({'message': 'Course deleted successfully'})

# Grade API
@app.route('/api/grades', methods=['GET'])
@login_required
def api_get_grades():
    grades = Grade.query.all()
    return jsonify([g.to_dict() for g in grades])

@app.route('/api/grades', methods=['POST'])
@admin_required
def api_create_grade():
    data = request.get_json() or {}
    student_id = data.get('student_id')
    course_id = data.get('course_id')
    score = data.get('score')
    if not student_id or not course_id or score is None:
        return jsonify({'error': 'student_id, course_id, and score required'}), 400

    grade = Grade(student_id=student_id, course_id=course_id, score=score)
    db.session.add(grade)
    db.session.commit()
    return jsonify(grade.to_dict()), 201

# Analytics API
@app.route('/api/analytics', methods=['GET'])
@login_required
def api_get_analytics():
    c_id = request.args.get('course_id', type=int)
    s_id = request.args.get('student_id', type=int)
    summary = get_analytics_summary(course_id=c_id, student_id=s_id)
    return jsonify(summary)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='127.0.0.1', port=5000)
