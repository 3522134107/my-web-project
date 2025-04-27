from langchain_community.chat_models.tongyi import ChatTongyi 
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import sqlite3
import re
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

class ScheduleManager:
    def __init__(self):
        self.api_error = False
        self.user_states = {}  # 添加用户状态管理
        try:
            api_key = os.getenv("DASHSCOPE_API_KEY")
            
            self.llm = ChatTongyi(
                model="qwen-plus",
                dashscope_api_key=api_key
            )
            
            # 初始化数据库
            self.init_database()
            
            # 创建提示模板
            template = """你是一个专业的日程管理助手。你可以帮助用户管理他们的日程安排，包括添加、修改、删除和查询日程。会话语气要温和，不要使用命令的语气。
            现在的时间是：{input}
            
            当前对话历史：
            {history}
            
            人类：{input}
            AI助手："""
            
            self.prompt = PromptTemplate(
                input_variables=["history", "input"],
                template=template
            )
            
            # 设置对话记忆
            self.memory = ConversationBufferMemory()
            
            # 创建对话链
            self.conversation = ConversationChain(
                llm=self.llm,
                memory=self.memory,
                prompt=self.prompt,
                verbose=True
            )
            
        except Exception as e:
            print(f"初始化 AI 助手时出错：{str(e)}")
            self.api_error = True
    
    def init_database(self):
        """初始化数据库和必要的表"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 创建 Events 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    location TEXT,
                    is_all_day BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            print("数据库初始化成功")
            
        except Exception as e:
            print(f"初始化数据库时出错：{str(e)}")
        finally:
            if conn:
                conn.close()
    
    def parse_schedule(self, message):
        """使用 AI 解析任意格式的日程信息"""
        logger.debug(f"尝试解析日程信息: {message}")
        
        try:
            # 检查是否是简单的修改指令
            time_patterns = {
                r'改到下午(\d{1,2})点(\d{1,2})?分?': lambda m: f"{int(m.group(1))+12:02d}:{int(m.group(2) or '0'):02d}",
                r'改到上午(\d{1,2})点(\d{1,2})?分?': lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or '0'):02d}",
                r'改到(\d{1,2})[:：](\d{1,2})': lambda m: f"{int(m.group(1)):02d}:{int(m.group(2)):02d}",
                r'改到(\d{1,2})点(\d{1,2})?分?': lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or '0'):02d}",
            }
            
            location_pattern = r'改到(.*?)(室|厅|楼|层|会议室|地点|场|中心|$)'
            location_match = re.search(location_pattern, message)
            
            # 如果是位置修改
            if location_match:
                return {
                    'is_schedule': True,
                    'location': location_match.group(1) + location_match.group(2),
                    'title': None,  # 保持原标题
                    'start_time': None,  # 保持原时间
                    'end_time': None,
                    'description': ''
                }
            
            # 如果是时间修改
            for pattern, time_formatter in time_patterns.items():
                time_match = re.search(pattern, message)
                if time_match:
                    time_str = time_formatter(time_match)
                    hour, minute = map(int, time_str.split(':'))
                    
                    # 检查是否指定了日期
                    date = self.parse_date_from_message(message)
                    if not date:
                        date = datetime.now()
                    
                    new_time = datetime(
                        date.year,
                        date.month,
                        date.day,
                        hour,
                        minute
                    )
                    
                    return {
                        'is_schedule': True,
                        'title': None,  # 保持原标题
                        'start_time': new_time,
                        'end_time': new_time + timedelta(hours=1),
                        'location': None,  # 保持原位置
                        'description': ''
                    }
            
            # 如果不是简单修改，使用原有的 AI 解析
            parse_prompt = f"""请帮我解析这段文本中的日程信息，并按以下 JSON 格式返回（仅返回 JSON，不要其他文字）：
{{
    "is_schedule": true/false,  // 这是否是一个日程安排
    "title": "日程标题",
    "start_time": "YYYY-MM-DD HH:mm",  // 开始时间
    "end_time": "YYYY-MM-DD HH:mm",    // 结束时间，如果没有明确指定则设为开始时间后1小时
    "location": "地点",                 // 如果没有则设为"未指定地点"
    "description": "描述"              // 如果没有则设为空字符串
}}

用户输入: {message}
当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

            # 使用 AI 解析
            response = self.llm.invoke(parse_prompt)
            
            try:
                # 尝试解析 JSON 响应
                import json
                schedule_data = json.loads(response.content)
                
                logger.debug(f"AI 解析结果: {schedule_data}")
                
                # 验证是否为日程信息
                if not schedule_data.get('is_schedule', False):
                    logger.debug("AI 判断不是日程信息")
                    return None
                    
                # 转换时间格式
                start_time = datetime.strptime(schedule_data['start_time'], '%Y-%m-%d %H:%M')
                if schedule_data.get('end_time'):
                    end_time = datetime.strptime(schedule_data['end_time'], '%Y-%m-%d %H:%M')
                else:
                    end_time = start_time + timedelta(hours=1)
                
                # 构建标准格式的日程数据
                parsed_data = {
                    'title': schedule_data['title'],
                    'start_time': start_time,
                    'end_time': end_time,
                    'location': schedule_data.get('location', '未指定地点'),
                    'description': schedule_data.get('description', '')
                }
                
                logger.debug(f"成功解析日程数据: {parsed_data}")
                return parsed_data
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析错误: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"处理 AI 响应时出错: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"调用 AI 解析时出错: {str(e)}")
            return None
    
    def save_schedule(self, schedule_data, user_id):
        """保存日程到数据库"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO Events (user_id, title, start_time, end_time, location)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user_id,  # 使用传入的 user_id
                schedule_data['title'],
                schedule_data['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                schedule_data['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
                schedule_data['location']
            ))
            
            conn.commit()
            logger.debug(f"日程保存成功: {schedule_data}")
            return True
        except Exception as e:
            logger.error(f"保存日程时出错：{str(e)}")
            return False
        finally:
            if conn:
                conn.close()
    
    def query_events(self, query_type, user_id, start_date=None, end_date=None):
        """查询日程
        query_type: 查询类型 (today/tomorrow/week/all)
        """
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            current_date = datetime.now().date()
            
            if query_type == "today":
                start = current_date.strftime('%Y-%m-%d 00:00:00')
                end = current_date.strftime('%Y-%m-%d 23:59:59')
            elif query_type == "tomorrow":
                tomorrow = current_date + timedelta(days=1)
                start = tomorrow.strftime('%Y-%m-%d 00:00:00')
                end = tomorrow.strftime('%Y-%m-%d 23:59:59')
            elif query_type == "week":
                start = current_date.strftime('%Y-%m-%d 00:00:00')
                end = (current_date + timedelta(days=7)).strftime('%Y-%m-%d 23:59:59')
            elif query_type == "custom":
                start = start_date.strftime('%Y-%m-%d 00:00:00')
                end = end_date.strftime('%Y-%m-%d 23:59:59')
            else:  # all
                cursor.execute('''
                    SELECT title, start_time, end_time, location, description
                    FROM Events
                    WHERE user_id = ?
                    ORDER BY start_time
                ''', (user_id,))
                return cursor.fetchall()

            cursor.execute('''
                SELECT title, start_time, end_time, location, description
                FROM Events
                WHERE start_time BETWEEN ? AND ?
                AND user_id = ?
                ORDER BY start_time
            ''', (start, end, user_id))
            
            return cursor.fetchall()
            
        except Exception as e:
            logger.error(f"查询日程时出错：{str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def format_events_response(self, events):
        """格式化日程查询结果的响应"""
        if not events:
            return "没有找到相关日程安排。"
        
        response = "为您找到以下日程安排：\n"
        for event in events:
            title, start_time, end_time, location, description = event
            start = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            
            response += f"\n📅 {title}\n"
            response += f"⏰ {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')}\n"
            if location and location != "未指定地点":
                response += f"📍 {location}\n"
            if description:
                response += f"📝 {description}\n"
            response += "-------------------"
        
        return response

    def process_message(self, message, user_id):
        """处理用户消息并返回响应"""
        try:
            logger.debug(f"收到消息: {message}")
            
            # 添加智能查询处理
            query_patterns = [
                r"(什么时候|何时|哪天).*?(有|的|是).*?(课|课程|会议|安排)",
                r"(\d{1,2})月.*?(有|的).*?(课|课程|会议|安排)",
                r"(今天|明天|下周|这周|本周).*?(有|的).*?(课|课程|会议|安排)"
            ]
            
            is_query = any(re.search(pattern, message) for pattern in query_patterns)
            
            if is_query:
                # 使用 LangChain 解析查询意图
                parse_prompt = f"""请分析这个查询请求，并返回以下 JSON 格式的结果（仅返回 JSON）：
{{
    "keywords": ["关键词1", "关键词2"],  // 提取相关的搜索关键词
    "time_range": {{
        "type": "specific_month" | "specific_date" | "this_week" | "next_week" | "all",
        "month": 数字,  // 如果是按月查询
        "date": "YYYY-MM-DD"  // 如果是具体日期
    }}
}}

用户查询: {message}
当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

                response = self.llm.invoke(parse_prompt)
                
                try:
                    import json
                    query_intent = json.loads(response.content)
                    
                    # 根据意图执行查询
                    events = []
                    if query_intent.get('keywords'):
                        events = self.search_events_by_keywords(query_intent['keywords'], user_id)
                    
                    # 根据时间范围过滤结果
                    time_range = query_intent.get('time_range', {})
                    if time_range.get('type') == 'specific_month':
                        month = time_range.get('month')
                        if month:
                            year = datetime.now().year
                            events = [e for e in events if datetime.strptime(e[1], '%Y-%m-%d %H:%M:%S').month == month]
                    elif time_range.get('type') == 'specific_date':
                        date = time_range.get('date')
                        if date:
                            target_date = datetime.strptime(date, '%Y-%m-%d').date()
                            events = [e for e in events if datetime.strptime(e[1], '%Y-%m-%d %H:%M:%S').date() == target_date]
                    
                    return self.format_events_response(events)
                    
                except json.JSONDecodeError:
                    logger.error("AI 响应解析失败")
                    
            # 检查是否是序号选择（用于修改或删除）
            number_match = re.match(r'^(\d+)$', message.strip())
            if number_match:
                user_state = self.user_states.get(user_id, {})
                events = user_state.get('events', [])
                operation = user_state.get('operation')  # 新增：记录操作类型
                
                if not events:
                    return "抱歉，请先告诉我您要操作哪个日程。"
                
                selected_index = int(number_match.group(1)) - 1
                if selected_index < 0 or selected_index >= len(events):
                    return "抱歉，请输入正确的序号。"
                
                selected_event = events[selected_index]
                
                # 根据操作类型处理
                if operation == 'delete':
                    # 执行删除操作
                    success = self.delete_event(selected_event[0], user_id)
                    # 清除状态
                    self.user_states[user_id] = {}
                    if success:
                        return f"已删除日程：\n📅 {selected_event[1]}\n⏰ {datetime.strptime(selected_event[2], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')}"
                    else:
                        return "删除日程失败，请稍后重试。"
                elif operation == 'modify':
                    # 原有的修改逻辑
                    self.user_states[user_id]['selected_event'] = selected_event
                    return (f"好的，您要如何修改这个日程？\n"
                           f"当前日程信息：\n"
                           f"📅 {selected_event[1]}\n"
                           f"⏰ {datetime.strptime(selected_event[2], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')}\n"
                           f"📍 {selected_event[4] if selected_event[4] else '未指定地点'}\n\n"
                           f"您可以：\n"
                           f"- 改到下午3点\n"
                           f"- 改成线上会议\n"
                           f"- 地点改到会议室A\n"
                           f"- 改到明天下午2点")
                
                return "请指定要执行的操作。"

            # 检查是否是删除请求
            delete_patterns = [
                r"删除.*日程",
                r"删掉.*日程",
                r"取消.*日程",
                r"删除.*安排",
                r"删掉.*安排",
                r"取消.*安排",
                r"删.*",
                r"取消.*"
            ]
            
            is_delete_request = any(re.search(pattern, message) for pattern in delete_patterns)
            
            if is_delete_request:
                date = self.parse_date_from_message(message)
                if not date:
                    return "请指定要删除哪一天的日程。"
                
                events = self.find_event_by_time(date, user_id)
                if not events:
                    return f"未找到{date.strftime('%Y-%m-%d')}的日程。"
                elif len(events) > 1:
                    # 保存查询结果到用户状态
                    self.user_states[user_id] = {
                        'events': events,
                        'operation': 'delete'  # 标记操作类型为删除
                    }
                    
                    response = "找到多个日程，请选择要删除哪一个：\n"
                    for idx, event in enumerate(events, 1):
                        response += f"{idx}. {event[1]} ({datetime.strptime(event[2], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')})\n"
                    return response
                else:
                    # 只有一个日程时直接删除
                    event = events[0]
                    if self.delete_event(event[0], user_id):
                        return f"已删除日程：\n📅 {event[1]}\n⏰ {datetime.strptime(event[2], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')}"
                    else:
                        return "删除日程失败，请稍后重试。"
            
            # 检查是否是修改请求
            modify_patterns = [
                r"修改.*日程",
                r"更改.*日程",
                r"调整.*日程",
                r"改一下.*日程",
                r"把.*日程.*改成",
                r"将.*日程.*改为",
                # 添加更多常见的修改表达方式
                r"修改.*行程",
                r"更改.*行程",
                r"调整.*行程",
                r"改.*时间",
                r"改.*地点",
                r"换.*时间",
                r"换.*地点",
                r"改到.*",
                r"调到.*",
                r"改成.*",
                r"改为.*"
            ]
            
            is_modify_request = (
                any(re.search(pattern, message) for pattern in modify_patterns) or
                ("改" in message and any(time_word in message for time_word in ["明天", "今天", "后天", "早上", "下午", "晚上"]))
            )
            
            if is_modify_request:
                # 检查是否有选中的事件需要修改
                user_state = self.user_states.get(user_id, {})
                selected_event = user_state.get('selected_event')
                
                if selected_event:
                    # 处理对已选中事件的修改
                    updated_data = self.parse_schedule(message)
                    if updated_data:
                        success, msg = self.update_event(selected_event[0], updated_data, user_id)
                        # 清除状态
                        self.user_states[user_id] = {}
                        return msg if not success else f"已成功修改日程：\n📅 {updated_data['title']}\n⏰ {updated_data['start_time'].strftime('%Y-%m-%d %H:%M')} - {updated_data['end_time'].strftime('%H:%M')}\n📍 {updated_data['location']}"
                
                # 如果没有选中的事件，继续原有的修改流程
                title_match = (
                    re.search(r"「(.+?)」", message) or
                    re.search(r'"(.+?)"', message) or
                    re.search(r'"(.+?)"', message)
                )
                
                if not title_match:
                    date = self.parse_date_from_message(message)
                    if not date:
                        return "请指定要修改哪个日程，可以用引号括起来或者指定具体时间。"
                    
                    events = self.find_event_by_time(date, user_id)
                    if not events:
                        return f"未找到{date.strftime('%Y-%m-%d')}的日程。"
                    elif len(events) > 1:
                        # 保存查询结果到用户状态
                        self.user_states[user_id] = {'events': events}
                        
                        response = "找到多个日程，请指定要修改哪一个：\n"
                        for idx, event in enumerate(events, 1):
                            response += f"{idx}. {event[1]} ({datetime.strptime(event[2], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')})\n"
                        return response
                    else:
                        event = events[0]
                        updated_data = self.parse_schedule(message)
                        if not updated_data:
                            return "无法解析要修改的内容，请确保包含新的日程信息。"
                        
                        success, msg = self.update_event(event[0], updated_data, user_id)
                        return msg if not success else f"已成功修改日程：\n📅 {updated_data['title']}\n⏰ {updated_data['start_time'].strftime('%Y-%m-%d %H:%M')} - {updated_data['end_time'].strftime('%H:%M')}\n📍 {updated_data['location']}"
            
            # 检查是否是添加日程的请求
            schedule_data = self.parse_schedule(message)
            if schedule_data:
                if self.save_schedule(schedule_data, user_id):
                    return f"已成功添加日程：\n📅 {schedule_data['title']}\n⏰ {schedule_data['start_time'].strftime('%Y-%m-%d %H:%M')} - {schedule_data['end_time'].strftime('%H:%M')}\n📍 {schedule_data['location']}"
                else:
                    return "添加日程时出错，请稍后重试。"

            # 检查是否是关键字搜索
            if "搜索" in message or "查找" in message or "查询" in message:
                keywords = self.extract_keywords(message)
                if keywords:
                    events = self.search_events_by_keywords(keywords, user_id)
                    return self.format_events_response(events)

            # 检查是否是日期查询
            query_patterns = {
                "today": r"(今天|今日).*日程",
                "tomorrow": r"(明天|明日).*日程",
                "week": r"(本周|这周|一周|未来一周).*日程",
                "all": r"(所有|全��).*日程",
                "date": r"(\d{4}年)?(\d{1,2})月(\d{1,2})日.*日程",
                "month": r"(\d{4}年)?(\d{1,2})月.*日程"
            }
            
            # 检查是否是查询请求
            for query_type, pattern in query_patterns.items():
                if re.search(pattern, message):
                    events = []
                    if query_type in ["today", "tomorrow", "week", "all"]:
                        events = self.query_events(query_type, user_id)
                    elif query_type == "date":
                        # 解析具体日期
                        date_match = re.search(r"(\d{4}年)?(\d{1,2})月(\d{1,2})日", message)
                        if date_match:
                            year = int(date_match.group(1)[:-1]) if date_match.group(1) else datetime.now().year
                            month = int(date_match.group(2))
                            day = int(date_match.group(3))
                            target_date = datetime(year, month, day).date()
                            events = self.query_events("custom", user_id, target_date, target_date)
                    elif query_type == "month":
                        # 解析月份
                        month_match = re.search(r"(\d{4}年)?(\d{1,2})月", message)
                        if month_match:
                            year = int(month_match.group(1)[:-1]) if month_match.group(1) else datetime.now().year
                            month = int(month_match.group(2))
                            start_date = datetime(year, month, 1).date()
                            if month == 12:
                                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
                            else:
                                end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
                            events = self.query_events("custom", user_id, start_date, end_date)
                    
                    return self.format_events_response(events)

            # 如果不是查询请求，使用 AI 助手处理
            if self.api_error:
                return "抱歉，AI 助手当前不可用，但您仍然可以使用日历功能来管理日程。"
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message_with_time = f"当前时间：{current_time}\n用户问题：{message}"
            
            response = self.conversation.predict(input=message_with_time)
            return response
            
        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}")
            return f"处理消息时出错：{str(e)}"
    
    def get_month_events(self, year, month, user_id):
        """获取指定月份的所有事件"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 构建日期范围
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year + 1}-01-01"
            else:
                end_date = f"{year}-{month + 1:02d}-01"
            
            print(f"查询日期范围: {start_date} 到 {end_date}")  # 调试输出
            
            cursor.execute('''
                SELECT title, start_time, end_time, description, location
                FROM Events
                WHERE date(start_time) >= date(?) AND date(start_time) < date(?)
                AND user_id = ?
                ORDER BY start_time
            ''', (start_date, end_date, user_id))
            
            events = []
            for row in cursor.fetchall():
                event = {
                    'title': row[0],
                    'start_time': datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S'),
                    'end_time': datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S'),
                    'description': row[3],
                    'location': row[4]
                }
                events.append(event)
                print(f"找到事件: {event}")  # 调试输出
            
            return events
            
        except Exception as e:
            print(f"获取月度事件时出错：{str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def delete_test_events(self):
        """只删除测试日程（标题包含'测试会议'的日程）"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 只删除标题包含"测试会议"的日程
            cursor.execute("DELETE FROM Events WHERE title LIKE '%测试会议%'")
            conn.commit()
            
            deleted_count = cursor.rowcount
            logger.debug(f"已删除 {deleted_count} 个测试日程")
            return True
        except Exception as e:
            logger.error(f"删除测试日程时出错：{str(e)}")
            return False
        finally:
            if conn:
                conn.close()
    
    def get_all_events(self):
        events = []
        # 将您的日程数据转换为 FullCalendar 可以理解的格式
        # 例如:
        for schedule in self.schedules:
            event = {
                'title': schedule.title,
                'start': schedule.start_time.isoformat(),
                'end': schedule.end_time.isoformat()
            }
            events.append(event)
        return events

    def extract_keywords(self, message):
        """从用户消息中提取搜索关键词"""
        # 移除常见的搜索词
        search_terms = ["搜索", "查找", "查询", "相关", "日程", "的"]
        for term in search_terms:
            message = message.replace(term, "")
        
        # 分词并返回关键词
        keywords = message.strip().split()
        return [keyword for keyword in keywords if keyword]

    def search_events_by_keywords(self, keywords, user_id):
        """根据关键词智能搜索日程"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 构建基础查询
            query = """
                SELECT title, start_time, end_time, location, description
                FROM Events
                WHERE user_id = ?
            """
            params = [user_id]
            
            # 构建智能搜索条件
            conditions = []
            for keyword in keywords:
                conditions.append("""
                    (title LIKE ? OR description LIKE ? OR location LIKE ?)
                """)
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
            
            if conditions:
                query += " AND (" + " OR ".join(conditions) + ")"
            
            # 按开始时间排序
            query += " ORDER BY start_time"
            
            cursor.execute(query, params)
            return cursor.fetchall()
            
        except Exception as e:
            logger.error(f"关键词搜索日程时出错：{str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def add_event(self, event_data, user_id):
        conn = sqlite3.connect('schedule_manager.db')
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO Events (user_id, title, start_time, end_time, description, location)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, event_data['title'], event_data['start_time'], 
              event_data['end_time'], event_data['description'], event_data['location']))
        
        conn.commit()
        conn.close()

    def delete_events_by_date(self, date_str, user_id):
        """删除指定日期的所有日程"""
        try:
            # 将日期字符串转换为标准格式（YYYY-MM-DD）
            date_obj = self.parse_date(date_str)
            
            date_start = date_obj.strftime("%Y-%m-%d 00:00:00")
            date_end = date_obj.strftime("%Y-%m-%d 23:59:59")
            
            with sqlite3.connect('schedule_manager.db') as conn:
                cursor = conn.cursor()
                
                # 先获取要删除的日程列表
                cursor.execute('''
                    SELECT event_id, title, start_time, end_time
                    FROM Events
                    WHERE user_id = ?
                    AND date(start_time) = date(?)
                ''', (user_id, date_start))
                
                events_to_delete = cursor.fetchall()
                
                if not events_to_delete:
                    logger.info(f"未找到{date_str}的日程")
                    return 0
                    
                # 执行删除
                cursor.execute('''
                    DELETE FROM Events
                    WHERE user_id = ?
                    AND date(start_time) = date(?)
                ''', (user_id, date_start))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                # 记录删除的日程信息
                logger.info(f"已删除{date_str}的{deleted_count}个日程")
                for event in events_to_delete:
                    logger.debug(f"删除日程: {event[1]} ({event[2]} - {event[3]})")
                    
                return deleted_count
                
        except Exception as e:
            logger.error(f"删除指定日期日程时出错：{str(e)}")
            return 0

    def parse_date(self, date_str):
        """解析各种格式的日期字符串"""
        # 处理"12月25日"这样的格式
        match = re.search(r'(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            month, day = map(int, match.groups())
            # 使用当前年份或上下文中的年份
            year = datetime.now().year
            return datetime(year, month, day)
        
        # 可以添加更多日期格式的解析...
        
        raise ValueError(f"无法解析日期格式：{date_str}")

    def update_event(self, event_id, updated_data, user_id):
        """更新指定的日程"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 首先获取原有事件数据
            cursor.execute('''
                SELECT title, start_time, end_time, location
                FROM Events 
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            
            original_event = cursor.fetchone()
            if not original_event:
                return False, "未找到指定的日程"
            
            # 合并更新数据，保留未修改的原值
            title = updated_data.get('title') or original_event[0]
            start_time = updated_data.get('start_time') or datetime.strptime(original_event[1], '%Y-%m-%d %H:%M:%S')
            end_time = updated_data.get('end_time') or datetime.strptime(original_event[2], '%Y-%m-%d %H:%M:%S')
            location = updated_data.get('location') or original_event[3]
            
            # 执行更新
            cursor.execute('''
                UPDATE Events 
                SET title = ?,
                    start_time = ?,
                    end_time = ?,
                    location = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ? AND user_id = ?
            ''', (
                title,
                start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time.strftime('%Y-%m-%d %H:%M:%S'),
                location,
                event_id,
                user_id
            ))
            
            conn.commit()
            return True, "日程更新成功"
            
        except Exception as e:
            logger.error(f"更新日程时出错：{str(e)}")
            return False, f"更新日程出错：{str(e)}"
        finally:
            if conn:
                conn.close()

    def find_event_by_title_and_time(self, title, date, user_id):
        """根据标题和��期查找日程"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 构建日期范围
            date_start = f"{date.strftime('%Y-%m-%d')} 00:00:00"
            date_end = f"{date.strftime('%Y-%m-%d')} 23:59:59"
            
            cursor.execute('''
                SELECT event_id, title, start_time, end_time, location, description
                FROM Events
                WHERE user_id = ?
                AND title LIKE ?
                AND start_time BETWEEN ? AND ?
            ''', (user_id, f"%{title}%", date_start, date_end))
            
            events = cursor.fetchall()
            return events
            
        except Exception as e:
            logger.error(f"查找日程时出错：{str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def parse_date_from_message(self, message):
        """从用户消息中解析日期和时间"""
        try:
            current_date = datetime.now()
            
            # 处理相对日期
            if "明天" in message:
                target_date = current_date + timedelta(days=1)
            elif "后天" in message:
                target_date = current_date + timedelta(days=2)
            elif "今天" in message:
                target_date = current_date
            else:
                # 处理具体日期格式
                date_match = re.search(r"(\d{4}年)?(\d{1,2})月(\d{1,2})日", message)
                if date_match:
                    year = int(date_match.group(1)[:-1]) if date_match.group(1) else current_date.year
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))
                    target_date = datetime(year, month, day)
                else:
                    # 如果没有找到日期，使用当前日期
                    target_date = current_date
            
            # 处理具体时间
            time_patterns = [
                (r"(\d{1,2})点(\d{1,2})?分?", lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or '0'):02d}"),
                (r"(\d{1,2}):(\d{1,2})", lambda m: f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"),
                (r"早上(\d{1,2})点(\d{1,2})?分?", lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or '0'):02d}"),
                (r"上午(\d{1,2})点(\d{1,2})?分?", lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or '0'):02d}"),
                (r"下午(\d{1,2})点(\d{1,2})?分?", lambda m: f"{int(m.group(1))+12:02d}:{int(m.group(2) or '0'):02d}"),
                (r"晚上(\d{1,2})点(\d{1,2})?分?", lambda m: f"{int(m.group(1))+12:02d}:{int(m.group(2) or '0'):02d}")
            ]
            
            for pattern, time_formatter in time_patterns:
                time_match = re.search(pattern, message)
                if time_match:
                    time_str = time_formatter(time_match)
                    hour, minute = map(int, time_str.split(':'))
                    return datetime(
                        target_date.year,
                        target_date.month,
                        target_date.day,
                        hour,
                        minute
                    )
            
            # 如果没有具体时间，返回整个日期
            return target_date
            
        except Exception as e:
            logger.error(f"解析日期时间出错: {str(e)}")
            return None

    def find_event_by_time(self, date, user_id):
        """根据日期查找日程"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            # 构建日期范围
            date_start = f"{date.strftime('%Y-%m-%d')} 00:00:00"
            date_end = f"{date.strftime('%Y-%m-%d')} 23:59:59"
            
            cursor.execute('''
                SELECT event_id, title, start_time, end_time, location, description
                FROM Events
                WHERE user_id = ?
                AND start_time BETWEEN ? AND ?
                ORDER BY start_time
            ''', (user_id, date_start, date_end))
            
            events = cursor.fetchall()
            return events
            
        except Exception as e:
            logger.error(f"查找日程时出错：{str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def delete_event(self, event_id, user_id):
        """删除指定的日程"""
        try:
            conn = sqlite3.connect('schedule_manager.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM Events 
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"删除日程时出错：{str(e)}")
            return False
        finally:
            if conn:
                conn.close()