import io
import pandas as pd
import numpy as np
from datetime import datetime
from models import db, Grade, Student, Course

def get_analytics_summary(course_id=None, student_id=None):
    # Query grade records with related student and course details
    query = db.session.query(
        Grade.id.label('grade_id'),
        Grade.score,
        Grade.date,
        Student.id.label('student_id'),
        Student.name.label('student_name'),
        Student.email.label('student_email'),
        Course.id.label('course_id'),
        Course.code.label('course_code'),
        Course.name.label('course_name')
    ).join(Student, Grade.student_id == Student.id)\
     .join(Course, Grade.course_id == Course.id)

    if course_id:
        query = query.filter(Grade.course_id == course_id)
    if student_id:
        query = query.filter(Grade.student_id == student_id)

    records = query.all()

    if not records:
        return {
            'has_data': False,
            'overall': {
                'count': 0, 'mean': 0.0, 'median': 0.0, 'std': 0.0,
                'min': 0.0, 'max': 0.0, 'unique_students': 0, 'unique_courses': 0
            },
            'course_analytics': [],
            'student_rankings': [],
            'grade_distribution': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
        }

    # Convert query records to DataFrame
    df = pd.DataFrame([{
        'grade_id': r.grade_id,
        'score': r.score,
        'date': r.date,
        'student_id': r.student_id,
        'student_name': r.student_name,
        'student_email': r.student_email,
        'course_id': r.course_id,
        'course_code': r.course_code,
        'course_name': r.course_name
    } for r in records])

    # Overall NumPy/Pandas Calculations
    scores = df['score'].values
    overall_mean = float(np.mean(scores))
    overall_median = float(np.median(scores))
    overall_std = float(np.std(scores)) if len(scores) > 1 else 0.0
    overall_min = float(np.min(scores))
    overall_max = float(np.max(scores))

    # Grade Distribution (Letter Grades)
    def assign_letter(score):
        if score >= 90: return 'A'
        elif score >= 80: return 'B'
        elif score >= 70: return 'C'
        elif score >= 60: return 'D'
        else: return 'F'

    df['letter_grade'] = df['score'].apply(assign_letter)
    dist_counts = df['letter_grade'].value_counts().to_dict()
    grade_distribution = {
        'A': int(dist_counts.get('A', 0)),
        'B': int(dist_counts.get('B', 0)),
        'C': int(dist_counts.get('C', 0)),
        'D': int(dist_counts.get('D', 0)),
        'F': int(dist_counts.get('F', 0))
    }

    # Grouping & Aggregations by Course
    course_analytics = []
    course_grouped = df.groupby(['course_id', 'course_code', 'course_name'])

    for (c_id, c_code, c_name), group in course_grouped:
        c_scores = group['score'].values
        course_analytics.append({
            'course_id': int(c_id),
            'course_code': c_code,
            'course_name': c_name,
            'count': int(len(group)),
            'mean': round(float(np.mean(c_scores)), 2),
            'median': round(float(np.median(c_scores)), 2),
            'std': round(float(np.std(c_scores)), 2) if len(c_scores) > 1 else 0.0,
            'min': round(float(np.min(c_scores)), 2),
            'max': round(float(np.max(c_scores)), 2),
            'pass_rate': round(float(np.sum(c_scores >= 60) / len(c_scores) * 100), 1)
        })

    # Student Ranking per Course using Pandas rank()
    df['rank_in_course'] = df.groupby('course_id')['score'].rank(ascending=False, method='min').astype(int)

    student_rankings = []
    for _, row in df.sort_values(by=['course_code', 'rank_in_course']).iterrows():
        student_rankings.append({
            'grade_id': int(row['grade_id']),
            'student_id': int(row['student_id']),
            'student_name': row['student_name'],
            'course_code': row['course_code'],
            'course_name': row['course_name'],
            'score': float(row['score']),
            'letter_grade': row['letter_grade'],
            'rank': int(row['rank_in_course']),
            'date': str(row['date'])
        })

    # Overall Student Performance Summaries
    student_grouped = df.groupby(['student_id', 'student_name', 'student_email'])
    student_summaries = []
    for (s_id, s_name, s_email), group in student_grouped:
        s_scores = group['score'].values
        student_summaries.append({
            'student_id': int(s_id),
            'student_name': s_name,
            'student_email': s_email,
            'courses_taken': int(len(group)),
            'average_score': round(float(np.mean(s_scores)), 2),
            'highest_score': round(float(np.max(s_scores)), 2),
            'lowest_score': round(float(np.min(s_scores)), 2)
        })

    # Sort student summaries by average score descending
    student_summaries.sort(key=lambda x: x['average_score'], reverse=True)
    for rank_idx, s in enumerate(student_summaries, start=1):
        s['overall_rank'] = rank_idx

    return {
        'has_data': True,
        'overall': {
            'count': int(len(df)),
            'mean': round(overall_mean, 2),
            'median': round(overall_median, 2),
            'std': round(overall_std, 2),
            'min': round(overall_min, 2),
            'max': round(overall_max, 2),
            'unique_students': int(df['student_id'].nunique()),
            'unique_courses': int(df['course_id'].nunique())
        },
        'course_analytics': course_analytics,
        'student_rankings': student_rankings,
        'student_summaries': student_summaries,
        'grade_distribution': grade_distribution
    }

def export_analytics_file(file_format='csv', course_id=None, student_id=None):
    summary = get_analytics_summary(course_id=course_id, student_id=student_id)
    
    if not summary['has_data']:
        df = pd.DataFrame(columns=['Course Code', 'Student Name', 'Score', 'Rank', 'Date'])
    else:
        df = pd.DataFrame(summary['student_rankings'])
        df = df.rename(columns={
            'course_code': 'Course Code',
            'course_name': 'Course Name',
            'student_name': 'Student Name',
            'score': 'Score',
            'letter_grade': 'Grade',
            'rank': 'Rank in Course',
            'date': 'Date'
        })[['Course Code', 'Course Name', 'Student Name', 'Score', 'Grade', 'Rank in Course', 'Date']]

    output_buffer = io.BytesIO()
    if file_format.lower() == 'xlsx':
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Student Ranks & Grades')
            
            # Additional Sheet for Course Summaries
            if summary['has_data']:
                c_df = pd.DataFrame(summary['course_analytics']).rename(columns={
                    'course_code': 'Course Code',
                    'course_name': 'Course Name',
                    'count': 'Total Students',
                    'mean': 'Mean Score',
                    'median': 'Median Score',
                    'std': 'Std Dev',
                    'min': 'Min Score',
                    'max': 'Max Score',
                    'pass_rate': 'Pass Rate (%)'
                })
                c_df.to_excel(writer, index=False, sheet_name='Course Analytics Summary')
        output_buffer.seek(0)
        return output_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'student_analytics_report.xlsx'
    else:
        csv_data = df.to_csv(index=False)
        output_buffer.write(csv_data.encode('utf-8'))
        output_buffer.seek(0)
        return output_buffer, 'text/csv', 'student_analytics_report.csv'

def process_csv_upload(file):
    """
    Parses a CSV file with grade details.
    Expected CSV columns: student_email, student_name (optional), course_code, score, date (optional)
    """
    df = pd.read_csv(file)
    df.columns = [col.strip().lower() for col in df.columns]

    # Column mappings flexibility
    email_col = next((c for c in df.columns if 'email' in c), None)
    course_col = next((c for c in df.columns if 'course' in c or 'code' in c), None)
    score_col = next((c for c in df.columns if 'score' in c or 'grade' in c or 'mark' in c), None)
    name_col = next((c for c in df.columns if 'name' in c and 'course' not in c), None)
    date_col = next((c for c in df.columns if 'date' in c), None)

    if not (email_col and course_col and score_col):
        raise ValueError("CSV must contain at least 'email', 'course_code', and 'score' columns.")

    success_count = 0
    errors = []

    for index, row in df.iterrows():
        try:
            email = str(row[email_col]).strip()
            c_code = str(row[course_col]).strip().upper()
            score = float(row[score_col])

            # Find or Create Student
            student = Student.query.filter_by(email=email).first()
            if not student:
                s_name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else email.split('@')[0].replace('.', ' ').title()
                student = Student(name=s_name, email=email)
                db.session.add(student)
                db.session.flush()

            # Find Course
            course = Course.query.filter_by(code=c_code).first()
            if not course:
                errors.append(f"Row {index+2}: Course code '{c_code}' not found.")
                continue

            # Parse Date
            if date_col and pd.notna(row[date_col]):
                try:
                    g_date = pd.to_datetime(row[date_col]).date()
                except Exception:
                    g_date = datetime.utcnow().date()
            else:
                g_date = datetime.utcnow().date()

            # Create or update Grade
            grade = Grade(student_id=student.id, course_id=course.id, score=score, date=g_date)
            db.session.add(grade)
            success_count += 1
        except Exception as e:
            errors.append(f"Row {index+2}: {str(e)}")

    db.session.commit()
    return success_count, errors
