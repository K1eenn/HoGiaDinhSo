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
    global family_data, events_data, notes_data
    
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

# Tải dữ liệu ban đầu
family_data = load_data(FAMILY_DATA_FILE)
events_data = load_data(EVENTS_DATA_FILE)
notes_data = load_data(NOTES_DATA_FILE)

# Kiểm tra và sửa cấu trúc dữ liệu
verify_data_structure()

# Hàm chuyển đổi hình ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Hàm stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key, system_prompt=""):
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
        "allergies": details.get("allergies", []),  # Thêm trường dị ứng
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

# Hàm mới để cập nhật thông tin dị ứng
def update_allergies(member_id, allergies):
    if member_id in family_data:
        family_data[member_id]["allergies"] = allergies
        save_data(FAMILY_DATA_FILE, family_data)
        return True
    return False

# Hàm tạo câu hỏi đề xuất dựa trên thông tin thành viên
def generate_suggested_questions(member_id=None):
    """Sinh câu hỏi đề xuất dựa trên thông tin và sở thích của thành viên gia đình"""
    import random
    
    # Câu hỏi chung nếu không chọn thành viên cụ thể
    if not member_id:
        return [
            "Thêm sự kiện ăn tối vào ngày mai",
            "Thêm kế hoạch du lịch cuối tuần này",
            "Thêm lịch đưa con đi học vào 7h30 sáng mai",
            "Nhắc tôi mua sữa vào thứ 6",
            "Thêm sinh nhật của mẹ vào ngày 15/5"
        ]
    
    # Lấy thông tin thành viên
    member = family_data.get(member_id)
    if not member or not isinstance(member, dict):
        return []
    
    questions = []
    name = member.get("name", "")
    preferences = member.get("preferences", {}) if isinstance(member.get("preferences"), dict) else {}
    allergies = member.get("allergies", []) if isinstance(member.get("allergies"), list) else []
    
    # Các thành phần câu hỏi
    question_prefixes = [
        "Bạn biết gì về", "Thông tin về", "Tìm hiểu về", "Cho tôi biết về", 
        "Tại sao", "Làm thế nào", "Khi nào", "Ai là người", 
        "Top 10", "Xu hướng", "Có những", "Lịch sử của",
        "Tương lai của", "Đánh giá về", "So sánh giữa", "Khám phá",
        "Phân tích", "Giải thích", "Những điều thú vị về", "Bí mật về",
        "Lợi ích của", "Tác hại của", "Cách để", "Hướng dẫn",
        "Tại sao người ta thích", "Điều gì làm cho", "Tôi nên chọn", "Giới thiệu về",
        "Sự khác biệt giữa", "Có đúng là", "Mới nhất về", "Phổ biến nhất về"
    ]
    
    question_connectors = [
        "trong", "ở", "vào", "cho", "với", "và", "hay", "hoặc",
        "khi", "nếu", "so với", "thay vì", "hơn là", "đối với",
        "liên quan đến", "dành cho", "tại", "bởi"
    ]
    
    question_contexts = [
        "hiện nay", "gần đây", "năm nay", "thời gian tới", "thế giới",
        "Việt Nam", "khu vực", "của các chuyên gia", "trong lịch sử",
        "trong tương lai", "theo nghiên cứu", "theo số liệu", "theo xu hướng",
        "trong mùa này", "cho người mới bắt đầu", "cho người có kinh nghiệm",
        "cho trẻ em", "cho người lớn", "vào mùa hè", "vào mùa đông",
        "trong thập kỷ qua", "2024", "mọi thời đại", "đang làm mưa làm gió"
    ]
    
    question_suffixes = [
        "?", "là gì?", "như thế nào?", "ra sao?", "nhỉ?",
        "vậy?", "phải không?", "đúng không?", "có phải không?", "nào tốt nhất?",
        "nào phổ biến nhất?", "và tại sao?", "thế nào là tốt?",
        "bạn có biết không?", "và lợi ích của nó?", "nên tránh điều gì?",
        "được không?", "khó không?", "dễ học không?", "tốn kém không?"
    ]
    
    # Tạo câu hỏi cơ bản về thành viên
    base_questions = [
        f"Thêm sinh nhật của {name}",
        f"Gợi ý quà tặng cho {name}",
        f"Thêm sự kiện đặc biệt cho {name}"
    ]
    questions.extend(base_questions)
    
    # Tạo câu hỏi linh động dựa trên sở thích - món ăn
    food_preference = preferences.get("food", "")
    if food_preference:
        # Tách thành các từ khóa nếu có nhiều sở thích
        food_keywords = [food_preference]
        if " và " in food_preference:
            food_keywords = food_preference.split(" và ")
        elif "," in food_preference:
            food_keywords = [h.strip() for h in food_preference.split(",")]
        
        for food in food_keywords:
            food = food.strip()
            if not food:
                continue
                
            # Sinh câu hỏi ngẫu nhiên về món ăn
            for _ in range(2):  # Tạo 2 câu hỏi cho mỗi sở thích món ăn
                prefix = random.choice(question_prefixes)
                context = random.choice(question_contexts) if random.random() > 0.3 else ""
                suffix = random.choice(question_suffixes)
                
                # Xây dựng câu hỏi với cấu trúc ngẫu nhiên
                if random.random() > 0.5:
                    # Cấu trúc 1: Prefix + food + context + suffix
                    question = f"{prefix} {food} {context} {suffix}".replace("  ", " ").strip()
                else:
                    # Cấu trúc 2: Cụm từ ngẫu nhiên
                    food_phrases = [
                        f"Món {food} ngon nhất {context}",
                        f"Cách chế biến {food}",
                        f"Nguồn gốc của {food}",
                        f"{food} có lợi cho sức khỏe không",
                        f"Thành phần dinh dưỡng trong {food}",
                        f"Địa điểm ăn {food} nổi tiếng",
                        f"Biến tấu món {food}",
                        f"Cách bảo quản {food}",
                        f"Kết hợp {food} với món nào ngon",
                        f"Mùa nào thích hợp để ăn {food}"
                    ]
                    question = f"{random.choice(food_phrases)} {suffix}".replace("  ", " ").strip()
                
                questions.append(question)
    
    # Tạo câu hỏi linh động dựa trên sở thích hoạt động
    hobby_preference = preferences.get("hobby", "")
    if hobby_preference:
        # Tách thành các từ khóa nếu có nhiều sở thích
        hobby_keywords = [hobby_preference]
        if " và " in hobby_preference:
            hobby_keywords = hobby_preference.split(" và ")
        elif "," in hobby_preference:
            hobby_keywords = [h.strip() for h in hobby_preference.split(",")]
        
        for hobby in hobby_keywords:
            hobby = hobby.strip()
            if not hobby:
                continue
                
            # Tạo câu hỏi sự kiện cho sở thích
            questions.append(f"Thêm sự kiện {hobby} vào cuối tuần")
            
            # Sinh câu hỏi ngẫu nhiên về sở thích
            for _ in range(3):  # Tạo 3 câu hỏi cho mỗi sở thích
                # Sinh câu hỏi với cấu trúc hoàn toàn ngẫu nhiên
                if random.random() > 0.6:
                    prefix = random.choice(question_prefixes)
                    connector = random.choice(question_connectors) if random.random() > 0.5 else ""
                    context = random.choice(question_contexts) if random.random() > 0.3 else ""
                    suffix = random.choice(question_suffixes)
                    
                    # Tạo câu hỏi với cấu trúc ngẫu nhiên
                    question_parts = [prefix, hobby]
                    if connector:
                        question_parts.append(connector)
                    if context:
                        question_parts.append(context)
                    question_parts.append(suffix)
                    
                    question = " ".join(question_parts).replace("  ", " ").strip()
                    questions.append(question)
                else:
                    # Tạo câu hỏi đặc thù cho từng lĩnh vực
                    specific_templates = []
                    
                    # Thể thao
                    if any(term in hobby.lower() for term in ["bóng đá", "tennis", "bơi", "cầu lông", "thể thao"]):
                        specific_templates = [
                            f"Kết quả trận đấu {hobby} gần đây nhất",
                            f"Giải đấu {hobby} sắp diễn ra",
                            f"Cầu thủ/VĐV {hobby} xuất sắc nhất hiện nay",
                            f"Lịch thi đấu {hobby} tuần này",
                            f"Kỷ lục {hobby} hiện tại là gì"
                        ]
                    # Phim/TV
                    elif any(term in hobby.lower() for term in ["phim", "movie", "netflix", "tv", "điện ảnh"]):
                        specific_templates = [
                            f"{hobby} hay nhất năm 2024",
                            f"Đánh giá {hobby} mới ra mắt",
                            f"Diễn viên nổi tiếng trong lĩnh vực {hobby}",
                            f"{hobby} sắp chiếu trong tháng tới",
                            f"Đạo diễn nổi tiếng về {hobby}"
                        ]
                    # Âm nhạc
                    elif any(term in hobby.lower() for term in ["âm nhạc", "nhạc", "music", "ca sĩ", "nhạc sĩ"]):
                        specific_templates = [
                            f"Bài hát {hobby} đang hot",
                            f"Ca sĩ {hobby} được yêu thích nhất",
                            f"Concert {hobby} sắp diễn ra",
                            f"Album {hobby} mới phát hành",
                            f"Xu hướng {hobby} đang thịnh hành"
                        ]
                    # Du lịch
                    elif any(term in hobby.lower() for term in ["du lịch", "travel", "khám phá", "phượt"]):
                        specific_templates = [
                            f"Địa điểm {hobby} tuyệt vời nhất",
                            f"Kinh nghiệm {hobby} tiết kiệm",
                            f"Thời điểm lý tưởng để {hobby}",
                            f"Những điều cần tránh khi {hobby}",
                            f"Ẩm thực nổi tiếng khi {hobby}"
                        ]
                    # Công nghệ
                    elif any(term in hobby.lower() for term in ["công nghệ", "tech", "smartphone", "máy tính", "ai"]):
                        specific_templates = [
                            f"Sản phẩm {hobby} mới nhất",
                            f"Đánh giá về {hobby} vừa ra mắt",
                            f"Tương lai của {hobby}",
                            f"So sánh các sản phẩm {hobby}",
                            f"Tin tức mới nhất về {hobby}"
                        ]
                    # Mặc định cho các sở thích khác
                    else:
                        specific_templates = [
                            f"Tin tức mới nhất về {hobby}",
                            f"Người nổi tiếng trong lĩnh vực {hobby}",
                            f"Cách học {hobby} hiệu quả",
                            f"Tài liệu hay về {hobby}",
                            f"Cộng đồng {hobby} ở Việt Nam",
                            f"Sự kiện {hobby} sắp tới",
                            f"Lợi ích của việc tham gia {hobby}",
                            f"Xu hướng {hobby} năm 2024"
                        ]
                    
                    if specific_templates:
                        question = random.choice(specific_templates)
                        # Thêm dấu hỏi nếu chưa có
                        if not question.endswith("?"):
                            question += "?"
                        questions.append(question)
    
    # Tạo câu hỏi liên quan đến dị ứng
    if allergies:
        for allergy in allergies:
            # Tạo câu hỏi linh động về dị ứng
            allergy_prefixes = [
                f"Món ăn thay thế cho người dị ứng {allergy}",
                f"Cách nấu ăn an toàn cho người dị ứng {allergy}",
                f"Những nguyên liệu có thể thay thế {allergy}",
                f"Triệu chứng dị ứng {allergy}",
                f"Cách phòng tránh tiếp xúc với {allergy}"
            ]
            
            # Thêm một câu hỏi ngẫu nhiên về dị ứng
            if allergy_prefixes:
                allergy_question = random.choice(allergy_prefixes)
                if not allergy_question.endswith("?"):
                    allergy_question += "?"
                questions.append(allergy_question)
    
    # Đảm bảo không trả về quá nhiều câu hỏi và luôn thay đổi
    if len(questions) > 5:
        return random.sample(questions, 5)
    
    return questions

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
                
                # Thêm trường dị ứng
                st.write("Dị ứng:")
                allergies = st.text_area("Nhập các dị ứng (phân cách bằng dấu phẩy)", 
                                       help="Ví dụ: tôm, cua, hải sản, đậu phộng, ...")
                
                add_member_submitted = st.form_submit_button("Thêm")
                
                if add_member_submitted and member_name:
                    # Tách danh sách dị ứng
                    allergies_list = [item.strip() for item in allergies.split(",") if item.strip()]
                    
                    member_id = str(len(family_data) + 1)
                    family_data[member_id] = {
                        "name": member_name,
                        "age": member_age,
                        "preferences": {
                            "food": food_pref,
                            "hobby": hobby_pref,
                            "color": color_pref
                        },
                        "allergies": allergies_list,
                        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(FAMILY_DATA_FILE, family_data)
                    st.success(f"Đã thêm {member_name} vào gia đình!")
        
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
                    
                    # Dị ứng
                    st.write("Dị ứng:")
                    allergies_text = ", ".join(member.get("allergies", []))
                    new_allergies = st.text_area("Nhập các dị ứng (phân cách bằng dấu phẩy)", allergies_text,
                                                help="Ví dụ: tôm, cua, hải sản, đậu phộng, ...")
                    
                    save_edits = st.form_submit_button("Lưu")
                    cancel_edits = st.form_submit_button("Hủy")
                    
                    if save_edits:
                        # Tách danh sách dị ứng
                        allergies_list = [item.strip() for item in new_allergies.split(",") if item.strip()]
                        
                        family_data[member_id]["name"] = new_name
                        family_data[member_id]["age"] = new_age
                        family_data[member_id]["preferences"] = {
                            "food": new_food,
                            "hobby": new_hobby,
                            "color": new_color
                        }
                        family_data[member_id]["allergies"] = allergies_list
                        
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
        
        # Xem sự kiện sắp tới
        with st.expander("📆 Sự kiện sắp tới"):
                            # Sắp xếp sự kiện theo ngày (với xử lý lỗi)
            try:
                sorted_events = sorted(
                    events_data.items(),
                    key=lambda x: (x[1].get("date", ""), x[1].get("time", ""))
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp sự kiện: {e}")
                sorted_events = []
            
            if not sorted_events:
                st.write("Không có sự kiện nào sắp tới")
            
            for event_id, event in sorted_events:
                st.write(f"**{event.get('title', 'Sự kiện không tiêu đề')}**")
                st.write(f"📅 {event.get('date', 'Chưa đặt ngày')} | ⏰ {event.get('time', 'Chưa đặt giờ')}")
                
                if event.get('description'):
                    st.write(event.get('description', ''))
                
                if event.get('participants'):
                    st.write(f"👥 {', '.join(event.get('participants', []))}")
                
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
            # Sắp xếp ghi chú theo ngày tạo (với xử lý lỗi)
            try:
                sorted_notes = sorted(
                    notes_data.items(),
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

        # Thêm giao diện đề xuất câu hỏi dưới vùng chat
        st.write("### 💡 Câu hỏi đề xuất")
        
        # Chọn thành viên để xem câu hỏi đề xuất cá nhân hóa
        question_cols = st.columns([2, 3])
        with question_cols[0]:
            # Tạo danh sách thành viên gia đình
            member_options = {"Tất cả": None}
            for member_id, member in family_data.items():
                if isinstance(member, dict) and member.get("name"):
                    member_options[member.get("name")] = member_id
            
            selected_member_name = st.selectbox(
                "Đề xuất cho:",
                options=list(member_options.keys()),
                index=0
            )
            selected_member_id = member_options[selected_member_name]
        
        # Hiển thị các câu hỏi đề xuất
        suggested_questions = generate_suggested_questions(selected_member_id)
        
        if not suggested_questions:
            st.info("Không có câu hỏi đề xuất cho thành viên này.")
        else:
            for i, question in enumerate(suggested_questions[:5]):  # Giới hạn 5 câu hỏi
                button_key = f"question_{i}_{selected_member_name}"
                if st.button(f"🔍 {question}", key=button_key, use_container_width=True):
                    # Khi người dùng nhấn vào câu hỏi, thêm nó vào vùng chat
                    st.session_state.messages.append({
                        "role": "user", 
                        "content": [{
                            "type": "text",
                            "text": question,
                        }]
                    })
                    
                    # Tự động xử lý câu trả lời từ trợ lý
                    with st.chat_message("assistant"):
                        system_prompt = f"""
                        Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là giúp quản lý thông tin về các thành viên trong gia đình, 
                        sở thích của họ, các sự kiện, ghi chú, và phân tích hình ảnh liên quan đến gia đình. Khi người dùng yêu cầu, bạn phải thực hiện ngay các hành động sau:
                        
                        1. Thêm thông tin về thành viên gia đình (tên, tuổi, sở thích)
                        2. Cập nhật sở thích của thành viên gia đình
                        3. Thêm, cập nhật, hoặc xóa sự kiện
                        4. Thêm ghi chú
                        5. Phân tích hình ảnh người dùng đưa ra (món ăn, hoạt động gia đình, v.v.)
                        
                        QUAN TRỌNG: Để bảo vệ sức khỏe, luôn kiểm tra thông tin dị ứng khi đề xuất món ăn.
                        
                        Thông tin dị ứng của các thành viên:
                        {json.dumps({member_id: member.get("allergies", []) for member_id, member in family_data.items() if isinstance(member, dict)}, ensure_ascii=False)}
                        
                        QUAN TRỌNG: Khi cần thực hiện các hành động trên, bạn PHẢI sử dụng đúng cú pháp lệnh đặc biệt này (người dùng sẽ không nhìn thấy):
                        
                        - Thêm thành viên: ##ADD_FAMILY_MEMBER:{{"name":"Tên","age":"Tuổi","preferences":{{"food":"Món ăn","hobby":"Sở thích","color":"Màu sắc"}},"allergies":["Dị ứng1", "Dị ứng2"]}}##
                        - Cập nhật sở thích: ##UPDATE_PREFERENCE:{{"id":"id_thành_viên","key":"loại_sở_thích","value":"giá_trị"}}##
                        - Thêm sự kiện: ##ADD_EVENT:{{"title":"Tiêu đề","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả","participants":["Tên1","Tên2"]}}##
                        - Cập nhật sự kiện: ##UPDATE_EVENT:{{"id":"id_sự_kiện","title":"Tiêu đề mới","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả mới","participants":["Tên1","Tên2"]}}##
                        - Xóa sự kiện: ##DELETE_EVENT:id_sự_kiện##
                        - Thêm ghi chú: ##ADD_NOTE:{{"title":"Tiêu đề","content":"Nội dung","tags":["tag1","tag2"]}}##
                        
                        Hôm nay là {datetime.datetime.now().strftime("%d/%m/%Y")}.
                        
                        Thông tin hiện tại về gia đình:
                        {json.dumps(family_data, ensure_ascii=False, indent=2)}
                        
                        Sự kiện sắp tới:
                        {json.dumps(events_data, ensure_ascii=False, indent=2)}
                        
                        Ghi chú:
                        {json.dumps(notes_data, ensure_ascii=False, indent=2)}
                        """
                        st.write_stream(stream_llm_response(api_key=openai_api_key, system_prompt=system_prompt))
                    
                    st.rerun()

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
                st.write_stream(stream_llm_response(api_key=openai_api_key, system_prompt=system_prompt))

if __name__=="__main__":
    main()