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
import random
import hashlib

dotenv.load_dotenv()

# Đường dẫn file lưu trữ dữ liệu
FAMILY_DATA_FILE = "family_data.json"
EVENTS_DATA_FILE = "events_data.json"
NOTES_DATA_FILE = "notes_data.json"
CHAT_HISTORY_FILE = "chat_history.json"

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
chat_history = load_data(CHAT_HISTORY_FILE)

# Kiểm tra và sửa cấu trúc dữ liệu
verify_data_structure()

# Hàm chuyển đổi hình ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Hàm tạo câu hỏi đề xuất dựa trên sở thích của thành viên
def generate_suggested_questions(member_id):
    if member_id not in family_data:
        return []
    
    member = family_data[member_id]
    questions = []
    
    # Từ điển ánh xạ các loại sở thích với loại câu hỏi
    interest_to_questions = {
        "food": [
            "Công thức nấu món {food} như thế nào?",
            "Hôm nay có gì ngon để ăn với {food} không?",
            "Những nhà hàng nào gần đây có món {food} ngon?",
            "Giá trị dinh dưỡng của {food} là gì?",
            "Có thể kết hợp {food} với món nào khác?"
        ],
        "hobby": [
            "Tin mới nhất về {hobby} hôm nay?",
            "Làm thế nào để tập/chơi {hobby} tốt hơn?",
            "Có sự kiện {hobby} nào sắp diễn ra không?",
            "Ai là người giỏi nhất về {hobby} hiện nay?",
            "Những dụng cụ cần thiết cho {hobby} là gì?"
        ],
        "color": [
            "Trang phục màu {color} phối với màu gì đẹp?",
            "Ý nghĩa của màu {color} trong văn hóa?",
            "Những món đồ màu {color} nên có trong nhà?",
            "Màu {color} phù hợp với phong cách nào?",
            "Tâm trạng liên quan đến màu {color} là gì?"
        ],
        "sport": [
            "Kết quả {sport} mới nhất hôm nay?",
            "Lịch thi đấu {sport} tuần này?",
            "Thông tin về cầu thủ/vận động viên {sport} nổi tiếng?",
            "Kỹ thuật tập luyện {sport} hiệu quả?",
            "Giải đấu {sport} nào đang diễn ra?"
        ],
        "music": [
            "Bài hát mới nhất của {artist} là gì?",
            "Album nhạc {genre} hay nhất hiện nay?",
            "Concert {genre} nào sắp diễn ra?",
            "Thông tin về ca sĩ/nhạc sĩ {artist}?",
            "Các bài hát {genre} phù hợp để tập thể dục?"
        ],
        "movie": [
            "Phim {genre} mới nào đáng xem?",
            "Đánh giá về phim {title}?",
            "Lịch chiếu phim mới tại rạp?",
            "Thông tin về diễn viên {actor}?",
            "Những phim {genre} hay nhất năm nay?"
        ],
        "book": [
            "Sách {genre} mới xuất bản?",
            "Tóm tắt nội dung sách {title}?",
            "Tác giả {author} có tác phẩm mới không?",
            "Sách {genre} được đánh giá cao nhất?",
            "Các sách hay về chủ đề {topic}?"
        ]
    }
    
    # Lấy các sở thích từ thành viên
    preferences = member.get("preferences", {})
    
    # Tạo câu hỏi dựa trên sở thích
    for pref_key, pref_value in preferences.items():
        if pref_value and pref_key in interest_to_questions:
            # Chọn ngẫu nhiên 2 câu hỏi từ mỗi loại sở thích
            template_questions = random.sample(interest_to_questions[pref_key], min(2, len(interest_to_questions[pref_key])))
            for template in template_questions:
                # Thay thế placeholder với giá trị sở thích
                question = template.format(**{pref_key: pref_value})
                questions.append(question)
    
    # Thêm một số câu hỏi chung về thành viên
    general_questions = [
        f"Sở thích mới của {member['name']} là gì?",
        f"Thêm sự kiện cho {member['name']}",
        f"Nhắc nhở {member['name']} về lịch sắp tới",
        f"Món ăn phù hợp cho {member['name']} hôm nay?",
        f"Hoạt động cuối tuần cho {member['name']}?"
    ]
    
    # Chọn ngẫu nhiên 3 câu hỏi chung
    selected_general = random.sample(general_questions, min(3, len(general_questions)))
    questions.extend(selected_general)
    
    # Thêm câu hỏi về sự kiện sắp tới của thành viên
    member_events = get_member_events(member_id)
    if member_events:
        next_event = member_events[0]  # Lấy sự kiện gần nhất
        questions.append(f"Chi tiết về sự kiện '{next_event.get('title')}' ngày {next_event.get('date')}?")
    
    # Đảm bảo không trùng lặp câu hỏi
    return list(set(questions))

# Hàm lấy sự kiện của thành viên cụ thể
def get_member_events(member_id):
    if member_id not in family_data:
        return []
    
    member_name = family_data[member_id]["name"]
    member_events = []
    
    for event_id, event in events_data.items():
        if member_name in event.get("participants", []):
            member_events.append(event)
    
    # Sắp xếp theo ngày
    try:
        member_events.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
    except Exception as e:
        logger.error(f"Lỗi khi sắp xếp sự kiện: {e}")
    
    return member_events

# Hàm tóm tắt lịch sử trò chuyện
def summarize_chat_history(member_id, max_summaries=3):
    if member_id not in chat_history:
        return []
    
    member_chat = chat_history.get(member_id, {})
    summaries = member_chat.get("summaries", [])
    
    # Chỉ trả về các tóm tắt gần đây nhất
    return summaries[-max_summaries:]

# Hàm thêm tóm tắt trò chuyện mới
def add_chat_summary(member_id, summary):
    if member_id not in chat_history:
        chat_history[member_id] = {"messages": [], "summaries": []}
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_history[member_id]["summaries"].append({
        "timestamp": timestamp,
        "summary": summary
    })
    
    # Giới hạn số lượng tóm tắt lưu trữ
    if len(chat_history[member_id]["summaries"]) > 10:
        chat_history[member_id]["summaries"] = chat_history[member_id]["summaries"][-10:]
    
    save_data(CHAT_HISTORY_FILE, chat_history)

# Hàm thêm tin nhắn vào lịch sử trò chuyện
def add_message_to_history(member_id, message):
    if member_id not in chat_history:
        chat_history[member_id] = {"messages": [], "summaries": []}
    
    chat_history[member_id]["messages"].append(message)
    
    # Giới hạn số lượng tin nhắn lưu trữ
    if len(chat_history[member_id]["messages"]) > 50:
        chat_history[member_id]["messages"] = chat_history[member_id]["messages"][-50:]
    
    save_data(CHAT_HISTORY_FILE, chat_history)

# Hàm lấy tin nhắn từ lịch sử trò chuyện
def get_chat_messages(member_id):
    if member_id not in chat_history:
        return []
    
    return chat_history.get(member_id, {}).get("messages", [])

# Hàm stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key, system_prompt="", member_id=None):
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
        process_assistant_response(response_message)
        
        # Thêm phản hồi vào session state
        st.session_state.messages.append({
            "role": "assistant", 
            "content": [
                {
                    "type": "text",
                    "text": response_message,
                }
            ]})
        
        # Lưu trữ tin nhắn vào lịch sử nếu có member_id
        if member_id:
            # Tạo tóm tắt cho cuộc trò chuyện hiện tại nếu đủ dài
            if len(st.session_state.messages) >= 4:  # Ít nhất 2 lượt đối thoại
                last_user_msg = [msg for msg in st.session_state.messages[-2:] if msg["role"] == "user"]
                if last_user_msg:
                    user_query = last_user_msg[0]["content"][0]["text"]
                    # Tạo tóm tắt ngắn gọn
                    summary = f"Người dùng hỏi về: '{user_query[:50]}...' - Trợ lý trả lời về: '{response_message[:100]}...'"
                    add_chat_summary(member_id, summary)
            
            # Lưu tin nhắn
            for msg in st.session_state.messages:
                add_message_to_history(member_id, msg)

    except Exception as e:
        logger.error(f"Lỗi khi tạo phản hồi từ OpenAI: {e}")
        error_message = f"Có lỗi xảy ra: {str(e)}"
        yield error_message

def process_assistant_response(response):
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
        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(NOTES_DATA_FILE, notes_data)

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

    # --- Thanh bên ---
    with st.sidebar:
        default_openai_api_key = os.getenv("OPENAI_API_KEY") if os.getenv("OPENAI_API_KEY") is not None else ""
        with st.popover("🔐 OpenAI API Key"):
            openai_api_key = st.text_input("Nhập OpenAI API Key của bạn:", value=default_openai_api_key, type="password")
        
        # Thêm chọn lựa thành viên gia đình
        st.write("## 👤 Chọn thành viên trò chuyện")
        
        # Mặc định là "Gia đình" (không chọn thành viên cụ thể)
        family_members = {"0": "👨‍👩‍👧‍👦 Cả gia đình"}
        
        # Thêm các thành viên từ dữ liệu
        for member_id, member in family_data.items():
            if isinstance(member, dict) and member.get("name"):
                family_members[member_id] = f"👤 {member.get('name')}"
        
        # Dropdown chọn thành viên
        selected_member = st.selectbox(
            "Bạn muốn trò chuyện với ai?",
            options=list(family_members.keys()),
            format_func=lambda x: family_members[x],
            key="selected_member"
        )
        
        # Đặt thành viên hiện tại vào session_state
        if "current_member_id" not in st.session_state or st.session_state.current_member_id != selected_member:
            st.session_state.current_member_id = selected_member
            # Reset tin nhắn khi chuyển thành viên
            st.session_state.messages = get_chat_messages(selected_member) if selected_member != "0" else []
        
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
                sport_pref = st.text_input("Thể thao yêu thích")
                music_pref = st.text_input("Thể loại nhạc/Ca sĩ yêu thích")
                
                add_member_submitted = st.form_submit_button("Thêm")
                
                if add_member_submitted and member_name:
                    member_id = str(len(family_data) + 1)
                    family_data[member_id] = {
                        "name": member_name,
                        "age": member_age,
                        "preferences": {
                            "food": food_pref,
                            "hobby": hobby_pref,
                            "color": color_pref,
                            "sport": sport_pref,
                            "music": music_pref
                        },
                        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(FAMILY_DATA_FILE, family_data)
                    st.success(f"Đã thêm {member_name} vào gia đình!")
                    st.rerun()
        
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
                    new_sport = st.text_input("Thể thao yêu thích", prefs.get("sport", ""))
                    new_music = st.text_input("Thể loại nhạc/Ca sĩ yêu thích", prefs.get("music", ""))
                    
                    save_edits = st.form_submit_button("Lưu")
                    cancel_edits = st.form_submit_button("Hủy")
                    
                    if save_edits:
                        family_data[member_id]["name"] = new_name
                        family_data[member_id]["age"] = new_age
                        family_data[member_id]["preferences"] = {
                            "food": new_food,
                            "hobby": new_hobby,
                            "color": new_color,
                            "sport": new_sport,
                            "music": new_music
                        }
                        save_data(FAMILY_DATA_FILE, family_data)
                        st.session_state.editing_member = None
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
        
        # Lọc sự kiện theo thành viên đang được chọn
        if selected_member != "0" and selected_member in family_data:
            member_name = family_data[selected_member].get("name", "")
            st.write(f"### Sự kiện của {member_name}")
        
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
                        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(EVENTS_DATA_FILE, events_data)
                    st.success(f"Đã thêm sự kiện: {event_title}!")
                    st.rerun()
        
        # Xem sự kiện sắp tới
        with st.expander("📆 Sự kiện sắp tới"):
            # Lọc sự kiện của thành viên được chọn
            filtered_events = {}
            
            if selected_member != "0" and selected_member in family_data:
                member_name = family_data[selected_member].get("name", "")
                for event_id, event in events_data.items():
                    if member_name in event.get("participants", []):
                        filtered_events[event_id] = event
            else:
                filtered_events = events_data
            
            # Sắp xếp sự kiện theo ngày (với xử lý lỗi)
            try:
                sorted_events = sorted(
                    filtered_events.items(),
                    key=lambda x: (x[1].get("date", ""), x[1].get("time", ""))
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp sự kiện: {e}")
                sorted_events = []
            
            if not sorted_events:
                if selected_member != "0":
                    st.write(f"Không có sự kiện nào sắp tới cho {family_data[selected_member].get('name', '')}")
                else:
                    st.write("Không có sự kiện nào sắp tới")
            
            for event_id, event in sorted_events:
                st.write(f"**{event.get('title', 'Sự kiện không tiêu đề')}**")
                st.write(f"📅 {event.get('date', 'Chưa đặt ngày')} | ⏰ {event.get('time', 'Chưa đặt giờ')}")
                
                if event.get('description'):
                    st.write(event.get('description', ''))
                
                if event.get('participants'):
                    participant_text = ", ".join(event.get('participants', []))
                    
                    # Đánh dấu thành viên đang được chọn
                    if selected_member != "0" and selected_member in family_data:
                        member_name = family_data[selected_member].get("name", "")
                        if member_name in event.get('participants', []):
                            participant_text = participant_text.replace(
                                member_name, 
                                f"**{member_name}**"
                            )
                    
                    st.write(f"👥 {participant_text}")
                
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
        
        # Xem ghi chú
        with st.expander("📝 Ghi chú"):
            # Cá nhân hóa ghi chú cho thành viên được chọn
            filtered_notes = {}
            
            if selected_member != "0" and selected_member in family_data:
                member_name = family_data[selected_member].get("name", "")
                for note_id, note in notes_data.items():
                    if member_name in note.get("tags", []):
                        filtered_notes[note_id] = note
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
                if selected_member != "0":
                    st.write(f"Không có ghi chú nào cho {family_data[selected_member].get('name', '')}")
                else:
                    st.write("Không có ghi chú nào")
            
            for note_id, note in sorted_notes:
                st.write(f"**{note.get('title', 'Ghi chú không tiêu đề')}**")
                st.write(note.get('content', ''))
                
                if note.get('tags'):
                    tags = ', '.join([f"#{tag}" for tag in note['tags']])
                    st.write(f"🏷️ {tags}")
                
                col1, col2 = st.columns(2)
                with col2:
                    if st.button(f"Xóa", key=f"delete_note_{note_id}"):
                        del notes_data[note_id]
                        save_data(NOTES_DATA_FILE, notes_data)
                        st.success(f"Đã xóa ghi chú!")
                        st.rerun()
                st.divider()
        
        # Thêm phần tóm tắt lịch sử trò chuyện
        if selected_member != "0":
            st.write("## 📜 Lịch sử trò chuyện")
            summaries = summarize_chat_history(selected_member)
            
            if not summaries:
                st.write(f"Chưa có lịch sử trò chuyện với {family_data[selected_member].get('name', '')}")
            else:
                for summary in summaries:
                    timestamp = summary.get("timestamp", "")
                    content = summary.get("summary", "")
                    st.write(f"**{timestamp}**")
                    st.write(content)
                    st.divider()
        
        st.divider()
        
        def reset_conversation():
            if "messages" in st.session_state and len(st.session_state.messages) > 0:
                st.session_state.pop("messages", None)
                # Nếu đang trò chuyện với thành viên cụ thể
                if st.session_state.current_member_id != "0":
                    # Cập nhật lịch sử nhưng xóa tin nhắn hiện tại
                    member_id = st.session_state.current_member_id
                    if member_id in chat_history:
                        chat_history[member_id]["messages"] = []
                        save_data(CHAT_HISTORY_FILE, chat_history)

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
        - 👤 Cá nhân hóa trò chuyện cho từng thành viên
        
        Để bắt đầu, hãy nhập OpenAI API Key của bạn ở thanh bên trái.
        """)

    else:
        client = OpenAI(api_key=openai_api_key)

        if "messages" not in st.session_state:
            # Nếu đang chat với thành viên cụ thể, tải lịch sử chat
            if st.session_state.current_member_id != "0":
                st.session_state.messages = get_chat_messages(st.session_state.current_member_id) 
            else:
                st.session_state.messages = []

        # Hiển thị thông tin thành viên đang được chọn
        if st.session_state.current_member_id != "0" and st.session_state.current_member_id in family_data:
            member = family_data[st.session_state.current_member_id]
            member_name = member.get("name", "")
            
            # Hiển thị thông tin thành viên
            st.write(f"### 👤 Đang trò chuyện với: {member_name}")
            
            # Hiển thị sở thích
            if member.get("preferences"):
                prefs = []
                for pref_key, pref_value in member.get("preferences", {}).items():
                    if pref_value:
                        prefs.append(f"{pref_key.capitalize()}: {pref_value}")
                
                if prefs:
                    st.write("**Sở thích:** " + ", ".join(prefs))
            
            # Hiển thị sự kiện sắp tới của thành viên
            member_events = get_member_events(st.session_state.current_member_id)
            if member_events:
                next_event = member_events[0]
                st.write(f"**Sự kiện sắp tới:** {next_event.get('title')} ({next_event.get('date')})")
            
            st.divider()

        # Hiển thị các câu hỏi đề xuất
        if st.session_state.current_member_id != "0":
            suggested_questions = generate_suggested_questions(st.session_state.current_member_id)
            if suggested_questions:
                st.write("### 💡 Bạn có thể hỏi:")
                
                # Tạo nút cho các câu hỏi đề xuất
                for i in range(0, len(suggested_questions), 2):
                    cols = st.columns(2)
                    for j in range(2):
                        idx = i + j
                        if idx < len(suggested_questions):
                            # Tạo ID duy nhất cho mỗi nút
                            button_id = hashlib.md5(suggested_questions[idx].encode()).hexdigest()[:10]
                            if cols[j].button(suggested_questions[idx], key=f"suggest_{button_id}"):
                                # Khi nút được nhấn, gửi câu hỏi như một tin nhắn
                                st.session_state.messages.append({
                                    "role": "user", 
                                    "content": [{
                                        "type": "text",
                                        "text": suggested_questions[idx],
                                    }]
                                })
                                # Thêm vào chat_history
                                add_message_to_history(st.session_state.current_member_id, {
                                    "role": "user", 
                                    "content": [{
                                        "type": "text",
                                        "text": suggested_questions[idx],
                                    }]
                                })
                                st.rerun()
                
                st.divider()

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
                    message = {
                        "role": "user", 
                        "content": [{
                            "type": "image_url",
                            "image_url": {"url": f"data:{img_type};base64,{img}"}
                        }]
                    }
                    st.session_state.messages.append(message)
                    
                    # Thêm vào lịch sử nếu đang chat với thành viên cụ thể
                    if st.session_state.current_member_id != "0":
                        add_message_to_history(st.session_state.current_member_id, message)
                    
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
        
        - Thêm thành viên: ##ADD_FAMILY_MEMBER:{{"name":"Tên","age":"Tuổi","preferences":{{"food":"Món ăn","hobby":"Sở thích","color":"Màu sắc","sport":"Thể thao","music":"Nhạc"}}}}##
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
        """
        
        # Bổ sung thông tin về thành viên đang được chọn
        if st.session_state.current_member_id != "0" and st.session_state.current_member_id in family_data:
            member = family_data[st.session_state.current_member_id]
            member_name = member.get("name", "")
            
            system_prompt += f"""
            
            THÔNG TIN THÀNH VIÊN HIỆN TẠI:
            Bạn đang trò chuyện với {member_name}. Hãy điều chỉnh phản hồi để phù hợp với người này.
            
            Thông tin chi tiết:
            {json.dumps(member, ensure_ascii=False, indent=2)}
            
            Sự kiện của {member_name}:
            {json.dumps(get_member_events(st.session_state.current_member_id), ensure_ascii=False, indent=2)}
            
            Khi thêm sự kiện mới, hãy tự động thêm {member_name} vào danh sách người tham gia nếu phù hợp.
            Khi thêm ghi chú mới, hãy tự động thêm {member_name} vào tags.
            
            Tóm tắt trò chuyện trước đó:
            {json.dumps(summarize_chat_history(st.session_state.current_member_id), ensure_ascii=False, indent=2)}
            """
        
        # Thêm thông tin về tất cả gia đình
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
            message = {
                "role": "user", 
                "content": [{
                    "type": "text",
                    "text": prompt or audio_prompt,
                }]
            }
            st.session_state.messages.append(message)
            
            # Thêm vào lịch sử nếu đang chat với thành viên cụ thể
            if st.session_state.current_member_id != "0":
                add_message_to_history(st.session_state.current_member_id, message)
            
            # Hiển thị tin nhắn mới
            with st.chat_message("user"):
                st.markdown(prompt or audio_prompt)

            with st.chat_message("assistant"):
                st.write_stream(stream_llm_response(
                    api_key=openai_api_key, 
                    system_prompt=system_prompt,
                    member_id=st.session_state.current_member_id if st.session_state.current_member_id != "0" else None
                ))

if __name__=="__main__":
    main()