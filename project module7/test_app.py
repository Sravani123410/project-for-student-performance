import unittest
import io
import json
import os
from app import app
from models import db, User, Student, Course, Grade

class TestStudentAnalyticsSystem(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        test_db_path = os.path.join(app.root_path, 'instance', 'test.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{test_db_path}'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

            # Create Admin User
            admin = User(name='Admin User', email='admin@analytics.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

            # Create Student User & Profile
            student_user = User(name='John Doe', email='john@analytics.com', role='student')
            student_user.set_password('student123')
            db.session.add(student_user)
            db.session.flush()

            student = Student(name='John Doe', email='john@test.com', user_id=student_user.id)
            db.session.add(student)

            # Create Course
            course = Course(code='CS101', name='Intro to Computer Science', credits=4)
            db.session.add(course)

            db.session.commit()

            self.admin_id = admin.id
            self.student_id = student.id
            self.course_id = course.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login_admin(self):
        res = self.client.post('/login', data={'email': 'admin@analytics.com', 'password': 'admin123'}, follow_redirects=True)
        if b'Invalid email or password' in res.data:
            print("LOGIN FAILED: Invalid email or password")
        return res

    def test_01_authentication(self):
        # Admin Login
        res = self.login_admin()
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome back, Admin User!', res.data)

        # API Auth Login
        api_res = self.client.post('/api/auth/login', json={'email': 'admin@analytics.com', 'password': 'admin123'})
        self.assertEqual(api_res.status_code, 200)
        data = json.loads(api_res.data)
        self.assertIn('token', data)
        self.assertEqual(data['user']['email'], 'admin@analytics.com')

    def test_02_student_crud_web(self):
        self.login_admin()

        # GET /students
        res = self.client.get('/students')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'John Doe', res.data)

        # POST /students (Create)
        res = self.client.post('/students', data={'name': 'Jane Smith', 'email': 'jane@test.com'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Jane Smith', res.data)

        # GET /students/<id> (Detail)
        res = self.client.get(f'/students/{self.student_id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'John Doe', res.data)

        # PUT /students/<id> (Full Update using method override)
        res = self.client.post(f'/students/{self.student_id}', data={'_method': 'PUT', 'name': 'Johnathan Doe', 'email': 'johnathan@test.com'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Johnathan Doe', res.data)

        # PATCH /students/<id> (Partial Update using method override)
        res = self.client.post(f'/students/{self.student_id}', data={'_method': 'PATCH', 'email': 'john.updated@test.com'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'john.updated@test.com', res.data)

        # DELETE /students/<id>
        res = self.client.post(f'/students/{self.student_id}', data={'_method': 'DELETE'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'deleted successfully', res.data)

    def test_03_course_crud_web(self):
        self.login_admin()

        # GET /courses
        res = self.client.get('/courses')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'CS101', res.data)

        # POST /courses (Create)
        res = self.client.post('/courses', data={'code': 'MATH201', 'name': 'Calculus II', 'credits': 3, 'description': 'Advanced calculus'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MATH201', res.data)

        # PUT /courses/<id> (Full Update)
        res = self.client.post(f'/courses/{self.course_id}', data={'_method': 'PUT', 'code': 'CS101-UPDATED', 'name': 'Computer Science Basics', 'credits': 4}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'CS101-UPDATED', res.data)

        # DELETE /courses/<id>
        res = self.client.post(f'/courses/{self.course_id}', data={'_method': 'DELETE'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'deleted', res.data)

    def test_04_grades_and_analytics(self):
        self.login_admin()

        # POST /grades (Assign Grade)
        res = self.client.post('/grades', data={'student_id': self.student_id, 'course_id': self.course_id, 'score': 95.0, 'date': '2026-09-20'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'95.0%', res.data)

        # GET /analytics
        res = self.client.get('/analytics')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Mean (Average Score)', res.data)
        self.assertIn(b'95', res.data)

        # Export CSV
        res_csv = self.client.get('/analytics/export?format=csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')

        # Export XLSX
        res_xlsx = self.client.get('/analytics/export?format=xlsx')
        self.assertEqual(res_xlsx.status_code, 200)
        self.assertIn('spreadsheetml', res_xlsx.mimetype)

    def test_05_csv_bulk_upload(self):
        self.login_admin()

        csv_data = "student_email,student_name,course_code,score,date\n" \
                   "sam@test.com,Sam Wilson,CS101,88.5,2026-09-25\n"

        file = (io.BytesIO(csv_data.encode('utf-8')), 'test_grades.csv')
        res = self.client.post('/grades/upload-csv', data={'file': file}, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Successfully imported 1 grade records', res.data)

    def test_06_restful_api_endpoints(self):
        # Obtain JWT Token via API login
        auth_res = self.client.post('/api/auth/login', json={'email': 'admin@analytics.com', 'password': 'admin123'})
        token = json.loads(auth_res.data)['token']
        headers = {'Authorization': f'Bearer {token}'}

        # GET /api/students
        res = self.client.get('/api/students', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(len(data) >= 1)

        # POST /api/students
        res = self.client.post('/api/students', json={'name': 'API Student', 'email': 'api@test.com'}, headers=headers)
        self.assertEqual(res.status_code, 201)

        # GET /api/analytics
        res = self.client.get('/api/analytics', headers=headers)
        self.assertEqual(res.status_code, 200)

if __name__ == '__main__':
    unittest.main()
