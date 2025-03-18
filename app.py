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
CHAT_HISTORY_FILE = "chat_history.json"  # File mới để lưu lịch sử chat

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

# Hàm quản lý lịch sử chat theo cá nhân
def add_message_to_history(member_id, role, content):
    """Thêm tin nhắn vào lịch sử chat của thành viên"""
    if not os.path.exists(CHAT_HISTORY_FILE):
        chat_history = {}
    else:
        chat_history = load_data(CHAT_HISTORY_FILE)
    
    if member_id not in chat_history:
        chat_history[member_id] = []
    
    chat_history[member_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # Giới hạn số lượng tin nhắn lưu trữ để tránh file quá lớn
    if len(chat_history[member_id]) > 100:
        chat_history[member_id] = chat_history[member_id][-100:]
    
    save_data(CHAT_HISTORY_FILE, chat_history)

def get_chat_history(member_id, limit=20):
    """Lấy lịch sử chat của thành viên"""
    chat_history = load_data(CHAT_HISTORY_FILE)
    if member_id in chat_history:
        return chat_history[member_id][-limit:]
    return []

def summarize_chat_history(member_id, api_key):
    """Tóm tắt lịch sử chat của thành viên sử dụng OpenAI"""
    chat_history = get_chat_history(member_id, limit=50)
    if not chat_history:
        return "Chưa có lịch sử trò chuyện nào."
    
    # Tạo nội dung cho prompt tóm tắt
    history_text = ""
    for message in chat_history:
        role = "Thành viên" if message["role"] == "user" else "Trợ lý"
        if isinstance(message["content"], list):
            # Xử lý đối với nội dung dạng list (có thể chứa hình ảnh)
            text_content = "\n".join([c["text"] for c in message["content"] if c["type"] == "text"])
            history_text += f"{role}: {text_content}\n"
        else:
            history_text += f"{role}: {message['content']}\n"
    
    # Sử dụng OpenAI để tóm tắt
    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Bạn là trợ lý tóm tắt. Hãy tóm tắt cuộc trò chuyện sau thành các điểm chính, các sở thích và thông tin quan trọng đã được đề cập:"},
                {"role": "user", "content": history_text}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Lỗi khi tóm tắt lịch sử: {e}")
        return "Không thể tóm tắt lịch sử trò chuyện do lỗi."

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

# Hàm stream phản hồi từ GPT-4o-mini đã được sửa đổi để lưu lịch sử theo cá nhân
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
        message_content = [{"type": "text", "text": response_message}]
        st.session_state.messages.append({
            "role": "assistant", 
            "content": message_content
        })
        
        # Lưu vào lịch sử chat nếu đang chat với thành viên cụ thể
        if "current_member_id" in st.session_state and st.session_state.current_member_id != "all":
            add_message_to_history(
                st.session_state.current_member_id,
                "assistant",
                message_content
            )
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
                    
                    # Tự động thêm người dùng hiện tại vào participants nếu đang chat với thành viên cụ thể
                    if "current_member_id" in st.session_state and st.session_state.current_member_id != "all":
                        current_member = family_data.get(st.session_state.current_member_id, {})
                        current_member_name = current_member.get("name", "")
                        if current_member_name and "participants" in details:
                            if current_member_name not in details["participants"]:
                                details["participants"].append(current_member_name)
                    
                    logger.info(f"Thêm sự kiện: {details.get('title', 'Không tiêu đề')}")
                    success = add_event(details)
                    if success:
                        st.success(f"Đã thêm sự kiện: {details.get('title', '')}")
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi khi phân tích JSON cho ADD_EVENT: {e}")
                logger.error(f"Chuỗi JSON gốc: {cmd}")
        
        # Xử lý các lệnh khác - giữ nguyên mã của các chức năng hiện tại
        # ... [code hiện tại của hàm process_assistant_response]
        
    except Exception as e:
        logger.error(f"Lỗi khi xử lý phản hồi của trợ lý: {e}")
        logger.error(f"Phản hồi gốc: {response[:100]}...")

# Các hàm quản lý thông tin gia đình, sự kiện, và ghi chú - giữ nguyên mã hiện tại

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
            
            if openai_api_key:
                st.session_state.openai_api_key = openai_api_key
        
        # Chọn người dùng hiện tại - CHỨC NĂNG MỚI
        st.write("## 👤 Người dùng hiện tại")
        
        # Tạo danh sách thành viên
        members = [(member_id, member.get("name", "Không tên")) 
                  for member_id, member in family_data.items()
                  if isinstance(member, dict)]
        
        # Thêm tùy chọn "Tất cả"
        members.insert(0, ("all", "Cả gia đình"))
        
        # Dropdown để chọn thành viên
        member_options = {name: id for id, name in members}
        
        # Xử lý khi không có thành viên nào
        if len(member_options) <= 1:  # Chỉ có "Cả gia đình"
            st.warning("Chưa có thành viên nào. Vui lòng thêm thành viên để sử dụng chức năng chat cá nhân.")
            selected_member_name = "Cả gia đình"
            selected_member_id = "all"
        else:
            selected_member_name = st.selectbox(
                "Chọn thành viên:", 
                options=list(member_options.keys()),
                index=0
            )
            selected_member_id = member_options[selected_member_name]
        
        # Lưu ID thành viên vào session state
        if "current_member_id" not in st.session_state or st.session_state.current_member_id != selected_member_id:
            # Lưu lại tin nhắn hiện tại của thành viên cũ (nếu có)
            if "current_member_id" in st.session_state and "messages" in st.session_state and st.session_state.messages:
                if st.session_state.current_member_id != "all":
                    # Lấy toàn bộ tin nhắn hiện tại để lưu
                    for message in st.session_state.messages:
                        add_message_to_history(
                            st.session_state.current_member_id,
                            message["role"],
                            message["content"]
                        )
            
            # Cập nhật thành viên hiện tại
            st.session_state.current_member_id = selected_member_id
            
            # Reset tin nhắn
            st.session_state.messages = []
            
            # Nếu chọn thành viên cụ thể, tải lịch sử chat gần đây
            if selected_member_id != "all":
                recent_history = get_chat_history(selected_member_id, limit=5)
                if recent_history:
                    # Chuyển định dạng từ lịch sử sang định dạng messages
                    for msg in recent_history:
                        st.session_state.messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
        
        # Hiển thị tóm tắt lịch sử trò chuyện - CHỨC NĂNG MỚI
        if selected_member_id != "all":
            with st.expander("📜 Tóm tắt trò chuyện trước đó"):
                if st.button("Tạo tóm tắt"):
                    if "openai_api_key" in st.session_state:
                        with st.spinner("Đang tóm tắt lịch sử trò chuyện..."):
                            summary = summarize_chat_history(selected_member_id, st.session_state.openai_api_key)
                            st.markdown(summary)
                    else:
                        st.error("Vui lòng nhập OpenAI API Key để sử dụng chức năng tóm tắt")
        
        st.divider()
        
        st.write("## Thông tin Gia đình")
        
        # Phần thêm thành viên gia đình - giữ nguyên mã hiện tại
        # ... [code hiện tại cho phần thêm thành viên]

        # Quản lý sự kiện - đã sửa đổi để hỗ trợ lọc theo người dùng
        st.write("## Sự kiện")
        
        # Phần thêm sự kiện - giữ nguyên mã hiện tại
        # ... [code hiện tại cho phần thêm sự kiện]
        
        # Xem sự kiện sắp tới - đã sửa đổi để hỗ trợ lọc theo người dùng
        with st.expander("📆 Sự kiện sắp tới"):
            # Thêm filter sự kiện theo người dùng hiện tại - CHỨC NĂNG MỚI
            if "current_member_id" in st.session_state and st.session_state.current_member_id != "all":
                show_personal_events_only = st.checkbox("Chỉ hiển thị sự kiện của tôi")
            else:
                show_personal_events_only = False
            
            # Sắp xếp sự kiện theo ngày (với xử lý lỗi)
            try:
                sorted_events = sorted(
                    events_data.items(),
                    key=lambda x: (x[1].get("date", ""), x[1].get("time", ""))
                )
                
                # Lọc sự kiện theo người dùng hiện tại nếu được chọn - CHỨC NĂNG MỚI
                if show_personal_events_only and st.session_state.current_member_id != "all":
                    current_member = family_data.get(st.session_state.current_member_id, {})
                    current_member_name = current_member.get("name", "")
                    sorted_events = [
                        (event_id, event) for event_id, event in sorted_events
                        if current_member_name in event.get("participants", [])
                    ]
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp sự kiện: {e}")
                sorted_events = []
            
            if not sorted_events:
                st.write("Không có sự kiện nào sắp tới")
            
            # Hiển thị sự kiện - giữ nguyên mã hiện tại
            # ... [code hiện tại cho phần hiển thị sự kiện]
        
        # Các phần còn lại của sidebar - giữ nguyên mã hiện tại
        # ... [code hiện tại cho phần còn lại của sidebar]

    # --- Nội dung chính ---
    # Kiểm tra nếu người dùng đã nhập OpenAI API Key
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        # Hiển thị thông báo và giới thiệu - giữ nguyên mã hiện tại
        # ... [code hiện tại]
    else:
        client = OpenAI(api_key=openai_api_key)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Hiển thị các tin nhắn trước đó
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                for content in message["content"]:
                    if content["type"] == "text":
                        st.write(content["text"])
                    elif content["type"] == "image_url":      
                        st.image(content["image_url"]["url"])

        # Chức năng hình ảnh - giữ nguyên mã hiện tại
        # ... [code hiện tại cho phần hình ảnh]

        # System prompt cho trợ lý - đã sửa đổi để tính đến người dùng hiện tại
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
        """

        # Thêm thông tin về người dùng hiện tại - CHỨC NĂNG MỚI
        if "current_member_id" in st.session_state and st.session_state.current_member_id != "all":
            current_member = family_data.get(st.session_state.current_member_id, {})
            system_prompt += f"""
            
            Người dùng hiện tại là: {current_member.get("name", "Không xác định")}
            Tuổi: {current_member.get("age", "Không xác định")}
            Sở thích: {json.dumps(current_member.get("preferences", {}), ensure_ascii=False)}
            
            Hãy điều chỉnh cách giao tiếp của bạn để phù hợp với người dùng hiện tại và đưa ra các đề xuất phù hợp với sở thích của họ.
            Khi thêm sự kiện, hãy tự động thêm người dùng hiện tại vào danh sách người tham gia nếu phù hợp.
            """

        # Chat input và ghi âm - sửa đổi để lưu lịch sử theo cá nhân
        audio_prompt = None
        if "prev_speech_hash" not in st.session_state:
            st.session_state.prev_speech_hash = None

        # Ghi âm - giữ nguyên mã hiện tại
        # ... [code hiện tại cho phần ghi âm]

        # Chat input - sửa đổi để lưu lịch sử theo cá nhân
        if prompt := st.chat_input(f"Xin chào{' ' + current_member.get('name', '') if 'current_member_id' in st.session_state and st.session_state.current_member_id != 'all' else ''}! Tôi có thể giúp gì cho bạn?") or audio_prompt:
            message_content = [{
                "type": "text",
                "text": prompt or audio_prompt,
            }]
            
            st.session_state.messages.append({
                "role": "user", 
                "content": message_content
            })
            
            # Lưu vào lịch sử chat nếu đang chat với thành viên cụ thể - CHỨC NĂNG MỚI
            if "current_member_id" in st.session_state and st.session_state.current_member_id != "all":
                add_message_to_history(
                    st.session_state.current_member_id,
                    "user",
                    message_content
                )
            
            # Hiển thị tin nhắn mới
            with st.chat_message("user"):
                st.markdown(prompt or audio_prompt)

            with st.chat_message("assistant"):
                st.write_stream(stream_llm_response(api_key=openai_api_key, system_prompt=system_prompt))

if __name__=="__main__":
    main()