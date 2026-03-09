"""
QR Attendance System Backend API
Provides REST API endpoints for dashboard data, statistics, and reports
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Any
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Data storage paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')
ATTENDANCE_FILE = os.path.join(DATA_DIR, 'attendance.json')
STUDENTS_FILE = os.path.join(DATA_DIR, 'students.json')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def load_data(filename: str, default: Any = None) -> Any:
    """Load data from JSON file"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or []

def save_data(filename: str, data: Any) -> None:
    """Save data to JSON file"""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def get_sessions() -> List[Dict]:
    """Get all sessions"""
    return load_data(SESSIONS_FILE, [])

def get_attendance() -> List[Dict]:
    """Get all attendance records"""
    return load_data(ATTENDANCE_FILE, [])

def get_students() -> List[Dict]:
    """Get all students"""
    return load_data(STUDENTS_FILE, [])

def get_teacher_sessions(teacher_id: str) -> List[Dict]:
    """Get sessions for a specific teacher"""
    sessions = get_sessions()
    return [s for s in sessions if s.get('teacher') == teacher_id]

def get_today_attendance() -> List[Dict]:
    """Get attendance records for today"""
    today = date.today().isoformat()
    attendance = get_attendance()
    return [a for a in attendance if a.get('date') == today]

def calculate_dashboard_stats(teacher_id: str = None) -> Dict:
    """Calculate dashboard statistics"""
    sessions = get_teacher_sessions(teacher_id) if teacher_id else get_sessions()
    attendance = get_attendance()
    students = get_students()
    today_attendance = get_today_attendance()

    # Total sessions
    total_sessions = len(sessions)

    # Total students
    total_students = len(students)

    # Present today (unique students who attended today)
    present_today = len(set(a.get('studentId') for a in today_attendance))

    # Average attendance calculation
    if total_sessions > 0 and total_students > 0:
        total_possible_attendances = total_sessions * total_students
        total_actual_attendances = len(attendance)
        avg_attendance = round((total_actual_attendances / total_possible_attendances) * 100, 1)
    else:
        avg_attendance = 0.0

    return {
        'total_sessions': total_sessions,
        'total_students': total_students,
        'present_today': present_today,
        'avg_attendance': avg_attendance
    }

def get_attendance_trends() -> Dict:
    """Get attendance trends for charts"""
    attendance = get_attendance()
    sessions = get_sessions()

    # Group attendance by date
    date_stats = {}
    for record in attendance:
        date_key = record.get('date', '')
        if date_key not in date_stats:
            date_stats[date_key] = {'present': 0, 'sessions': 0}
        date_stats[date_key]['present'] += 1

    # Count sessions per date
    for session in sessions:
        created_date = session.get('createdAt', '').split('T')[0]
        if created_date in date_stats:
            date_stats[created_date]['sessions'] += 1

    # Prepare chart data
    dates = sorted(date_stats.keys())[-7:]  # Last 7 days
    present_data = [date_stats.get(d, {'present': 0})['present'] for d in dates]
    session_data = [date_stats.get(d, {'sessions': 0})['sessions'] for d in dates]

    return {
        'dates': dates,
        'present': present_data,
        'sessions': session_data
    }

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    teacher_id = request.args.get('teacher_id')
    stats = calculate_dashboard_stats(teacher_id)
    return jsonify(stats)

# Support path-based teacher ID for convenience
@app.route('/api/dashboard/stats/<teacher_id>', methods=['GET'])
def get_dashboard_stats_by_teacher(teacher_id):
    """Get dashboard statistics for a specific teacher"""
    stats = calculate_dashboard_stats(teacher_id)
    return jsonify(stats)

@app.route('/api/dashboard/trends', methods=['GET'])
def get_dashboard_trends():
    """Get attendance trends for charts"""
    trends = get_attendance_trends()
    return jsonify(trends)

# Alias for trend endpoint to support /api/attendance/trends path
@app.route('/api/attendance/trends', methods=['GET'])
def get_attendance_trends_alias():
    """Alias endpoint: Get attendance trends"""
    return get_dashboard_trends()

@app.route('/api/sessions', methods=['GET'])
def get_sessions_api():
    """Get sessions, optionally filtered by teacher"""
    teacher_id = request.args.get('teacher_id')
    sessions = get_teacher_sessions(teacher_id) if teacher_id else get_sessions()
    return jsonify(sessions)

@app.route('/api/attendance', methods=['GET'])
def get_attendance_api():
    """Get attendance records"""
    attendance = get_attendance()
    return jsonify(attendance)

@app.route('/api/students', methods=['GET'])
def get_students_api():
    """Get all students"""
    students = get_students()
    return jsonify(students)

@app.route('/api/sessions', methods=['POST'])
def create_session():
    """Create a new session"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    sessions = get_sessions()
    new_session = {
        'id': f"session-{len(sessions) + 1}",
        'sessionId': data.get('sessionId'),
        'subject': data.get('subject'),
        'department': data.get('department'),
        'year': data.get('year'),
        'teacher': data.get('teacher'),
        'createdAt': datetime.now().isoformat(),
        'expiresAt': data.get('expiresAt')
    }

    sessions.append(new_session)
    save_data(SESSIONS_FILE, sessions)
    return jsonify(new_session), 201

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    """Mark attendance. Auto-creates session and student from payload if missing (so attendance always marks)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Basic required fields
    required_fields = ['sessionId', 'studentId', 'name', 'rollNumber', 'department', 'year', 'subject']
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    session_id = data.get('sessionId')
    student_id = data.get('studentId')
    today_str = date.today().isoformat()
    now = datetime.now()

    sessions = get_sessions()
    students = get_students()
    attendance = get_attendance()

    # Ensure session exists: create from payload if missing (e.g. teacher created QR on another device)
    session = next((s for s in sessions if s.get('sessionId') == session_id), None)
    if not session:
        expires_at = (now + timedelta(minutes=10)).isoformat()
        new_sess = {
            'id': f"session-{len(sessions) + 1}",
            'sessionId': session_id,
            'subject': data.get('subject', 'N/A'),
            'department': data.get('department', 'N/A'),
            'year': data.get('year', 'N/A'),
            'teacher': data.get('teacher', ''),
            'createdAt': now.isoformat(),
            'expiresAt': data.get('expiresAt') or expires_at,
        }
        sessions.append(new_sess)
        save_data(SESSIONS_FILE, sessions)
        session = new_sess

    expires_at_str = session.get('expiresAt')
    if expires_at_str:
        try:
            # Support ISO strings with or without 'Z'
            exp_str = expires_at_str.replace('Z', '')[:26]
            expires_at = datetime.fromisoformat(exp_str)
            if now > expires_at:
                return jsonify({'error': 'QR/session has expired'}), 400
        except (ValueError, TypeError):
            pass  # If expiry malformed, allow the scan (session was just created or legacy)

    # Ensure student exists: create from payload if missing (e.g. registered only on another device)
    student = next((s for s in students if s.get('id') == student_id), None)
    if not student:
        new_student = {
            'id': student_id,
            'name': data.get('name', ''),
            'rollNumber': data.get('rollNumber', ''),
            'email': data.get('email', ''),
            'department': data.get('department', 'N/A'),
            'year': data.get('year', 'N/A'),
            'registeredAt': now.isoformat(),
        }
        students.append(new_student)
        save_data(STUDENTS_FILE, students)
        student = new_student

    # Prevent duplicate attendance for same session+student+date
    if any(
        a.get('sessionId') == session_id and
        a.get('studentId') == student_id and
        a.get('date') == today_str
        for a in attendance
    ):
        return jsonify({'error': 'Attendance already marked for this session', 'duplicate': True}), 409

    new_record = {
        'id': f"attendance-{len(attendance) + 1}",
        'sessionId': session_id,
        'studentId': student_id,
        'name': data.get('name'),
        'rollNumber': data.get('rollNumber'),
        'department': data.get('department'),
        'year': data.get('year'),
        'subject': data.get('subject'),
        'date': today_str,
        'scanTime': now.isoformat(),
        'status': 'Present'
    }

    attendance.append(new_record)
    save_data(ATTENDANCE_FILE, attendance)
    return jsonify(new_record), 201

@app.route('/api/students', methods=['POST'])
def add_student():
    """Add a new student"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    students = get_students()
    # Use frontend id if provided so attendance records match
    student_id = data.get('id') or f"student-{len(students) + 1}"
    if any(s.get('id') == student_id for s in students):
        return jsonify({'error': 'Student with this ID already exists'}), 409
    new_student = {
        'id': student_id,
        'name': data.get('name'),
        'rollNumber': data.get('rollNumber'),
        'email': data.get('email'),
        'department': data.get('department'),
        'year': data.get('year'),
        'registeredAt': datetime.now().isoformat()
    }

    students.append(new_student)
    save_data(STUDENTS_FILE, students)
    return jsonify(new_student), 201

@app.route('/api/analysis', methods=['GET'])
def api_analysis():
    """Get attendance analysis (Python) for teacher dashboard."""
    try:
        import attendance_analysis
        return jsonify(attendance_analysis.analyze_attendance())
    except Exception as e:
        return jsonify({'error': str(e), 'summary': calculate_dashboard_stats()})


@app.route('/api/report/session/<session_id>/pdf', methods=['GET'])
def api_session_report_pdf(session_id: str):
    """
    Generate a PDF attendance report for a single session.

    The report is built entirely from JSON files (no database) using ReportLab.
    """
    sessions = get_sessions()
    attendance = get_attendance()
    students = get_students()

    session = next((s for s in sessions if s.get('sessionId') == session_id), None)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    records = [a for a in attendance if a.get('sessionId') == session_id]
    if not records:
        return jsonify({'error': 'No attendance records for this session'}), 404

    # Map student id -> extra info if needed later
    student_lookup = {s.get('id'): s for s in students}

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header
    y = height - 40
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Attendance Report")
    y -= 24

    pdf.setFont("Helvetica", 11)
    created_at = session.get('createdAt', '')[:19].replace('T', ' ')
    info_lines = [
        f"Session ID : {session.get('sessionId')}",
        f"Subject    : {session.get('subject', '')}",
        f"Department : {session.get('department', '')}",
        f"Year       : {session.get('year', '')}",
        f"Created At : {created_at}",
        f"Total Records : {len(records)}",
    ]
    for line in info_lines:
        pdf.drawString(40, y, line)
        y -= 16

    y -= 10
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "No.")
    pdf.drawString(70, y, "Roll")
    pdf.drawString(140, y, "Name")
    pdf.drawString(280, y, "Dept")
    pdf.drawString(325, y, "Year")
    pdf.drawString(365, y, "Status")
    pdf.drawString(420, y, "Date")
    pdf.drawString(480, y, "Time")
    y -= 12
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 9)
    row_num = 1
    for rec in records:
        if y < 60:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(40, y, "No.")
            pdf.drawString(70, y, "Roll")
            pdf.drawString(140, y, "Name")
            pdf.drawString(280, y, "Dept")
            pdf.drawString(325, y, "Year")
            pdf.drawString(365, y, "Status")
            pdf.drawString(420, y, "Date")
            pdf.drawString(480, y, "Time")
            y -= 12
            pdf.line(40, y, width - 40, y)
            y -= 12
            pdf.setFont("Helvetica", 9)

        student = student_lookup.get(rec.get('studentId')) or {}
        roll = rec.get('rollNumber') or student.get('rollNumber', '')
        name = rec.get('name') or student.get('name', '')
        dept = rec.get('department') or student.get('department', '')
        year = rec.get('year') or student.get('year', '')
        status = rec.get('status', 'Present')
        date_str = rec.get('date', '')
        time_str = (rec.get('scanTime') or '').split('T')[-1][:8]

        pdf.drawString(40, y, str(row_num))
        pdf.drawString(70, y, roll)
        pdf.drawString(140, y, name[:24])
        pdf.drawString(280, y, dept)
        pdf.drawString(325, y, year)
        pdf.drawString(365, y, status)
        pdf.drawString(420, y, date_str)
        pdf.drawString(480, y, time_str)
        y -= 14
        row_num += 1

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"attendance_{session_id}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


if __name__ == '__main__':
    # Run with debug=False for production to improve performance
    # Use PORT from environment when deployed (e.g. Render, Heroku)
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, port=port, use_reloader=False, host='0.0.0.0')