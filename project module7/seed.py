import os
from datetime import datetime, timedelta
import random
from app import app
from models import db, User, Student, Course, Grade

def seed_database():
    with app.app_context():
        # Create database tables
        db.create_all()

        # Check if already seeded
        if User.query.first():
            print("Database already contains data.")
            return

        print("Seeding database with sample users, students, courses, and grades...")

        # Create Admin User
        admin = User(name='Admin User', email='admin@analytics.com', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)

        # Sample Students Data
        student_data = [
            {'name': 'Alice Johnson', 'email': 'alice.johnson@university.edu'},
            {'name': 'Bob Smith', 'email': 'bob.smith@university.edu'},
            {'name': 'Charlie Brown', 'email': 'charlie.brown@university.edu'},
            {'name': 'Diana Prince', 'email': 'diana.prince@university.edu'},
            {'name': 'Ethan Hunt', 'email': 'ethan.hunt@university.edu'},
            {'name': 'Fiona Gallagher', 'email': 'fiona.gallagher@university.edu'},
            {'name': 'George Clark', 'email': 'george.clark@university.edu'},
            {'name': 'Hannah Abbott', 'email': 'hannah.abbott@university.edu'}
        ]

        students = []
        for s in student_data:
            # Create user account for student
            user = User(name=s['name'], email=s['email'], role='student')
            user.set_password('student123')
            db.session.add(user)
            db.session.flush()

            student = Student(name=s['name'], email=s['email'], user_id=user.id)
            db.session.add(student)
            students.append(student)

        db.session.flush()

        # Sample Courses
        courses_data = [
            {'code': 'CS101', 'name': 'Computer Science Fundamentals', 'credits': 4, 'description': 'Introduction to algorithms, data structures, and Python programming.'},
            {'code': 'MATH201', 'name': 'Calculus & Linear Algebra', 'credits': 3, 'description': 'Vector spaces, matrices, differentiation, and integration.'},
            {'code': 'DS301', 'name': 'Data Science & Machine Learning', 'credits': 4, 'description': 'Pandas, NumPy, statistical modeling, and data analytics.'},
            {'code': 'DB102', 'name': 'Database Systems & MySQL', 'credits': 3, 'description': 'Relational data modeling, SQL queries, indexing, and ORM.'}
        ]

        courses = []
        for c in courses_data:
            course = Course(code=c['code'], name=c['name'], credits=c['credits'], description=c['description'])
            db.session.add(course)
            courses.append(course)

        db.session.flush()

        # Sample Grades
        base_date = datetime.utcnow().date() - timedelta(days=60)
        random.seed(42)  # For deterministic seed scores

        for student in students:
            for course in courses:
                # Randomize realistic scores
                score = round(random.uniform(62.0, 99.0), 1)
                date = base_date + timedelta(days=random.randint(1, 55))
                grade = Grade(student_id=student.id, course_id=course.id, score=score, date=date)
                db.session.add(grade)

        db.session.commit()
        print("Database successfully seeded!")

        # Create sample_grades.csv for upload testing
        create_sample_csv()

def create_sample_csv():
    sample_csv_content = """student_email,student_name,course_code,score,date
ian.wright@university.edu,Ian Wright,CS101,92.5,2026-09-15
julia.roberts@university.edu,Julia Roberts,MATH201,88.0,2026-09-16
alice.johnson@university.edu,Alice Johnson,DS301,96.0,2026-09-17
bob.smith@university.edu,Bob Smith,DB102,74.5,2026-09-18
kevin.bacon@university.edu,Kevin Bacon,CS101,81.0,2026-09-19
"""
    csv_path = os.path.join(os.path.dirname(__file__), 'sample_grades.csv')
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(sample_csv_content)
    print(f"Sample CSV created at {csv_path}")

if __name__ == '__main__':
    seed_database()
