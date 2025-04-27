from flask import Blueprint, render_template, jsonify
from datetime import datetime, timedelta
import sqlite3

calendar_view = Blueprint('calendar_view', __name__)

class CalendarDisplay:
    def __init__(self, db_path="schedules.db"):
        self.db_path = db_path

    def get_schedules_by_date_range(self, start_date, end_date):
        """获取指定日期范围内的所有日程"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT id, title, description, start_time, end_time, priority, status
        FROM schedules 
        WHERE start_time BETWEEN ? AND ?
        ORDER BY start_time ASC
        """
        
        cursor.execute(query, (start_date, end_date))
        schedules = cursor.fetchall()
        
        # 转换为字典列表
        result = []
        for schedule in schedules:
            result.append({
                'id': schedule[0],
                'title': schedule[1],
                'description': schedule[2],
                'start': schedule[3],
                'end': schedule[4],
                'priority': schedule[5],
                'status': schedule[6],
                'className': f'priority-{schedule[5]}'  # 用于前端显示不同优先级的样式
            })
            
        conn.close()
        return result

    def get_schedule_details(self, schedule_id):
        """获取单个日程的详细信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        schedule = cursor.fetchone()
        
        conn.close()
        
        if schedule:
            return {
                'id': schedule[0],
                'title': schedule[1],
                'description': schedule[2],
                'start_time': schedule[3],
                'end_time': schedule[4],
                'priority': schedule[5],
                'status': schedule[6]
            }
        return None

@calendar_view.route('/calendar')
def show_calendar():
    """显示日历页面"""
    return render_template('calendar_display.html')

@calendar_view.route('/api/calendar/events')
def get_events():
    """获取日历事件的API端点"""
    try:
        # 获取当前月份的开始和结束日期
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        end_date = (end_date - timedelta(days=1)).strftime('%Y-%m-%d')
        
        calendar = CalendarDisplay()
        events = calendar.get_schedules_by_date_range(start_date, end_date)
        
        return jsonify({
            'status': 'success',
            'data': events
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@calendar_view.route('/api/calendar/event/<int:event_id>')
def get_event(event_id):
    """获取单个事件详情的API端点"""
    try:
        calendar = CalendarDisplay()
        event = calendar.get_schedule_details(event_id)
        
        if event:
            return jsonify({
                'status': 'success',
                'data': event
            })
        return jsonify({
            'status': 'error',
            'message': 'Event not found'
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500