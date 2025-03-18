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

# Chỉ sử dụng một mô hình duy nhất
openai_model = "gpt-4o-mini"

# Đường dẫn file lưu trữ dữ liệu
FAMILY_DATA_FILE = "family_data.json"
EVENTS_DATA_FILE = "events_data.json"
NOTES_DATA_FILE = "notes_data.json"

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
    except Exception as e:
        print(f"Lỗi khi lưu dữ liệu vào {file_path}: {e}")

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
    response_message = ""
    
    # Tạo tin nhắn với system prompt
    messages = [{"role": "system", "content": system_prompt}]
    for message in st.session_state.messages:
        messages.append({
            "role": message["role"],
            "content": message["content"][0]["text"]
        })
    
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

def process_assistant_response(response):
    """Hàm xử lý lệnh từ phản hồi của trợ lý"""
    try:
        # Tìm kiếm mẫu lệnh trong phản hồi
        if "##ADD_FAMILY_MEMBER:" in response:
            cmd = response.split("##ADD_FAMILY_MEMBER:")[1].split("##")[0].strip()
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    add_family_member(details)
            except json.JSONDecodeError as e:
                print(f"Lỗi khi phân tích JSON cho ADD_FAMILY_MEMBER: {e}")
        
        if "##UPDATE_PREFERENCE:" in response:
            cmd = response.split("##UPDATE_PREFERENCE:")[1].split("##")[0].strip()
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    update_preference(details)
            except json.JSONDecodeError as e:
                print(f"Lỗi khi phân tích JSON cho UPDATE_PREFERENCE: {e}")
        
        if "##ADD_EVENT:" in response:
            cmd = response.split("##ADD_EVENT:")[1].split("##")[0].strip()
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    add_event(details)
            except json.JSONDecodeError as e:
                print(f"Lỗi khi phân tích JSON cho ADD_EVENT: {e}")
        
        if "##UPDATE_EVENT:" in response:
            cmd = response.split("##UPDATE_EVENT:")[1].split("##")[0].strip()
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    update_event(details)
            except json.JSONDecodeError as e:
                print(f"Lỗi khi phân tích JSON cho UPDATE_EVENT: {e}")
        
        if "##DELETE_EVENT:" in response:
            cmd = response.split("##DELETE_EVENT:")[1].split("##")[0].strip()
            try:
                event_id = cmd.strip()
                delete_event(event_id)
            except Exception as e:
                print(f"Lỗi khi xóa sự kiện: {e}")
        
        if "##ADD_NOTE:" in response:
            cmd = response.split("##ADD_NOTE:")[1].split("##")[0].strip()
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    add_note(details)
            except json.JSONDecodeError as e:
                print(f"Lỗi khi phân tích JSON cho ADD_NOTE: {e}")
    except Exception as e:
        print(f"Lỗi khi xử lý phản hồi của trợ lý: {e}")

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

# Các hàm quản lý sự kiện
def add_event(details):
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

def update_event(details):
    event_id = details.get("id")
    if event_id in events_data:
        for key, value in details.items():
            if key != "id" and value is not None:
                events_data[event_id][key] = value
        save_data(EVENTS_DATA_FILE, events_data)

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

        # System prompt cho trợ lý
        system_prompt = f"""
        Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là giúp quản lý thông tin về các thành viên trong gia đình, 
        sở thích của họ, các sự kiện, và ghi chú. Khi người dùng yêu cầu, bạn có thể thực hiện các hành động sau:
        
        1. Thêm thông tin về thành viên gia đình (tên, tuổi, sở thích)
        2. Cập nhật sở thích của thành viên gia đình
        3. Thêm, cập nhật, hoặc xóa sự kiện
        4. Thêm ghi chú
        
        Khi cần thực hiện các hành động trên, hãy sử dụng cú pháp lệnh đặc biệt (người dùng sẽ không nhìn thấy):
        
        - Thêm thành viên: ##ADD_FAMILY_MEMBER:{{"name":"Tên","age":"Tuổi","preferences":{{"food":"Món ăn","hobby":"Sở thích","color":"Màu sắc"}}}}##
        - Cập nhật sở thích: ##UPDATE_PREFERENCE:{{"id":"id_thành_viên","key":"loại_sở_thích","value":"giá_trị"}}##
        - Thêm sự kiện: ##ADD_EVENT:{{"title":"Tiêu đề","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả","participants":["Tên1","Tên2"]}}##
        - Cập nhật sự kiện: ##UPDATE_EVENT:{{"id":"id_sự_kiện","title":"Tiêu đề mới","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả mới","participants":["Tên1","Tên2"]}}##
        - Xóa sự kiện: ##DELETE_EVENT:id_sự_kiện##
        - Thêm ghi chú: ##ADD_NOTE:{{"title":"Tiêu đề","content":"Nội dung","tags":["tag1","tag2"]}}##
        
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