from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from schedule_manager import ScheduleManager
from datetime import datetime, timedelta
import calendar
import sqlite3
import logging
import re
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
from typing import List, Dict
import json

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your_secret_key'
schedule_manager = ScheduleManager()

css = """
<style>
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
    }
    
    .message {
        margin: 15px 0;
        padding: 15px 20px;
        border-radius: 10px;
        line-height: 1.5;
    }
    
    .user-message {
        background: #e3f2fd;
        margin-left: 50px;
    }
    
    .assistant-message {
        background: #f5f5f5;
        margin-right: 50px;
    }
    
    .input-container {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 20px;
        background: white;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
    }
    
    textarea {
        width: 100%;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 5px;
        font-size: 16px;
        resize: none;
    }
    
    button {
        background: #2196F3;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        cursor: pointer;
        font-size: 16px;
        transition: background 0.3s;
    }
    
    button:hover {
        background: #1976D2;
    }
</style>
"""

def parse_date_from_message(message):
    """从消息中解析日期"""
    try:
        # 处理"今天"、"明天"、"后天"等相对日期
        if "今天" in message:
            return datetime.now()
        elif "明天" in message:
            return datetime.now() + timedelta(days=1)
        elif "后天" in message:
            return datetime.now() + timedelta(days=2)
        
        # 原有的日期格式处理
        patterns = [
            r'(\d{1,2})月(\d{1,2})日',    # 12月25日
            r'(\d{1,2})月(\d{1,2})号',    # 12月25号
            r'(\d{1,2})/(\d{1,2})',      # 12/25
            r'(\d{1,2})-(\d{1,2})',      # 12-25
            r'(\d{1,2})\.(\d{1,2})'      # 12.25
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                month, day = map(int, match.groups())
                year = datetime.now().year
                return datetime(year, month, day)
        return None
    except Exception as e:
        logger.error(f"解析日期出错: {str(e)}")
        return None

def format_events_message(events):
    """格式化日程信息为可读消息"""
    if not events:
        return "未找到相关日程。"
    
    message = "为您找到以下日程安排：\n\n"
    for event in events:
        message += f"📅 {event['title']}\n"
        message += f"⏰ {event['start_time']} - {event['end_time']}\n"
        if event['location'] and event['location'] != '未指定地点':
            message += f"📍 {event['location']}\n"
        if event['description']:
            message += f"📝 {event['description']}\n"
        message += "-------------------\n"
    return message

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            description TEXT,
            location TEXT,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        )
    ''')
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('schedule_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('密码不匹配', 'danger')
            return render_template('register.html')
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            if cur.execute('SELECT 1 FROM Users WHERE username = ?', (username,)).fetchone():
                flash('用户名已存在', 'danger')
                return render_template('register.html')
            
            password_hash = generate_password_hash(password)
            cur.execute('INSERT INTO Users (username, password_hash) VALUES (?, ?)',
                       (username, password_hash))
            conn.commit()
            flash('注册成功！请登录', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('注册失败，请稍后重试', 'danger')
            logger.error(f"注册错误: {str(e)}")
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        user = cur.execute('SELECT * FROM Users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = username
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('登录失败。用户名或密码错误。', 'danger')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功退出登录', 'info')
    return redirect(url_for('login'))

def get_chat_history() -> List[Dict[str, str]]:
    """获取聊天历史记录"""
    if 'chat_history' not in session:
        session['chat_history'] = []
    return session['chat_history']

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        user_id = session['user_id']
        logger.debug(f"收到用户 {user_id} 的消息: {user_message}")

        # 添加用户消息到历史记录
        chat_history = get_chat_history()
        chat_history.append({
            "role": "user",
            "content": user_message
        })

        # 使用 schedule_manager 处理消息
        response = schedule_manager.process_message(user_message, user_id)

        # 添加助手回复到历史记录
        chat_history.append({
            "role": "assistant",
            "content": response
        })

        # 保存聊天历史
        session['chat_history'] = chat_history

        return jsonify({'response': response})

    except Exception as e:
        logger.error(f"处理聊天请求时出错: {str(e)}")
        return jsonify({
            'response': "抱歉，系统暂时无法处理您的请求。请稍后重试或使用日历功能来管理日程。"
        })

@app.route('/get_calendar', methods=['POST'])
@login_required
def get_calendar():
    data = request.json
    year = int(data.get('year', datetime.now().year))
    month = int(data.get('month', datetime.now().month))
    
    # 获取特定用户的日历数据
    events = schedule_manager.get_month_events(year, month, session['user_id'])
    
    # 获取日历数据
    cal = calendar.monthcalendar(year, month)
    
    # 构建日历数据
    calendar_data = {
        'year': year,
        'month': month,
        'days': []
    }
    
    # 打印调试信息
    print(f"获取到的原始事件: {events}")
    
    for week in cal:
        for day in week:
            if day != 0:
                # 筛选当天的事件
                day_events = []
                for event in events:
                    if isinstance(event['start_time'], datetime) and event['start_time'].day == day:
                        day_events.append({
                            'title': event['title'],
                            'start_time': event['start_time'].strftime('%H:%M'),
                            'end_time': event['end_time'].strftime('%H:%M'),
                            'description': event['description'],
                            'location': event['location']
                        })
                
                calendar_data['days'].append({
                    'date': day,
                    'events': day_events
                })
                
                # 打印调试信息
                if day_events:
                    print(f"{year}年{month}月{day}日的事件: {day_events}")
    
    return jsonify({
        'calendar': calendar_data,
        'events': [
            {
                'title': e['title'],
                'start_time': e['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': e['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'description': e['description'],
                'location': e['location']
            } for e in events
        ]
    })

@app.route('/check_events', methods=['GET'])
def check_events():
    try:
        conn = sqlite3.connect('schedule_manager.db')
        cursor = conn.cursor()
        
        # 查询所有事件
        cursor.execute('SELECT * FROM Events')
        events = cursor.fetchall()
        
        # 打印查询结果
        print("数据库中的事件：", events)
        
        return jsonify({
            'status': 'success',
            'events': events
        })
    except Exception as e:
        print(f"查询事件时出错：{str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })
    finally:
        if conn:
            conn.close()

@app.route('/delete_test_events', methods=['GET'])
def delete_test_events():
    try:
        if schedule_manager.delete_test_events():
            return jsonify({
                'status': 'success',
                'message': '测试会议已删除'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '删除测试会议时出错'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/get_events')
def get_events():
    # 从 schedule_manager 获取事件数据
    events = schedule_manager.get_all_events()
    return jsonify(events)

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/clear_chat_history', methods=['POST'])
@login_required
def clear_chat_history():
    session.pop('chat_history', None)
    return jsonify({'status': 'success'})

@app.route('/day_events/<int:year>/<int:month>/<int:day>')
@login_required
def day_events(year, month, day):
    try:
        start_date = datetime(year, month, day).strftime('%Y-%m-%d 00:00:00')
        end_date = datetime(year, month, day).strftime('%Y-%m-%d 23:59:59')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT title, start_time, end_time, location, description
            FROM Events
            WHERE date(start_time) = date(?)
            AND user_id = ?
            ORDER BY start_time
        ''', (start_date, session['user_id']))
        
        events = []
        for row in cur.fetchall():
            events.append({
                'title': row[0],
                'start_time': datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S'),
                'end_time': datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S'),
                'location': row[3],
                'description': row[4]
            })
        
        return render_template('day_events.html',
                             year=year,
                             month=month,
                             day=day,
                             events=events)
    except Exception as e:
        logger.error(f"获取日程详情时出错: {str(e)}")
        flash('获取日程详情时出错', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/get_chart_data')
@login_required
def get_chart_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        user_id = session['user_id']
        
        # 获取当前月份的第一天和最后一天
        today = datetime.now()
        first_day = today.replace(day=1)
        if today.month == 12:
            last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        
        # 获取本月每天的日程数量数据
        line_data = []
        current_date = first_day
        while current_date <= last_day:
            cursor.execute('''
                SELECT COUNT(*) 
                FROM Events 
                WHERE user_id = ? 
                AND date(start_time) = date(?)
            ''', (user_id, current_date.strftime('%Y-%m-%d')))
            count = cursor.fetchone()[0]
            line_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'count': count
            })
            current_date += timedelta(days=1)
        
        # 获取最近7天的数据用于柱状图
        bar_data = []
        total_events = 0
        for i in range(7):
            date = today - timedelta(days=i)
            cursor.execute('''
                SELECT COUNT(*) 
                FROM Events 
                WHERE user_id = ? 
                AND date(start_time) = date(?)
            ''', (user_id, date))
            count = cursor.fetchone()[0]
            total_events += count
            bar_data.append({
                'date': date.strftime('%m-%d'),
                'count': count
            })
        
        # 计算百分比
        if total_events > 0:
            for item in bar_data:
                item['percentage'] = round((item['count'] / total_events) * 100, 2)
        else:
            for item in bar_data:
                item['percentage'] = 0
                
        return jsonify({
            'line_data': line_data,
            'bar_data': bar_data
        })
        
    except Exception as e:
        logger.error(f"获取图表数据时出错：{str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    init_db()  # 初始化数据库
    app.run(debug=True)

# 打印所有路由（用于调试）
for rule in app.url_map.iter_rules():
    print(rule.endpoint)