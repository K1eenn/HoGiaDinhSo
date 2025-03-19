import streamlit as st
from openai import OpenAI
import dotenv
import os
from PIL import Image
from audio_recorder_streamlit import audio_recorder
import base64
from io import BytesIO
import json
import datetime

dotenv.load_dotenv()

# Đường dẫn file lưu trữ dữ liệu
FAMILY_DATA_FILE = "family_data.json"
EVENTS_DATA_FILE = "events_data.json"
NOTES_DATA_FILE = "notes_data.json"
CHAT_HISTORY_FILE = "chat_history.json"  # Thêm file lưu trữ lịch sử chat

# Thiết lập log để debug
import logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler()])
logger = logging.getLogger('family_assistant')

# Chỉ sử dụng một mô hình duy nhất
openai_model = "gpt-4o-mini"

# Thêm các hàm tiện ích cho việc tính toán ngày tháng
def get_date_from_relative_term(term):
    """Chuyển đổi từ mô tả tương đối về ngày thành ngày thực tế"""
    today = datetime.datetime.now().date()
    
    if term in ["hôm nay", "today"]:
        return today
    elif term in ["ngày mai", "mai", "tomorrow"]:
        return today + datetime.timedelta(days=1)
    elif term in ["ngày kia", "day after tomorrow"]:
        return today + datetime.timedelta(days=2)
    elif term in ["hôm qua", "yesterday"]:
        return today - datetime.timedelta(days=1)
    elif "tuần tới" in term or "tuần sau" in term or "next week" in term:
        return today + datetime.timedelta(days=7)
    elif "tuần trước" in term or "last week" in term:
        return today - datetime.timedelta(days=7)
    elif "tháng tới" in term or "tháng sau" in term or "next month" in term:
        # Đơn giản hóa bằng cách thêm 30 ngày
        return today + datetime.timedelta(days=30)
    
    return None

# Tải dữ liệu ban đầu
def load_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Đảm bảo dữ liệu là một từ điển
                if not isinstance(data, dict):
                    print(f"Dữ liệu trong {file_path} không phải từ điển. Khởi tạo lại.")
                    return {}
                return data
        except Exception as e:
            print(f"Lỗi khi đọc {file_path}: {e}")
            return {}
    return {}

def save_data(file_path, data):
    try:
        # Đảm bảo thư mục tồn tại
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Đã lưu dữ liệu vào {file_path}: {len(data)} mục")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi lưu dữ liệu vào {file_path}: {e}")
        st.error(f"Không thể lưu dữ liệu: {e}")
        return False

# Kiểm tra và đảm bảo cấu trúc dữ liệu đúng
def verify_data_structure():
    global family_data, events_data, notes_data, chat_history
    
    # Đảm bảo tất cả dữ liệu là từ điển
    if not isinstance(family_data, dict):
        print("family_data không phải từ điển. Khởi tạo lại.")
        family_data = {}
        
    if not isinstance(events_data, dict):
        print("events_data không phải từ điển. Khởi tạo lại.")
        events_data = {}
        
    if not isinstance(notes_data, dict):
        print("notes_data không phải từ điển. Khởi tạo lại.")
        notes_data = {}
        
    if not isinstance(chat_history, dict):
        print("chat_history không phải từ điển. Khởi tạo lại.")
        chat_history = {}
    
    # Kiểm tra và sửa các dữ liệu thành viên
    members_to_fix = []
    for member_id, member in family_data.items():
        if not isinstance(member, dict):
            members_to_fix.append(member_id)
    
    # Xóa các mục không hợp lệ
    for member_id in members_to_fix:
        del family_data[member_id]
        
    # Lưu lại dữ liệu đã sửa
    save_data(FAMILY_DATA_FILE, family_data)
    save_data(EVENTS_DATA_FILE, events_data)
    save_data(NOTES_DATA_FILE, notes_data)
    save_data(CHAT_HISTORY_FILE, chat_history)

# Tải dữ liệu ban đầu
family_data = load_data(FAMILY_DATA_FILE)
events_data = load_data(EVENTS_DATA_FILE)
notes_data = load_data(NOTES_DATA_FILE)
chat_history = load_data(CHAT_HISTORY_FILE)  # Tải lịch sử chat

# Kiểm tra và sửa cấu trúc dữ liệu
verify_data_structure()

# Hàm chuyển đổi hình ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Hàm tạo tóm tắt lịch sử chat
def generate_chat_summary(messages, api_key):
    """Tạo tóm tắt từ lịch sử trò chuyện"""
    if not messages or len(messages) < 3:  # Cần ít nhất một vài tin nhắn để tạo tóm tắt
        return "Chưa có đủ tin nhắn để tạo tóm tắt."
    
    # Chuẩn bị dữ liệu cho API
    content_texts = []
    for message in messages:
        if "content" in message:
            # Xử lý cả tin nhắn văn bản và hình ảnh
            if isinstance(message["content"], list):
                for content in message["content"]:
                    if content["type"] == "text":
                        content_texts.append(f"{message['role'].upper()}: {content['text']}")
            else:
                content_texts.append(f"{message['role'].upper()}: {message['content']}")
    
    # Ghép tất cả nội dung lại
    full_content = "\n".join(content_texts)
    
    # Gọi API để tạo tóm tắt
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Bạn là trợ lý tạo tóm tắt. Hãy tóm tắt cuộc trò chuyện dưới đây thành 1-3 câu ngắn gọn, tập trung vào các thông tin và yêu cầu chính."},
                {"role": "user", "content": f"Tóm tắt cuộc trò chuyện sau:\n\n{full_content}"}
            ],
            temperature=0.3,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Lỗi khi tạo tóm tắt: {e}")
        return "Không thể tạo tóm tắt vào lúc này."

# Hàm lưu lịch sử trò chuyện cho người dùng hiện tại
def save_chat_history(member_id, messages, summary=None):
    """Lưu lịch sử chat cho một thành viên cụ thể"""
    if member_id not in chat_history:
        chat_history[member_id] = []
    
    # Tạo bản ghi mới
    history_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
        "summary": summary if summary else ""
    }
    
    # Thêm vào lịch sử và giới hạn số lượng
    chat_history[member_id].insert(0, history_entry)  # Thêm vào đầu danh sách
    
    # Giới hạn lưu tối đa 10 cuộc trò chuyện gần nhất
    if len(chat_history[member_id]) > 10:
        chat_history[member_id] = chat_history[member_id][:10]
    
    # Lưu vào file
    save_data(CHAT_HISTORY_FILE, chat_history)

# Hàm stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key, system_prompt="", current_member=None):
    """Hàm tạo và xử lý phản hồi từ mô hình AI"""
    response_message = ""
    
    # Tạo tin nhắn với system prompt
    messages = [{"role": "system", "content": system_prompt}]
    
    # Thêm tất cả tin nhắn trước đó vào cuộc trò chuyện
    for message in st.session_state.messages:
        # Xử lý các tin nhắn hình ảnh
        if any(content["type"] == "image_url" for content in message["content"]):
            # Đối với tin nhắn có hình ảnh, chúng ta cần tạo tin nhắn theo định dạng của OpenAI
            images = [content for content in message["content"] if content["type"] == "image_url"]
            texts = [content for content in message["content"] if content["type"] == "text"]
            
            # Thêm hình ảnh và văn bản vào tin nhắn
            message_content = []
            for image in images:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": image["image_url"]["url"]}
                })
            
            if texts:
                text_content = "\n".join([text["text"] for text in texts])
                message_content.append({
                    "type": "text",
                    "text": text_content
                })
            
            messages.append({
                "role": message["role"],
                "content": message_content
            })
        else:
            # Đối với tin nhắn chỉ có văn bản
            text_content = message["content"][0]["text"] if message["content"] else ""
            messages.append({
                "role": message["role"],
                "content": text_content
            })
    
    try:
        client = OpenAI(api_key=api_key)
        for chunk in client.chat.completions.create(
            model=openai_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        ):
            chunk_text = chunk.choices[0].delta.content or ""
            response_message += chunk_text
            yield chunk_text

        # Hiển thị phản hồi đầy đủ trong log để debug
        logger.info(f"Phản hồi đầy đủ từ trợ lý: {response_message[:200]}...")
        
        # Xử lý phản hồi để trích xuất lệnh
        process_assistant_response(response_message, current_member)
        
        # Thêm phản hồi vào session state
        st.session_state.messages.append({
            "role": "assistant", 
            "content": [
                {
                    "type": "text",
                    "text": response_message,
                }
            ]})
        
        # Nếu đang chat với một thành viên cụ thể, lưu lịch sử
        if current_member:
            # Tạo tóm tắt cuộc trò chuyện
            summary = generate_chat_summary(st.session_state.messages, api_key)
            # Lưu lịch sử
            save_chat_history(current_member, st.session_state.messages, summary)
            
    except Exception as e:
        logger.error(f"Lỗi khi tạo phản hồi từ OpenAI: {e}")
        error_message = f"Có lỗi xảy ra: {str(e)}"
        yield error_message

def process_assistant_response(response, current_member=None):
    """Hàm xử lý lệnh từ phản hồi của trợ lý"""
    try:
        logger.info(f"Xử lý phản hồi của trợ lý, độ dài: {len(response)}")
        
        # Xử lý lệnh thêm sự kiện
        if "##ADD_EVENT:" in response:
            logger.info("Tìm thấy lệnh ADD_EVENT")
            cmd_start = response.index("##ADD_EVENT:") + len("##ADD_EVENT:")
            cmd_end = response.index("##", cmd_start)
            cmd = response[cmd_start:cmd_end].strip()
            
            logger.info(f"Nội dung lệnh ADD_EVENT: {cmd}")
            
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    # Xử lý các từ ngữ tương đối về thời gian
                    logger.info(f"Đang xử lý ngày: {details.get('date', '')}")
                    if details.get('date') and not details['date'][0].isdigit():
                        # Nếu ngày không bắt đầu bằng số, có thể là mô tả tương đối
                        relative_date = get_date_from_relative_term(details['date'].lower())
                        if relative_date:
                            details['date'] = relative_date.strftime("%Y-%m-%d")
                            logger.info(f"Đã chuyển đổi ngày thành: {details['date']}")
                    
                    # Thêm thông tin về người tạo sự kiện
                    if current_member:
                        details['created_by'] = current_member
                    
                    logger.info(f"Thêm sự kiện: {details.get('title', 'Không tiêu đề')}")
                    success = add_event(details)
                    if success:
                        st.success(f"Đã thêm sự kiện: {details.get('title', '')}")
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi khi phân tích JSON cho ADD_EVENT: {e}")
                logger.error(f"Chuỗi JSON gốc: {cmd}")
        
        # Xử lý lệnh UPDATE_EVENT
        if "##UPDATE_EVENT:" in response:
            logger.info("Tìm thấy lệnh UPDATE_EVENT")
            cmd_start = response.index("##UPDATE_EVENT:") + len("##UPDATE_EVENT:")
            cmd_end = response.index("##", cmd_start)
            cmd = response[cmd_start:cmd_end].strip()
            
            logger.info(f"Nội dung lệnh UPDATE_EVENT: {cmd}")
            
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    # Xử lý các từ ngữ tương đối về thời gian
                    if details.get('date') and not details['date'][0].isdigit():
                        # Nếu ngày không bắt đầu bằng số, có thể là mô tả tương đối
                        relative_date = get_date_from_relative_term(details['date'].lower())
                        if relative_date:
                            details['date'] = relative_date.strftime("%Y-%m-%d")
                    
                    logger.info(f"Cập nhật sự kiện: {details.get('title', 'Không tiêu đề')}")
                    success = update_event(details)
                    if success:
                        st.success(f"Đã cập nhật sự kiện: {details.get('title', '')}")
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi khi phân tích JSON cho UPDATE_EVENT: {e}")
        
        # Các lệnh xử lý khác tương tự
        for cmd_type in ["ADD_FAMILY_MEMBER", "UPDATE_PREFERENCE", "DELETE_EVENT", "ADD_NOTE"]:
            cmd_pattern = f"##{cmd_type}:"
            if cmd_pattern in response:
                logger.info(f"Tìm thấy lệnh {cmd_type}")
                try:
                    cmd_start = response.index(cmd_pattern) + len(cmd_pattern)
                    cmd_end = response.index("##", cmd_start)
                    cmd = response[cmd_start:cmd_end].strip()
                    
                    if cmd_type == "DELETE_EVENT":
                        event_id = cmd.strip()
                        delete_event(event_id)
                        st.success(f"Đã xóa sự kiện!")
                    else:
                        details = json.loads(cmd)
                        if isinstance(details, dict):
                            if cmd_type == "ADD_FAMILY_MEMBER":
                                add_family_member(details)
                                st.success(f"Đã thêm thành viên: {details.get('name', '')}")
                            elif cmd_type == "UPDATE_PREFERENCE":
                                update_preference(details)
                                st.success(f"Đã cập nhật sở thích!")
                            elif cmd_type == "ADD_NOTE":
                                # Thêm thông tin về người tạo ghi chú
                                if current_member:
                                    details['created_by'] = current_member
                                add_note(details)
                                st.success(f"Đã thêm ghi chú!")
                except Exception as e:
                    logger.error(f"Lỗi khi xử lý lệnh {cmd_type}: {e}")
    
    except Exception as e:
        logger.error(f"Lỗi khi xử lý phản hồi của trợ lý: {e}")
        logger.error(f"Phản hồi gốc: {response[:100]}...")

# Các hàm quản lý thông tin gia đình
def add_family_member(details):
    member_id = details.get("id") or str(len(family_data) + 1)
    family_data[member_id] = {
        "name": details.get("name", ""),
        "age": details.get("age", ""),
        "preferences": details.get("preferences", {}),
        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(FAMILY_DATA_FILE, family_data)

def update_preference(details):
    member_id = details.get("id")
    preference_key = details.get("key")
    preference_value = details.get("value")
    
    if member_id in family_data and preference_key:
        if "preferences" not in family_data[member_id]:
            family_data[member_id]["preferences"] = {}
        family_data[member_id]["preferences"][preference_key] = preference_value
        save_data(FAMILY_DATA_FILE, family_data)

def add_event(details):
    """Thêm một sự kiện mới vào danh sách sự kiện"""
    try:
        event_id = str(len(events_data) + 1)
        events_data[event_id] = {
            "title": details.get("title", ""),
            "date": details.get("date", ""),
            "time": details.get("time", ""),
            "description": details.get("description", ""),
            "participants": details.get("participants", []),
            "created_by": details.get("created_by", ""),  # Thêm người tạo sự kiện
            "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(EVENTS_DATA_FILE, events_data)
        print(f"Đã thêm sự kiện: {details.get('title', '')} vào {EVENTS_DATA_FILE}")
        print(f"Tổng số sự kiện hiện tại: {len(events_data)}")
        return True
    except Exception as e:
        print(f"Lỗi khi thêm sự kiện: {e}")
        return False

def update_event(details):
    """Cập nhật thông tin về một sự kiện"""
    try:
        event_id = details.get("id")
        if event_id in events_data:
            # Cập nhật các trường được cung cấp
            for key, value in details.items():
                if key != "id" and value is not None:
                    events_data[event_id][key] = value
            
            # Đảm bảo trường created_on được giữ nguyên
            if "created_on" not in events_data[event_id]:
                events_data[event_id]["created_on"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            save_data(EVENTS_DATA_FILE, events_data)
            logger.info(f"Đã cập nhật sự kiện ID={event_id}: {details}")
            return True
        else:
            logger.warning(f"Không tìm thấy sự kiện ID={event_id}")
            return False
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật sự kiện: {e}")
        return False

def delete_event(event_id):
    if event_id in events_data:
        del events_data[event_id]
        save_data(EVENTS_DATA_FILE, events_data)

# Các hàm quản lý ghi chú
def add_note(details):
    note_id = str(len(notes_data) + 1)
    notes_data[note_id] = {
        "title": details.get("title", ""),
        "content": details.get("content", ""),
        "tags": details.get("tags", []),
        "created_by": details.get("created_by", ""),  # Thêm người tạo ghi chú
        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(NOTES_DATA_FILE, notes_data)

# Lọc sự kiện theo người dùng
def filter_events_by_member(member_id=None):
    """Lọc sự kiện theo thành viên cụ thể"""
    if not member_id:
        return events_data  # Trả về tất cả sự kiện nếu không có ID
    
    filtered_events = {}
    for event_id, event in events_data.items():
        # Lọc những sự kiện mà thành viên tạo hoặc tham gia
        if (event.get("created_by") == member_id or 
            (member_id in family_data and 
             family_data[member_id].get("name") in event.get("participants", []))):
            filtered_events[event_id] = event
    
    return filtered_events

# Tạo câu hỏi gợi ý cá nhân hóa
def generate_personalized_questions(member_id=None):
    """Tạo các câu hỏi gợi ý dựa trên sở thích và thông tin của thành viên"""
    if not member_id or member_id not in family_data:
        return []  # Trả về danh sách trống nếu không có ID hoặc không tìm thấy thành viên
    
    import random
    from datetime import datetime
    
    member = family_data[member_id]
    all_questions = []
    
    # Lấy thông tin sở thích
    preferences = member.get("preferences", {})
    member_name = member.get("name", "").split()[0] if member.get("name") else ""
    
    # Tạo các biến thể cách hỏi
    question_starters = [
        "", # Câu trực tiếp
        "Cho tôi biết về ",
        f"{member_name} muốn tìm hiểu về ",
        "Tôi muốn biết ",
        "Hãy nói về ",
        "Thông tin về ",
        f"Chuyện gì đang xảy ra với ",
        "Cập nhật mới nhất về ",
        "Tin tức về ",
        "Có gì mới về ",
    ]
    
    # Hàm tạo câu hỏi ngẫu nhiên từ danh sách chủ đề
    def generate_questions_from_topics(topics, count=3):
        questions = []
        for _ in range(min(count, len(topics))):
            topic = random.choice(topics)
            prefix = random.choice(question_starters)
            # Nếu prefix là chuỗi rỗng, thêm dấu hỏi chấm
            if prefix == "":
                questions.append(f"{topic}?")
            else:
                questions.append(f"{prefix}{topic.lower()}")
            topics.remove(topic)  # Tránh lặp lại chủ đề
        return questions
    
    # --- Xử lý sở thích món ăn ---
    if preferences.get("food"):
        food = preferences["food"]
        food_variations = [
            f"món {food}",
            f"{food}",
            f"nấu {food}",
            f"các loại {food}",
            f"chế biến {food}",
        ]
        food_chosen = random.choice(food_variations)
        
        food_topics = [
            f"Công thức nấu {food_chosen}",
            f"Cách làm {food_chosen} ngon nhất",
            f"Dinh dưỡng trong {food_chosen}",
            f"Các biến tấu của {food_chosen}",
            f"{food_chosen} nổi tiếng ở đâu",
            f"Nguồn gốc của {food_chosen}",
            f"Cách kết hợp {food_chosen} với các món khác",
            f"{food_chosen} có lợi gì cho sức khỏe",
            f"Cách chọn nguyên liệu cho {food_chosen}",
            f"Các nhà hàng nổi tiếng với {food_chosen}",
            f"Xu hướng mới trong cách chế biến {food_chosen}",
            f"Thay thế nguyên liệu khi nấu {food_chosen}"
        ]
        all_questions.extend(generate_questions_from_topics(food_topics, 2))
    
    # --- Xử lý sở thích hobby ---
    if preferences.get("hobby"):
        hobby = preferences["hobby"]
        
        # Danh sách chủ đề thể thao
        sports_topics = [
            "Kết quả trận đấu mới nhất",
            f"Giải {hobby} sắp diễn ra",
            "Cầu thủ xuất sắc nhất tháng này",
            f"Chuyển nhượng mới nhất trong làng {hobby}",
            f"Kỷ lục mới trong {hobby}",
            f"Lịch thi đấu {hobby} tuần này",
            "Scandal thể thao gây sốc",
            "Những khoảnh khắc đáng nhớ",
            f"Cách luyện tập {hobby} hiệu quả",
            f"Trang phục và thiết bị cần thiết cho {hobby}",
            f"Luật chơi mới trong {hobby}",
            f"Những đội bóng đang lên trong {hobby}",
            f"Thống kê thú vị về {hobby}",
            "Dự đoán kết quả trận tới"
        ]
        
        # Danh sách chủ đề âm nhạc
        music_topics = [
            "Bản nhạc đang viral trên TikTok",
            "Album mới ra mắt tháng này",
            f"Nhạc sĩ nổi tiếng trong thể loại {hobby}",
            f"Hòa nhạc {hobby} sắp diễn ra",
            "Các bước học chơi nhạc cụ từ đầu",
            "Nghệ sĩ đang lên của làng nhạc",
            f"Phong cách {hobby} đang thịnh hành",
            "Phần mềm sáng tác nhạc tốt nhất",
            "Ca khúc nổi tiếng nhất tuần qua",
            f"Sự phát triển của dòng nhạc {hobby}",
            "Nhạc cụ nên chọn cho người mới bắt đầu",
            "Mẹo luyện giọng hát hiệu quả"
        ]
        
        # Danh sách chủ đề sách
        reading_topics = [
            "Sách bestseller trong tháng",
            f"Tác giả nổi tiếng trong thể loại {hobby}",
            "Sách hay nên đọc trong mùa này",
            "Tác phẩm được chuyển thể thành phim",
            "Các tựa sách gây tranh cãi",
            f"Xu hướng mới trong văn học {hobby}",
            "Sách giúp cải thiện kỹ năng sống",
            "Những cuốn tự truyện đáng đọc",
            "Sách được giới trẻ yêu thích",
            f"Cốt truyện của quyển {hobby} nổi tiếng",
            "Các tủ sách online miễn phí",
            "Phương pháp đọc sách hiệu quả"
        ]
        
        # Danh sách chủ đề công nghệ
        tech_topics = [
            "Smartphone mới ra mắt",
            "Công nghệ AI đang thay đổi cuộc sống",
            "Xu hướng công nghệ năm nay",
            "Thiết bị thông minh đáng mua",
            f"Phần mềm {hobby} tốt nhất hiện nay",
            "Phát triển mới trong làng công nghệ",
            "Thông tin rò rỉ về sản phẩm sắp ra mắt",
            "Công nghệ xanh và bền vững",
            "Ngôn ngữ lập trình đang được ưa chuộng",
            "Các công cụ làm việc từ xa hiệu quả",
            "Kênh YouTube về công nghệ đáng theo dõi",
            "Cách bảo vệ dữ liệu cá nhân"
        ]
        
        # Danh sách chủ đề nấu ăn
        cooking_topics = [
            "Công thức món ăn nhanh gọn 15 phút",
            "Mẹo vặt trong nhà bếp ít ai biết",
            "Món tráng miệng dễ làm cho người mới",
            "Cách bảo quản thực phẩm lâu hơn",
            "Thiết bị nhà bếp đáng đầu tư",
            "Thực đơn ăn kiêng lành mạnh",
            "Món ngon từ những nguyên liệu sẵn có",
            "Các lỗi thường gặp khi nấu ăn",
            "Cách trang trí món ăn đẹp mắt",
            "Xu hướng ẩm thực đang thịnh hành",
            "Công thức món chay ngon",
            "Cách làm bánh không cần lò nướng"
        ]
        
        # Xác định sở thích cụ thể từ hobby
        hobby_lower = hobby.lower()
        if any(sport in hobby_lower for sport in ["bóng đá", "thể thao", "bóng rổ", "tennis", "football", "soccer", "basketball"]):
            all_questions.extend(generate_questions_from_topics(sports_topics, 2))
        elif any(music in hobby_lower for music in ["âm nhạc", "music", "hát", "ca", "đàn", "nhạc cụ"]):
            all_questions.extend(generate_questions_from_topics(music_topics, 2))
        elif any(read in hobby_lower for read in ["đọc", "sách", "truyện", "reading", "book"]):
            all_questions.extend(generate_questions_from_topics(reading_topics, 2))
        elif any(tech in hobby_lower for tech in ["công nghệ", "máy tính", "technology", "lập trình", "coding"]):
            all_questions.extend(generate_questions_from_topics(tech_topics, 2))
        elif any(cook in hobby_lower for cook in ["nấu ăn", "nấu nướng", "cooking"]):
            all_questions.extend(generate_questions_from_topics(cooking_topics, 2))
        else:
            # Tạo câu hỏi chung cho các sở thích khác
            generic_hobby_topics = [
                f"Các trang web tốt nhất để học {hobby}",
                f"Người nổi tiếng trong lĩnh vực {hobby}",
                f"Sự kiện {hobby} sắp diễn ra",
                f"Cách tiết kiệm chi phí khi tham gia {hobby}",
                f"Thiết bị cần thiết cho {hobby}",
                f"Mẹo để tiến bộ nhanh trong {hobby}",
                f"Nguồn cảm hứng cho {hobby}",
                f"Cộng đồng {hobby} ở địa phương",
                f"Ứng dụng hỗ trợ cho {hobby}",
                f"Khóa học {hobby} trực tuyến",
                f"Thử thách {hobby} đang viral",
                f"Xu hướng mới trong {hobby}"
            ]
            all_questions.extend(generate_questions_from_topics(generic_hobby_topics, 2))
    
    # --- Xử lý màu sắc yêu thích ---
    if preferences.get("color"):
        color = preferences["color"]
        color_topics = [
            f"Ý nghĩa của màu {color}",
            f"Trang phục màu {color} phù hợp với dịp nào",
            f"Cách kết hợp màu {color} trong trang trí nhà",
            f"Màu {color} ảnh hưởng gì đến tâm lý",
            f"Trang phục tông màu {color} cho mùa này",
            f"Các màu kết hợp đẹp với {color}",
            f"Biến thể của màu {color} trong thiết kế",
            f"Sự phổ biến của màu {color} trong văn hóa"
        ]
        all_questions.extend(generate_questions_from_topics(color_topics, 1))
    
    # --- Tạo câu hỏi dựa trên sự kiện ---
    member_events = filter_events_by_member(member_id)
    if member_events:
        # Lấy sự kiện gần nhất (theo ngày)
        try:
            today = datetime.now().date()
            
            sorted_events = sorted(
                member_events.items(),
                key=lambda x: datetime.strptime(x[1].get("date", "3000-01-01"), "%Y-%m-%d").date()
            )
            
            upcoming_events = []
            for event_id, event in sorted_events:
                event_date = datetime.strptime(event.get("date", "3000-01-01"), "%Y-%m-%d").date()
                if event_date >= today:
                    upcoming_events.append((event_id, event))
            
            if upcoming_events:
                # Lấy ngẫu nhiên một sự kiện sắp tới
                event_id, next_event = random.choice(upcoming_events)
                event_title = next_event.get('title', 'sự kiện')
                event_date = datetime.strptime(next_event.get("date", "3000-01-01"), "%Y-%m-%d")
                days_until = (event_date.date() - today).days
                
                # Tạo các loại câu hỏi về sự kiện
                event_topics = [
                    f"Ý tưởng cho {event_title}",
                    f"Chuẩn bị gì cho {event_title}",
                    f"Món quà phù hợp cho {event_title}",
                    f"Điều cần lưu ý trước {event_title}",
                    f"Trang phục phù hợp cho {event_title}",
                    f"Địa điểm phù hợp cho {event_title}",
                    f"Ngân sách hợp lý cho {event_title}"
                ]
                
                # Thêm câu hỏi tùy thuộc vào loại sự kiện
                event_title_lower = event_title.lower()
                if "sinh nhật" in event_title_lower:
                    event_topics.extend([
                        f"Món quà sinh nhật ý nghĩa cho {event_title.split()[-1]}",
                        f"Trang trí tiệc sinh nhật cho {event_title}",
                        f"Trò chơi vui cho {event_title}",
                        "Bánh sinh nhật độc đáo và ý nghĩa"
                    ])
                elif "du lịch" in event_title_lower or "đi" in event_title_lower:
                    event_topics.extend([
                        f"Đồ dùng cần thiết cho {event_title}",
                        f"Địa điểm ăn uống tại {' '.join(event_title_lower.split()[1:])}",
                        f"Kinh nghiệm du lịch {' '.join(event_title_lower.split()[1:])}",
                        "Mẹo tiết kiệm chi phí khi đi du lịch"
                    ])
                elif "họp" in event_title_lower or "meeting" in event_title_lower:
                    event_topics.extend([
                        "Cách chuẩn bị cho cuộc họp hiệu quả",
                        "Kỹ năng thuyết trình ấn tượng",
                        "Tạo bài thuyết trình chuyên nghiệp",
                        "Cách ghi nhớ thông tin trong cuộc họp"
                    ])
                elif "liên hoan" in event_title_lower or "tiệc" in event_title_lower or "party" in event_title_lower:
                    event_topics.extend([
                        "Các món chủ đạo cho bữa tiệc",
                        "Trang phục phù hợp cho bữa tiệc",
                        "Danh sách nhạc sôi động cho bữa tiệc",
                        "Trò chơi giúp không khí bữa tiệc sôi động"
                    ])
                
                # Tạo câu hỏi với thông tin thời gian
                if days_until == 0:
                    event_topics.append(f"Những việc cần làm gấp cho {event_title} hôm nay")
                elif days_until == 1:
                    event_topics.append(f"Chuẩn bị vào phút chót cho {event_title} ngày mai")
                elif days_until < 7:
                    event_topics.append(f"Lịch trình chuẩn bị cho {event_title} trong {days_until} ngày tới")
                else:
                    event_topics.append(f"Kế hoạch dài hạn cho {event_title} vào ngày {event_date.strftime('%d/%m')}")
                
                all_questions.extend(generate_questions_from_topics(event_topics, 2))
        except Exception as e:
            # Bỏ qua nếu có lỗi khi sắp xếp
            pass
    
    # --- Câu hỏi tổng quát theo ngày trong tuần và thời gian ---
    # Lấy thông tin về ngày và giờ hiện tại
    now = datetime.now()
    weekday = now.weekday()  # 0 = Thứ 2, 6 = Chủ nhật
    hour = now.hour
    month = now.month
    day = now.day
    
    # Câu hỏi theo thời gian trong ngày
    time_of_day_topics = []
    if 5 <= hour < 10:
        time_of_day_topics = [
            "Bữa sáng nhanh gọn và đủ dinh dưỡng",
            "Bài tập buổi sáng giúp tỉnh táo",
            "Thói quen buổi sáng của người thành công",
            "Đồ uống thay thế cà phê buổi sáng"
        ]
    elif 10 <= hour < 14:
        time_of_day_topics = [
            "Ý tưởng cho bữa trưa văn phòng",
            "Cách nghỉ trưa hiệu quả",
            "Thực đơn bữa trưa lành mạnh",
            "Đồ ăn nhẹ buổi trưa giúp tỉnh táo"
        ]
    elif 14 <= hour < 18:
        time_of_day_topics = [
            "Cách vượt qua cơn buồn ngủ buổi chiều",
            "Giải pháp tăng năng suất cuối ngày",
            "Thức uống giúp tỉnh táo buổi chiều",
            "Bài tập thư giãn tại bàn làm việc"
        ]
    elif 18 <= hour < 22:
        time_of_day_topics = [
            "Ý tưởng cho bữa tối nhanh gọn",
            "Hoạt động thư giãn buổi tối",
            "Công thức món tối đơn giản",
            "Phim hay nên xem tối nay"
        ]
    else:
        time_of_day_topics = [
            "Mẹo ngủ ngon vào ban đêm",
            "Thực phẩm nên tránh trước khi ngủ",
            "Cách thư giãn giúp dễ ngủ",
            "Đọc sách gì trước khi ngủ"
        ]
    
    # Câu hỏi theo ngày trong tuần
    weekday_topics = []
    if weekday == 0:  # Thứ 2
        weekday_topics = [
            "Cách khởi đầu tuần mới hiệu quả",
            "Lên kế hoạch tuần làm việc",
            "Vượt qua cảm giác uể oải ngày đầu tuần",
            "Thực đơn cả tuần tiết kiệm thời gian"
        ]
    elif weekday == 4:  # Thứ 6
        weekday_topics = [
            "Địa điểm vui chơi cuối tuần",
            "Hoạt động thư giãn cho ngày cuối tuần",
            "Món ngon cho bữa tối thứ 6",
            "Lên kế hoạch cho chuyến đi cuối tuần"
        ]
    elif weekday in [5, 6]:  # Thứ 7, Chủ nhật
        weekday_topics = [
            "Hoạt động gia đình cho ngày cuối tuần",
            "Địa điểm du lịch ngắn ngày",
            "Món ăn đặc biệt cho bữa cuối tuần",
            "Kế hoạch tự chăm sóc bản thân cuối tuần"
        ]
    
    # Câu hỏi theo mùa và sự kiện đặc biệt
    seasonal_topics = []
    # Mùa xuân (tháng 2-4)
    if 2 <= month <= 4:
        seasonal_topics = [
            "Hoạt động ngoài trời mùa xuân",
            "Món ăn phù hợp với thời tiết mùa xuân",
            "Cách chăm sóc sức khỏe mùa giao mùa",
            "Trang phục phù hợp với thời tiết thất thường"
        ]
    # Mùa hè (tháng 5-8)
    elif 5 <= month <= 8:
        seasonal_topics = [
            "Điểm du lịch mùa hè lý tưởng",
            "Cách giải nhiệt ngày nóng",
            "Công thức nước uống mát lành mùa hè",
            "Hoạt động trong nhà cho ngày quá nóng"
        ]
    # Mùa thu (tháng 9-10)
    elif 9 <= month <= 10:
        seasonal_topics = [
            "Địa điểm ngắm lá vàng mùa thu",
            "Món ăn phù hợp với tiết trời se lạnh",
            "Trang phục cho mùa thu",
            "Hoạt động ngoài trời thích hợp mùa thu"
        ]
    # Mùa đông (tháng 11-1)
    else:
        seasonal_topics = [
            "Món ăn ấm nóng cho ngày lạnh",
            "Cách giữ ấm hiệu quả",
            "Hoạt động giải trí trong nhà",
            "Đồ uống nóng cho ngày đông"
        ]
    
    # Tết/Năm mới (tháng 12, tháng 1)
    if month == 12 or month == 1:
        seasonal_topics.extend([
            "Ý tưởng quà tặng năm mới",
            "Món ăn truyền thống dịp Tết",
            "Cách trang trí nhà dịp năm mới",
            "Kế hoạch du lịch dịp Tết"
        ])
    
    # Lễ tình nhân (tháng 2)
    if month == 2 and day <= 14:
        seasonal_topics.extend([
            "Ý tưởng quà Valentine độc đáo",
            "Địa điểm hẹn hò lãng mạn",
            "Món ăn lãng mạn tự làm tại nhà",
            "Hoạt động ý nghĩa ngày Valentine"
        ])
    
    # Thêm các câu hỏi ngẫu nhiên từ các danh sách
    all_questions.extend(generate_questions_from_topics(time_of_day_topics, 1))
    all_questions.extend(generate_questions_from_topics(weekday_topics, 1))
    all_questions.extend(generate_questions_from_topics(seasonal_topics, 1))
    
    # Thêm câu hỏi tổng quát
    general_topics = [
        "Tin tức nổi bật ngày hôm nay",
        "Cách sắp xếp thời gian hiệu quả",
        "Mẹo giữ sức khỏe trong mùa này",
        "Ý tưởng món ăn mới",
        "Hoạt động gia đình cuối tuần",
        "Xu hướng thời trang hiện nay",
        "Phim mới đáng xem",
        "Sách hay nên đọc",
        "Cách tiết kiệm chi tiêu hàng ngày",
        "Kỹ năng cần thiết trong thời đại mới",
        "Công nghệ mới trong năm nay",
        "Bài tập thể dục tại nhà đơn giản",
        "Mẹo tăng cường sức khỏe tinh thần",
        "Cách nấu ăn tiết kiệm thời gian",
        "Địa điểm du lịch phù hợp mùa này"
    ]
    all_questions.extend(generate_questions_from_topics(general_topics, 3))
    
    # Thêm thông tin cá nhân vào một số câu hỏi
    for i in range(len(all_questions)):
        if random.random() < 0.3 and member_name:  # 30% câu hỏi thêm tên người dùng
            all_questions[i] = f"{member_name} muốn biết: {all_questions[i]}"
    
    # Xáo trộn và trả về danh sách
    random.shuffle(all_questions)
    
    # Thêm dấu hỏi chấm nếu câu không có
    for i in range(len(all_questions)):
        if not all_questions[i].endswith("?"):
            all_questions[i] += "?"
    
    # Trả về tối đa 10 câu hỏi
    return all_questions[:10]
    
    # Kết hợp và xáo trộn câu hỏi
    import random
    all_questions = questions + general_questions
    random.shuffle(all_questions)
    
    # Trả về tối đa 10 câu hỏi
    return all_questions[:10]

def main():
    # --- Cấu hình trang ---
    st.set_page_config(
        page_title="Trợ lý Gia đình",
        page_icon="👨‍👩‍👧‍👦",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    # --- Tiêu đề ---
    st.html("""<h1 style="text-align: center; color: #6ca395;">👨‍👩‍👧‍👦 <i>Trợ lý Gia đình</i> 💬</h1>""")
    
    # --- Khởi tạo session state ---
    if "current_member" not in st.session_state:
        st.session_state.current_member = None  # ID thành viên đang trò chuyện
    if "refresh_suggestions" not in st.session_state:
        st.session_state.refresh_suggestions = False  # Cờ làm mới gợi ý

    # --- Thanh bên ---
    with st.sidebar:
        default_openai_api_key = os.getenv("OPENAI_API_KEY") if os.getenv("OPENAI_API_KEY") is not None else ""
        with st.popover("🔐 OpenAI API Key"):
            openai_api_key = st.text_input("Nhập OpenAI API Key của bạn:", value=default_openai_api_key, type="password")
        
        # Chọn người dùng hiện tại
        st.write("## 👤 Chọn người dùng")
        
        # Tạo danh sách tên thành viên và ID
        member_options = {"Chung (Không cá nhân hóa)": None}
        for member_id, member in family_data.items():
            if isinstance(member, dict) and "name" in member:
                member_options[member["name"]] = member_id
        
        # Dropdown chọn người dùng
        selected_member_name = st.selectbox(
            "Bạn đang trò chuyện với tư cách ai?",
            options=list(member_options.keys()),
            index=0
        )
        
        # Cập nhật người dùng hiện tại
        new_member_id = member_options[selected_member_name]
        
        # Nếu người dùng thay đổi, cập nhật session state và khởi tạo lại tin nhắn
        if new_member_id != st.session_state.current_member:
            st.session_state.current_member = new_member_id
            st.session_state.refresh_suggestions = True  # Đánh dấu để làm mới gợi ý
            if "messages" in st.session_state:
                st.session_state.pop("messages", None)
                st.rerun()
        
        # Hiển thị thông tin người dùng hiện tại
        if st.session_state.current_member:
            member = family_data[st.session_state.current_member]
            st.info(f"Đang trò chuyện với tư cách: **{member.get('name')}**")
            
            # Hiển thị lịch sử trò chuyện trước đó
            if st.session_state.current_member in chat_history and chat_history[st.session_state.current_member]:
                with st.expander("📜 Lịch sử trò chuyện trước đó"):
                    for idx, history in enumerate(chat_history[st.session_state.current_member]):
                        st.write(f"**{history.get('timestamp')}**")
                        st.write(f"*{history.get('summary', 'Không có tóm tắt')}*")
                        
                        # Nút để tải lại cuộc trò chuyện cũ
                        if st.button(f"Tải lại cuộc trò chuyện này", key=f"load_chat_{idx}"):
                            st.session_state.messages = history.get('messages', [])
                            st.rerun()
                        st.divider()
        
        st.write("## Thông tin Gia đình")
        
        # Phần thêm thành viên gia đình
        with st.expander("➕ Thêm thành viên gia đình"):
            with st.form("add_family_form"):
                member_name = st.text_input("Tên")
                member_age = st.text_input("Tuổi")
                st.write("Sở thích:")
                food_pref = st.text_input("Món ăn yêu thích")
                hobby_pref = st.text_input("Sở thích")
                color_pref = st.text_input("Màu yêu thích")
                
                add_member_submitted = st.form_submit_button("Thêm")
                
                if add_member_submitted and member_name:
                    member_id = str(len(family_data) + 1)
                    family_data[member_id] = {
                        "name": member_name,
                        "age": member_age,
                        "preferences": {
                            "food": food_pref,
                            "hobby": hobby_pref,
                            "color": color_pref
                        },
                        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(FAMILY_DATA_FILE, family_data)
                    st.success(f"Đã thêm {member_name} vào gia đình!")
                    st.rerun()  # Tải lại trang để cập nhật danh sách người dùng
        
        # Xem và chỉnh sửa thành viên gia đình
        with st.expander("👥 Thành viên gia đình"):
            if not family_data:
                st.write("Chưa có thành viên nào trong gia đình")
            else:
                for member_id, member in family_data.items():
                    # Kiểm tra kiểu dữ liệu của member
                    if isinstance(member, dict):
                        # Sử dụng get() khi member là dict
                        member_name = member.get("name", "Không tên")
                        member_age = member.get("age", "")
                        
                        st.write(f"**{member_name}** ({member_age})")
                        
                        # Hiển thị sở thích
                        if "preferences" in member and isinstance(member["preferences"], dict):
                            for pref_key, pref_value in member["preferences"].items():
                                if pref_value:
                                    st.write(f"- {pref_key.capitalize()}: {pref_value}")
                        
                        # Nút chỉnh sửa cho mỗi thành viên
                        if st.button(f"Chỉnh sửa {member_name}", key=f"edit_{member_id}"):
                            st.session_state.editing_member = member_id
                    else:
                        # Xử lý khi member không phải dict
                        st.error(f"Dữ liệu thành viên ID={member_id} không đúng định dạng")
        
        # Form chỉnh sửa thành viên (xuất hiện khi đang chỉnh sửa)
        if "editing_member" in st.session_state and st.session_state.editing_member:
            member_id = st.session_state.editing_member
            if member_id in family_data and isinstance(family_data[member_id], dict):
                member = family_data[member_id]
                
                with st.form(f"edit_member_{member_id}"):
                    st.write(f"Chỉnh sửa: {member.get('name', 'Không tên')}")
                    
                    # Các trường chỉnh sửa
                    new_name = st.text_input("Tên", member.get("name", ""))
                    new_age = st.text_input("Tuổi", member.get("age", ""))
                    
                    # Sở thích
                    st.write("Sở thích:")
                    prefs = member.get("preferences", {}) if isinstance(member.get("preferences"), dict) else {}
                    new_food = st.text_input("Món ăn yêu thích", prefs.get("food", ""))
                    new_hobby = st.text_input("Sở thích", prefs.get("hobby", ""))
                    new_color = st.text_input("Màu yêu thích", prefs.get("color", ""))
                    
                    save_edits = st.form_submit_button("Lưu")
                    cancel_edits = st.form_submit_button("Hủy")
                    
                    if save_edits:
                        family_data[member_id]["name"] = new_name
                        family_data[member_id]["age"] = new_age
                        family_data[member_id]["preferences"] = {
                            "food": new_food,
                            "hobby": new_hobby,
                            "color": new_color
                        }
                        save_data(FAMILY_DATA_FILE, family_data)
                        st.session_state.editing_member = None
                        # Cập nhật ngay lập tức để tạo câu hỏi mới
                        if member_id == st.session_state.current_member:
                            st.session_state.refresh_suggestions = True
                        st.success("Đã cập nhật thông tin!")
                        st.rerun()
                    
                    if cancel_edits:
                        st.session_state.editing_member = None
                        st.rerun()
            else:
                st.error(f"Không tìm thấy thành viên với ID: {member_id}")
                st.session_state.editing_member = None
        
        st.divider()
        
        # Quản lý sự kiện
        st.write("## Sự kiện")
        
        # Phần thêm sự kiện
        with st.expander("📅 Thêm sự kiện"):
            with st.form("add_event_form"):
                event_title = st.text_input("Tiêu đề sự kiện")
                event_date = st.date_input("Ngày")
                event_time = st.time_input("Giờ")
                event_desc = st.text_area("Mô tả")
                
                # Multi-select cho người tham gia
                try:
                    member_names = [member.get("name", "") for member_id, member in family_data.items() 
                                   if isinstance(member, dict) and member.get("name")]
                    participants = st.multiselect("Người tham gia", member_names)
                except Exception as e:
                    st.error(f"Lỗi khi tải danh sách thành viên: {e}")
                    participants = []
                
                add_event_submitted = st.form_submit_button("Thêm sự kiện")
                
                if add_event_submitted and event_title:
                    event_id = str(len(events_data) + 1)
                    events_data[event_id] = {
                        "title": event_title,
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": event_time.strftime("%H:%M"),
                        "description": event_desc,
                        "participants": participants,
                        "created_by": st.session_state.current_member,  # Lưu người tạo
                        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(EVENTS_DATA_FILE, events_data)
                    st.success(f"Đã thêm sự kiện: {event_title}!")
        
        # Xem sự kiện sắp tới - đã được lọc theo người dùng
        with st.expander("📆 Sự kiện"):
            # Lọc sự kiện theo người dùng hiện tại
            filtered_events = (
                filter_events_by_member(st.session_state.current_member) 
                if st.session_state.current_member 
                else events_data
            )
            
            # Phần hiển thị chế độ lọc
            mode = st.radio(
                "Chế độ hiển thị:",
                ["Tất cả sự kiện", "Sự kiện của tôi", "Sự kiện tôi tham gia"],
                horizontal=True,
                disabled=not st.session_state.current_member
            )
            
            # Lọc thêm theo chế độ được chọn
            display_events = {}
            current_member_name = ""
            if st.session_state.current_member:
                current_member_name = family_data[st.session_state.current_member].get("name", "")
            
            if mode == "Sự kiện của tôi" and st.session_state.current_member:
                for event_id, event in filtered_events.items():
                    if event.get("created_by") == st.session_state.current_member:
                        display_events[event_id] = event
            elif mode == "Sự kiện tôi tham gia" and current_member_name:
                for event_id, event in filtered_events.items():
                    if current_member_name in event.get("participants", []):
                        display_events[event_id] = event
            else:
                display_events = filtered_events
            
            # Sắp xếp sự kiện theo ngày (với xử lý lỗi)
            try:
                sorted_events = sorted(
                    display_events.items(),
                    key=lambda x: (x[1].get("date", ""), x[1].get("time", ""))
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp sự kiện: {e}")
                sorted_events = []
            
            if not sorted_events:
                st.write("Không có sự kiện nào")
            
            for event_id, event in sorted_events:
                st.write(f"**{event.get('title', 'Sự kiện không tiêu đề')}**")
                st.write(f"📅 {event.get('date', 'Chưa đặt ngày')} | ⏰ {event.get('time', 'Chưa đặt giờ')}")
                
                if event.get('description'):
                    st.write(event.get('description', ''))
                
                if event.get('participants'):
                    st.write(f"👥 {', '.join(event.get('participants', []))}")
                
                # Hiển thị người tạo
                if event.get('created_by') and event.get('created_by') in family_data:
                    creator_name = family_data[event.get('created_by')].get("name", "")
                    st.write(f"👤 Tạo bởi: {creator_name}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Chỉnh sửa", key=f"edit_event_{event_id}"):
                        st.session_state.editing_event = event_id
                with col2:
                    if st.button(f"Xóa", key=f"delete_event_{event_id}"):
                        delete_event(event_id)
                        st.success(f"Đã xóa sự kiện!")
                        st.rerun()
                st.divider()
        
        # Form chỉnh sửa sự kiện (xuất hiện khi đang chỉnh sửa)
        if "editing_event" in st.session_state and st.session_state.editing_event:
            event_id = st.session_state.editing_event
            event = events_data[event_id]
            
            with st.form(f"edit_event_{event_id}"):
                st.write(f"Chỉnh sửa sự kiện: {event['title']}")
                
                # Chuyển đổi định dạng ngày
                try:
                    event_date_obj = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
                except:
                    event_date_obj = datetime.date.today()
                
                # Chuyển đổi định dạng giờ
                try:
                    event_time_obj = datetime.datetime.strptime(event["time"], "%H:%M").time()
                except:
                    event_time_obj = datetime.datetime.now().time()
                
                # Các trường chỉnh sửa
                new_title = st.text_input("Tiêu đề", event["title"])
                new_date = st.date_input("Ngày", event_date_obj)
                new_time = st.time_input("Giờ", event_time_obj)
                new_desc = st.text_area("Mô tả", event["description"])
                
                # Multi-select cho người tham gia
                try:
                    member_names = [member.get("name", "") for member_id, member in family_data.items() 
                                   if isinstance(member, dict) and member.get("name")]
                    new_participants = st.multiselect("Người tham gia", member_names, default=event.get("participants", []))
                except Exception as e:
                    st.error(f"Lỗi khi tải danh sách thành viên: {e}")
                    new_participants = []
                
                save_event_edits = st.form_submit_button("Lưu")
                cancel_event_edits = st.form_submit_button("Hủy")
                
                if save_event_edits:
                    events_data[event_id]["title"] = new_title
                    events_data[event_id]["date"] = new_date.strftime("%Y-%m-%d")
                    events_data[event_id]["time"] = new_time.strftime("%H:%M")
                    events_data[event_id]["description"] = new_desc
                    events_data[event_id]["participants"] = new_participants
                    save_data(EVENTS_DATA_FILE, events_data)
                    st.session_state.editing_event = None
                    st.success("Đã cập nhật sự kiện!")
                    st.rerun()
                
                if cancel_event_edits:
                    st.session_state.editing_event = None
                    st.rerun()
        
        st.divider()
        
        # Quản lý ghi chú
        st.write("## Ghi chú")
        
        # Xem ghi chú - lọc theo người dùng hiện tại
        with st.expander("📝 Ghi chú"):
            # Lọc ghi chú theo người dùng hiện tại
            if st.session_state.current_member:
                filtered_notes = {note_id: note for note_id, note in notes_data.items() 
                               if note.get("created_by") == st.session_state.current_member}
            else:
                filtered_notes = notes_data
            
            # Sắp xếp ghi chú theo ngày tạo (với xử lý lỗi)
            try:
                sorted_notes = sorted(
                    filtered_notes.items(),
                    key=lambda x: x[1].get("created_on", ""),
                    reverse=True
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp ghi chú: {e}")
                sorted_notes = []
            
            if not sorted_notes:
                st.write("Không có ghi chú nào")
            
            for note_id, note in sorted_notes:
                st.write(f"**{note.get('title', 'Ghi chú không tiêu đề')}**")
                st.write(note.get('content', ''))
                
                if note.get('tags'):
                    tags = ', '.join([f"#{tag}" for tag in note['tags']])
                    st.write(f"🏷️ {tags}")
                
                # Hiển thị người tạo
                if note.get('created_by') and note.get('created_by') in family_data:
                    creator_name = family_data[note.get('created_by')].get("name", "")
                    st.write(f"👤 Tạo bởi: {creator_name}")
                
                col1, col2 = st.columns(2)
                with col2:
                    if st.button(f"Xóa", key=f"delete_note_{note_id}"):
                        del notes_data[note_id]
                        save_data(NOTES_DATA_FILE, notes_data)
                        st.success(f"Đã xóa ghi chú!")
                        st.rerun()
                st.divider()
        
        st.divider()
        
        def reset_conversation():
            if "messages" in st.session_state and len(st.session_state.messages) > 0:
                # Trước khi xóa, lưu lịch sử trò chuyện nếu đang trò chuyện với một thành viên
                if st.session_state.current_member and openai_api_key:
                    summary = generate_chat_summary(st.session_state.messages, openai_api_key)
                    save_chat_history(st.session_state.current_member, st.session_state.messages, summary)
                # Xóa tin nhắn
                st.session_state.pop("messages", None)

        st.button(
            "🗑️ Xóa lịch sử trò chuyện", 
            on_click=reset_conversation,
        )

    # --- Nội dung chính ---
    # Kiểm tra nếu người dùng đã nhập OpenAI API Key, nếu không thì hiển thị cảnh báo
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        st.write("#")
        st.warning("⬅️ Vui lòng nhập OpenAI API Key để tiếp tục...")
        
        st.write("""
        ### Chào mừng bạn đến với Trợ lý Gia đình!
        
        Ứng dụng này giúp bạn:
        
        - 👨‍👩‍👧‍👦 Lưu trữ thông tin và sở thích của các thành viên trong gia đình
        - 📅 Quản lý các sự kiện gia đình
        - 📝 Tạo và lưu trữ các ghi chú
        - 💬 Trò chuyện với trợ lý AI để cập nhật thông tin
        - 👤 Cá nhân hóa trò chuyện theo từng thành viên
        - 📜 Lưu lịch sử trò chuyện và tạo tóm tắt tự động
        
        Để bắt đầu, hãy nhập OpenAI API Key của bạn ở thanh bên trái.
        """)

    else:
        client = OpenAI(api_key=openai_api_key)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Hiển thị các tin nhắn trước đó nếu có
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                for content in message["content"]:
                    if content["type"] == "text":
                        st.write(content["text"])
                    elif content["type"] == "image_url":      
                        st.image(content["image_url"]["url"])

        # Thêm chức năng hình ảnh
        with st.sidebar:
            st.divider()
            st.write("## 🖼️ Hình ảnh")
            st.write("Thêm hình ảnh để hỏi trợ lý về món ăn, hoạt động gia đình...")

            def add_image_to_messages():
                if st.session_state.uploaded_img or ("camera_img" in st.session_state and st.session_state.camera_img):
                    img_type = st.session_state.uploaded_img.type if st.session_state.uploaded_img else "image/jpeg"
                    raw_img = Image.open(st.session_state.uploaded_img or st.session_state.camera_img)
                    img = get_image_base64(raw_img)
                    st.session_state.messages.append(
                        {
                            "role": "user", 
                            "content": [{
                                "type": "image_url",
                                "image_url": {"url": f"data:{img_type};base64,{img}"}
                            }]
                        }
                    )
                    st.rerun()
            
            cols_img = st.columns(2)
            with cols_img[0]:
                with st.popover("📁 Tải lên"):
                    st.file_uploader(
                        "Tải lên hình ảnh:", 
                        type=["png", "jpg", "jpeg"],
                        accept_multiple_files=False,
                        key="uploaded_img",
                        on_change=add_image_to_messages,
                    )

            with cols_img[1]:                    
                with st.popover("📸 Camera"):
                    activate_camera = st.checkbox("Bật camera")
                    if activate_camera:
                        st.camera_input(
                            "Chụp ảnh", 
                            key="camera_img",
                            on_change=add_image_to_messages,
                        )

        # Hiển thị banner thông tin người dùng hiện tại
        if st.session_state.current_member and st.session_state.current_member in family_data:
            member_name = family_data[st.session_state.current_member].get("name", "")
            st.info(f"👤 Đang trò chuyện với tư cách: **{member_name}**")
            
            # Hiển thị câu hỏi gợi ý cá nhân hóa
            suggested_questions = generate_personalized_questions(st.session_state.current_member)
            if suggested_questions:
                st.write("#### Câu hỏi gợi ý cho bạn:")
                cols = st.columns(2)
                for i, question in enumerate(suggested_questions[:4]):  # Giới hạn 4 câu hỏi
                    col_idx = i % 2
                    with cols[col_idx]:
                        if st.button(f"{question}", key=f"suggest_q_{i}"):
                            # Khi nhấn nút, gửi câu hỏi vào chat
                            st.session_state.messages.append({
                                "role": "user", 
                                "content": [{
                                    "type": "text",
                                    "text": question,
                                }]
                            })
                            st.rerun()
        elif st.session_state.current_member is None:
            st.info("👨‍👩‍👧‍👦 Đang trò chuyện trong chế độ chung")

        # System prompt cho trợ lý
        system_prompt = f"""
        Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là giúp quản lý thông tin về các thành viên trong gia đình, 
        sở thích của họ, các sự kiện, ghi chú, và phân tích hình ảnh liên quan đến gia đình. Khi người dùng yêu cầu, bạn phải thực hiện ngay các hành động sau:
        
        1. Thêm thông tin về thành viên gia đình (tên, tuổi, sở thích)
        2. Cập nhật sở thích của thành viên gia đình
        3. Thêm, cập nhật, hoặc xóa sự kiện
        4. Thêm ghi chú
        5. Phân tích hình ảnh người dùng đưa ra (món ăn, hoạt động gia đình, v.v.)
        
        QUAN TRỌNG: Khi cần thực hiện các hành động trên, bạn PHẢI sử dụng đúng cú pháp lệnh đặc biệt này (người dùng sẽ không nhìn thấy):
        
        - Thêm thành viên: ##ADD_FAMILY_MEMBER:{{"name":"Tên","age":"Tuổi","preferences":{{"food":"Món ăn","hobby":"Sở thích","color":"Màu sắc"}}}}##
        - Cập nhật sở thích: ##UPDATE_PREFERENCE:{{"id":"id_thành_viên","key":"loại_sở_thích","value":"giá_trị"}}##
        - Thêm sự kiện: ##ADD_EVENT:{{"title":"Tiêu đề","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả","participants":["Tên1","Tên2"]}}##
        - Cập nhật sự kiện: ##UPDATE_EVENT:{{"id":"id_sự_kiện","title":"Tiêu đề mới","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả mới","participants":["Tên1","Tên2"]}}##
        - Xóa sự kiện: ##DELETE_EVENT:id_sự_kiện##
        - Thêm ghi chú: ##ADD_NOTE:{{"title":"Tiêu đề","content":"Nội dung","tags":["tag1","tag2"]}}##
        
        QUY TẮC THÊM SỰ KIỆN ĐƠN GIẢN:
        1. Khi được yêu cầu thêm sự kiện, hãy thực hiện NGAY LẬP TỨC mà không cần hỏi thêm thông tin không cần thiết.
        2. Khi người dùng nói "ngày mai" hoặc "tuần sau", hãy tự động tính toán ngày trong cú pháp YYYY-MM-DD.
        3. Nếu không có thời gian cụ thể, sử dụng thời gian mặc định là 19:00.
        4. Sử dụng mô tả ngắn gọn từ yêu cầu của người dùng.
        5. Chỉ hỏi thông tin nếu thực sự cần thiết, tránh nhiều bước xác nhận.
        6. Sau khi thêm/cập nhật/xóa sự kiện, tóm tắt ngắn gọn hành động đã thực hiện.
        
        Hôm nay là {datetime.datetime.now().strftime("%d/%m/%Y")}.
        
        CẤU TRÚC JSON PHẢI CHÍNH XÁC như trên. Đảm bảo dùng dấu ngoặc kép cho cả keys và values. Đảm bảo các dấu ngoặc nhọn và vuông được đóng đúng cách.
        
        QUAN TRỌNG: Khi người dùng yêu cầu tạo sự kiện mới, hãy luôn sử dụng lệnh ##ADD_EVENT:...## trong phản hồi của bạn mà không cần quá nhiều bước xác nhận.
        
        Đối với hình ảnh:
        - Nếu người dùng gửi hình ảnh món ăn, hãy mô tả món ăn, và đề xuất cách nấu hoặc thông tin dinh dưỡng nếu phù hợp
        - Nếu là hình ảnh hoạt động gia đình, hãy mô tả hoạt động và đề xuất cách ghi nhớ khoảnh khắc đó
        - Với bất kỳ hình ảnh nào, hãy giúp người dùng liên kết nó với thành viên gia đình hoặc sự kiện nếu phù hợp
        
        """
        
        # Thêm thông tin về người dùng hiện tại
        if st.session_state.current_member and st.session_state.current_member in family_data:
            current_member = family_data[st.session_state.current_member]
            system_prompt += f"""
            THÔNG TIN NGƯỜI DÙNG HIỆN TẠI:
            Bạn đang trò chuyện với: {current_member.get('name')}
            Tuổi: {current_member.get('age', '')}
            Sở thích: {json.dumps(current_member.get('preferences', {}), ensure_ascii=False)}
            
            QUAN TRỌNG: Hãy điều chỉnh cách giao tiếp và đề xuất phù hợp với người dùng này. Các sự kiện và ghi chú sẽ được ghi danh nghĩa người này tạo.
            """
        
        # Thêm thông tin dữ liệu
        system_prompt += f"""
        Thông tin hiện tại về gia đình:
        {json.dumps(family_data, ensure_ascii=False, indent=2)}
        
        Sự kiện sắp tới:
        {json.dumps(events_data, ensure_ascii=False, indent=2)}
        
        Ghi chú:
        {json.dumps(notes_data, ensure_ascii=False, indent=2)}
        
        Hãy hiểu và đáp ứng nhu cầu của người dùng một cách tự nhiên và hữu ích. Không hiển thị các lệnh đặc biệt
        trong phản hồi của bạn, chỉ sử dụng chúng để thực hiện các hành động được yêu cầu.
        """

        # Chat input và các tùy chọn âm thanh
        audio_prompt = None
        if "prev_speech_hash" not in st.session_state:
            st.session_state.prev_speech_hash = None

        # Ghi âm
        st.write("🎤 Bạn có thể nói:")
        speech_input = audio_recorder("Nhấn để nói", icon_size="2x", neutral_color="#6ca395")
        if speech_input and st.session_state.prev_speech_hash != hash(speech_input):
            st.session_state.prev_speech_hash = hash(speech_input)
            
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=("audio.wav", speech_input),
            )

            audio_prompt = transcript.text

        # Chat input
        if prompt := st.chat_input("Xin chào! Tôi có thể giúp gì cho gia đình bạn?") or audio_prompt:
            st.session_state.messages.append(
                {
                    "role": "user", 
                    "content": [{
                        "type": "text",
                        "text": prompt or audio_prompt,
                    }]
                }
            )
            
            # Hiển thị tin nhắn mới
            with st.chat_message("user"):
                st.markdown(prompt or audio_prompt)

            with st.chat_message("assistant"):
                st.write_stream(stream_llm_response(
                    api_key=openai_api_key, 
                    system_prompt=system_prompt,
                    current_member=st.session_state.current_member
                ))

if __name__=="__main__":
    main()