
import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from utils import (
    STAFF_OPTIONS, STAFF_CODE_MAP, init_gemini,
    fetch_staff_activities, summarize_staff_activities, count_activities_by_type,
    filter_mass_emails
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# --- Configuration ---
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# --- Routes ---

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.before_request
def check_auth():
    if request.endpoint == 'serve_static':
        return
    if request.endpoint == 'login':
        return
    if APP_PASSWORD and not session.get('authenticated'):
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            flash('パスワードが違います', 'error')
    return render_template('login.html')

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', staff_options=STAFF_OPTIONS)

@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        staff_name = request.form.get('staff_name', '')
        period = request.form.get('period', '1week')
        custom_start = request.form.get('custom_start', '')
        custom_end = request.form.get('custom_end', '')
        
        # Calculate date range based on period selection
        today = datetime.now().date()
        if period == 'custom' and custom_start and custom_end:
            start_date = custom_start
            end_date = custom_end
        elif period == '2weeks':
            start_date = (today - timedelta(days=14)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        elif period == '1month':
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        else:  # Default: 1week
            start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        
        # Get staff email for Kintone query
        staff_email = STAFF_CODE_MAP.get(staff_name, '')
        if not staff_email:
            flash('社員が見つかりませんでした', 'error')
            return redirect(url_for('index'))
        
        # Fetch activities from Kintone
        print(f"[DEBUG] Fetching activities for {staff_email}, {start_date} to {end_date}")
        all_activities = fetch_staff_activities(staff_email, start_date, end_date)
        print(f"[DEBUG] Fetched {len(all_activities)} activities")
        
        # Filter out mass emails
        individual_activities, mass_email_count = filter_mass_emails(all_activities)
        print(f"[DEBUG] Individual: {len(individual_activities)}, Mass emails: {mass_email_count}")
        
        # Generate AI summary (using individual activities only)
        debug_info = ""
        if not init_gemini():
            debug_info = "GEMINI_API_KEY が未設定です"
            summary = {"summary": f"AI要約機能が利用できません（{debug_info}）", "highlights": "", "concerns": "", "mass_email_note": ""}
        else:
            try:
                summary = summarize_staff_activities(individual_activities, staff_name, start_date, end_date)
                if not summary or not summary.get("summary"):
                    debug_info = "要約結果が空でした"
                    summary = {"summary": f"要約生成に失敗しました（{debug_info}）", "highlights": "", "concerns": "", "mass_email_note": ""}
            except Exception as e:
                debug_info = str(e)
                summary = {"summary": f"エラー: {debug_info}", "highlights": "", "concerns": "", "mass_email_note": ""}
        
        # Always use program-detected mass email count (not AI's)
        if mass_email_count > 0:
            summary["mass_email_note"] = f"※ この期間に{mass_email_count}件の一斉メールを実施"
        else:
            summary["mass_email_note"] = ""
        
        # Count activities by type (all activities for accurate stats)
        activity_counts = count_activities_by_type(all_activities)
        
        return render_template('report.html',
                               staff_name=staff_name,
                               start_date=start_date,
                               end_date=end_date,
                               activities=individual_activities,  # Only show individual activities
                               summary=summary,
                               activity_counts=activity_counts,
                               total_count=len(all_activities),  # Total includes mass emails
                               individual_count=len(individual_activities),
                               mass_email_count=mass_email_count)
    
    # GET request - redirect to index
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=8502, host='0.0.0.0')
