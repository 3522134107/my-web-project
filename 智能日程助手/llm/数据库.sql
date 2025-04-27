/*1. 需求
//- 用户管理：注册、登录、个人信息管理。
//- 日程管理：创建、编辑、删除日程；设置提醒；查看日程列表。
//- 共享与协作：邀请他人参加日程；查看他人的日程。
//- 分析与报告：生成日程统计报告；分析用户行为模式。

 //2. 设计数据模型
*/


 
 




/*a. 用户表 (Users)
- `user_id` (主键, 唯一标识每个用户)
- `username` (用户名)
- `email` (邮箱地址，用于登录)
- `password_hash` (密码哈希值，安全存储密码)
- `created_at` (账户创建时间
*/
CREATE DATABASE ScheduleManager;
USE ScheduleManager;
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


/*b. 日程表 (Events)
- `event_id` (主键, 唯一日程标识符)
- `user_id` (外键, 关联到用户表)
- `title` (日程标题)
- `description` (描述)
- `start_time` (开始时间)
- `end_time` (结束时间)
- `location` (地点)
- `is_all_day` (是否全天事件)
- `created_at` (创建时间)
- `updated_at` (最后更新时间)
*/
CREATE TABLE Events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    location VARCHAR(255),
    is_all_day BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);


/*c. 提醒表 (Reminders)
- `reminder_id` (主键, 唯一标识每个提醒)
- `event_id` (外键, 关联到日程表)
- `reminder_time` (提醒时间)
- `method` (提醒方式，如短信、邮件等)
*/
CREATE TABLE Reminders (
    reminder_id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    reminder_time DATETIME NOT NULL,
    method VARCHAR(50) NOT NULL,
    FOREIGN KEY (event_id) REFERENCES Events(event_id)
);


/*d. 参与者表 (Participants)
- `participant_id` (主键, 唯一标识每个参与者)
- `event_id` (外键, 关联到日程表)
- `user_id` (外键, 关联到用户表)
- `status` (状态，如待确认、已接受、已拒绝)*/
CREATE TABLE Participants (
    participant_id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    user_id INT NOT NULL,
    status ENUM('pending', 'accepted', 'declined') DEFAULT 'pending',
    FOREIGN KEY (event_id) REFERENCES Events(event_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);


/*e. 日程标签表 (EventTags)
- `tag_id` (主键, 唯一标识每个标签)
- `event_id` (外键, 关联到日程表)
- `tag_name` (标签名称)
*/
CREATE TABLE EventTags (
    tag_id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    tag_name VARCHAR(50) NOT NULL,
    FOREIGN KEY (event_id) REFERENCES Events(event_id)
);
 
 
 /*5. 索引优化*/
CREATE INDEX idx_start_time ON Events(start_time);
CREATE INDEX idx_end_time ON Events(end_time);










