# Hàm để phân tích tin nhắn và thêm sự kiện từ trò chuyện
def parse_event_from_message(message):
    """
    Phân tích tin nhắn từ người dùng để trích xuất thông tin sự kiện nếu có
    Trả về dict với các trường event_detected, title, date, description
    """
    result = {
        "event_detected": False,
        "title": "",
        "date": None,
        "description": ""
    }
    
    # Các pattern để nhận diện khi người dùng muốn thêm sự kiện
    event_patterns = [
        "thêm sự kiện", "tạo sự kiện", "lưu sự kiện", "ghi nhớ sự kiện", 
        "đặt lịch", "tạo lịch", "nhắc nhở", "ghi nhớ", "thêm lịch",
        "hẹn", "hẹn lịch", "đặt hẹn"
    ]
    
    message = message.lower()
    
    # Kiểm tra xem tin nhắn có chứa pattern nào không
    if not any(pattern in message for pattern in event_patterns):
        return result
    
    result["event_detected"] = True
    
    # Trích xuất tiêu đề sự kiện - tìm tiêu đề ở sau các từ khóa hoặc từ đầu câu
    title_patterns = ["tên là ", "tiêu đề là ", "tên sự kiện là ", "với tên ", " là ", ": "]
    title = ""
    for pattern in title_patterns:
        if pattern in message:
            parts = message.split(pattern, 1)
            if len(parts) > 1:
                # Lấy từ sau pattern đến hết câu hoặc dấu phẩy, chấm
                potential_title = parts[1].split(".")[0].split(",")[0].split("\n")[0]
                if len(potential_title) > len(title):
                    title = potential_title
    
    # Nếu không tìm thấy tiêu đề, thử lấy phần đầu tin nhắn
    if not title:
        first_sentence = message.split(".")[0].split("!")[0].split("?")[0]
        for pattern in event_patterns:
            if pattern in first_sentence:
                title = first_sentence.split(pattern, 1)[1].strip()
                break
    
    result["title"] = title.strip()
    
    # Trích xuất ngày - tìm các pattern ngày tháng
    import re
    from datetime import datetime, timedelta
    
    # Tìm kiểu dd/mm/yyyy hoặc dd-mm-yyyy
    date_patterns = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    date_matches = re.findall(date_patterns, message)
    
    # Tìm kiểu "ngày dd tháng mm"
    vietnamese_date = r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})'
    vn_matches = re.findall(vietnamese_date, message)
    
    # Tìm các từ khóa như "hôm nay", "ngày mai", "tuần sau"
    today = datetime.now().date()
    if "hôm nay" in message:
        result["date"] = today
    elif "ngày mai" in message or "mai" in message:
        result["date"] = today + timedelta(days=1)
    elif "ngày kia" in message:
        result["date"] = today + timedelta(days=2)
    elif "tuần sau" in message:
        result["date"] = today + timedelta(days=7)
    elif "tháng sau" in message:
        # Đơn giản hóa: thêm 30 ngày
        result["date"] = today + timedelta(days=30)
    
    # Xử lý các kết quả match từ regex
    if date_matches and not result["date"]:
        date_str = date_matches[0]
        try:
            # Thử parse nhiều định dạng
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                try:
                    result["date"] = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    
    if vn_matches and not result["date"]:
        try:
            day, month = vn_matches[0]
            year = today.year
            result["date"] = datetime(year, int(month), int(day)).date()
        except Exception:
            pass
    
    # Mặc định là hôm nay nếu không tìm thấy ngày
    if not result["date"]:
        result["date"] = today
    
    # Trích xuất mô tả - lấy phần còn lại của tin nhắn sau khi đã xác định tiêu đề và ngày
    description = message
    # Loại bỏ phần tiêu đề nếu đã tìm thấy
    if result["title"] and result["title"] in description:
        description = description.replace(result["title"], "", 1)
    
    # Loại bỏ các từ khóa sự kiện
    for pattern in event_patterns:
        description = description.replace(pattern, "")
    
    # Loại bỏ các từ khóa ngày
    date_keywords = ["hôm nay", "ngày mai", "mai", "ngày kia", "tuần sau", "tháng sau", 
                     "ngày", "tháng", "năm", "lúc", "vào"]
    for keyword in date_keywords:
        description = description.replace(keyword, "")
    
    # Làm sạch mô tả
    description = re.sub(r'[,\.]+', '.', description)  # Chuẩn hóa dấu câu
    description = re.sub(r'\s+', ' ', description).strip()  # Loại bỏ khoảng trắng thừa
    
    result["description"] = description
    
    return result

# Hàm để thêm sự kiện từ thông tin đã phân tích
def add_event_from_chat(event_info, family_data):
    """
    Thêm sự kiện mới vào dữ liệu gia đình từ thông tin đã phân tích
    Trả về thông báo xác nhận
    """
    if not event_info["event_detected"] or not event_info["title"]:
        return None
    
    # Tạo tiêu đề mặc định nếu không phân tích được
    title = event_info["title"]
    if not title.strip():
        title = "Sự kiện mới"
    
    # Đảm bảo ngày được định dạng đúng
    if event_info["date"]:
        date_str = event_info["date"].strftime("%Y-%m-%d")
    else:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Chuẩn bị mô tả
    description = event_info["description"]
    if not description.strip():
        description = "Không có mô tả"
    
    # Thêm sự kiện mới
    family_data["events"].append({
        "title": title,
        "date": date_str,
        "description": description
    })
    
    # Lưu dữ liệu
    save_family_data(family_data)
    
    # Tạo thông báo xác nhận
    confirmation = f"✅ Đã thêm sự kiện: {title} vào ngày {date_str}."
    return confirmation
from openai import OpenAI
import dotenv
import os
from PIL import Image
from audio_recorder_streamlit import audio_recorder
import base64
from io import BytesIO
import json
import datetime

# Tải các biến môi trường từ file .env
dotenv.load_dotenv()

# Chỉ sử dụng mô hình GPT-4o-mini
openai_model = "gpt-4o-mini"

# Hàm để lưu và tải dữ liệu gia đình
def save_family_data(data):
    with open("family_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_family_data():
    try:
        with open("family_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            # Chuyển đổi members thành dictionary nếu nó là list
            if isinstance(data["members"], list):
                members_dict = {}
                for i, member in enumerate(data["members"]):
                    members_dict[str(i+1)] = member
                data["members"] = members_dict
            elif "members" not in data:
                data["members"] = {}
                
            # Đảm bảo mỗi thành viên có đầy đủ các trường cần thiết
            for member_id, member in data["members"].items():
                if not isinstance(member, dict):
                    # Nếu thành viên không phải là dictionary, tạo một dictionary mới
                    data["members"][member_id] = {
                        "name": str(member) if member else f"Thành viên {member_id}",
                        "relationship": "Không xác định",
                        "age": 0,
                        "preferences": [],
                        "restrictions": [],
                        "notes": ""
                    }
                    continue
                
                # Đảm bảo tất cả các trường cần thiết đều tồn tại
                if "name" not in member or not member["name"]:
                    member["name"] = f"Thành viên {member_id}"
                if "relationship" not in member:
                    member["relationship"] = "Không xác định"
                if "age" not in member:
                    member["age"] = 0
                if "preferences" not in member or not isinstance(member["preferences"], list):
                    member["preferences"] = []
                if "restrictions" not in member or not isinstance(member["restrictions"], list):
                    member["restrictions"] = []
                if "notes" not in member:
                    member["notes"] = ""
            
            # Đảm bảo các khóa khác tồn tại
            if "events" not in data:
                data["events"] = []
            if "notes" not in data:
                data["notes"] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        # Trả về cấu trúc dữ liệu mẫu nếu file không tồn tại hoặc trống
        return {
            "members": {},
            "events": [],
            "notes": []
        }

# Hàm để truy xuất thông tin thành viên gia đình cho AI
def get_family_context():
    data = load_family_data()
    context = "Thông tin về các thành viên trong gia đình:\n\n"
    
    for member_id, member in data["members"].items():
        context += f"- {member['name']} ({member['relationship']}, {member['age']} tuổi)\n"
        context += f"  + Sở thích: {', '.join(member['preferences'])}\n"
        context += f"  + Dị ứng/Hạn chế: {', '.join(member['restrictions'])}\n"
        context += f"  + Ghi chú: {member['notes']}\n\n"
    
    # Thêm các sự kiện sắp tới
    context += "Các sự kiện sắp tới:\n"
    today = datetime.datetime.now().date()
    upcoming_events = [e for e in data["events"] 
                      if datetime.datetime.strptime(e["date"], "%Y-%m-%d").date() >= today]
    
    for event in sorted(upcoming_events, key=lambda x: x["date"]):
        event_date = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
        days_remaining = (event_date - today).days
        context += f"- {event['title']} ({event['date']}): {event['description']} - {days_remaining} ngày nữa\n"
    
    return context

# Function để chuyển file ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

    # Function để query và stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key=None):
    response_message = ""
    
    # Tạo ngữ cảnh gia đình cho AI
    family_context = get_family_context()
    
    # Thêm ngữ cảnh vào tin nhắn hệ thống
    system_message = {
        "role": "system", 
        "content": f"""Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là hỗ trợ và tư vấn cho các thành viên 
        trong gia đình về mọi vấn đề liên quan đến cuộc sống hàng ngày, kế hoạch, sở thích và nhu cầu của họ.
        
        {family_context}
        
        Người dùng có thể thêm sự kiện mới bằng cách chat với bạn. Khi họ nhắc đến việc thêm sự kiện, tạo lịch,
        đặt hẹn, hay ghi nhớ một điều gì đó vào một ngày cụ thể, hãy hiểu rằng họ muốn thêm sự kiện mới vào lịch gia đình.
        
        Hãy sử dụng thông tin này để cá nhân hóa câu trả lời của bạn. Khi người dùng hỏi về một thành viên cụ thể, 
        hãy đưa ra gợi ý phù hợp với sở thích và hạn chế của họ. Nếu họ hỏi về kế hoạch, hãy nhắc họ về các sự kiện sắp tới."""
    }
    
    # Thêm tin nhắn hệ thống vào đầu danh sách
    messages = [system_message] + st.session_state.messages
    
    # Trước khi gọi AI, kiểm tra xem tin nhắn cuối cùng có phải là thêm sự kiện không
    if len(st.session_state.messages) > 0:
        last_user_message = None
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "user" and msg["content"][0]["type"] == "text":
                last_user_message = msg["content"][0]["text"]
                break
        
        if last_user_message:
            # Phân tích tin nhắn xem có phải là thêm sự kiện không
            family_data = load_family_data()
            event_info = parse_event_from_message(last_user_message)
            if event_info["event_detected"]:
                # Thêm sự kiện mới
                confirmation = add_event_from_chat(event_info, family_data)
                if confirmation:
                    # Thêm thông báo xác nhận vào đầu tin nhắn phản hồi
                    response_message = confirmation + "\n\n"
    
    client = OpenAI(api_key=api_key)
    for chunk in client.chat.completions.create(
        model=openai_model,
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
        stream=True,
    ):
        chunk_text = chunk.choices[0].delta.content or ""
        response_message += chunk_text
        yield chunk_text

    st.session_state.messages.append({
        "role": "assistant", 
        "content": [
            {
                "type": "text",
                "text": response_message,
            }
        ]})

def main():
    # --- Cấu hình trang ---
    st.set_page_config(
        page_title="Trợ lý Gia đình AI",
        page_icon="👨‍👩‍👧‍👦",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Header ---
    st.html("""<h1 style="text-align: center; color: #6ca395;">👨‍👩‍👧‍👦 <i>Trợ lý Gia đình AI</i> 🏡</h1>""")
    
    # --- Thanh bên ---
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        default_openai_api_key = os.getenv("OPENAI_API_KEY") or ""
        openai_api_key = st.text_input("OpenAI API Key:", value=default_openai_api_key, type="password")
        
        st.divider()
        
        # Tab để quản lý thành viên gia đình
        st.header("👨‍👩‍👧‍👦 Quản lý Gia đình")
        tab1, tab2, tab3 = st.tabs(["Thành viên", "Sự kiện", "Ghi chú"])
        
        with tab1:
            family_data = load_family_data()
            
            # Hiển thị danh sách thành viên
            if family_data["members"]:
                st.subheader("Thành viên hiện tại:")
                for member_id, member in family_data["members"].items():
                    try:
                        name = member.get("name", f"Thành viên {member_id}")
                        relationship = member.get("relationship", "Không xác định")
                        age = member.get("age", 0)
                        st.write(f"{name} ({relationship}, {age} tuổi)")
                        
                        # Nút để xem/chỉnh sửa thành viên
                        if st.button(f"Chỉnh sửa {name}", key=f"edit_{member_id}"):
                            st.session_state.edit_member = member_id
                    except Exception as e:
                        st.error(f"Lỗi hiển thị thành viên: {e}")
            
            # Form để thêm thành viên mới
            with st.expander("➕ Thêm thành viên mới"):
                with st.form("add_member_form"):
                    new_name = st.text_input("Tên:")
                    new_relationship = st.text_input("Quan hệ (ví dụ: Cha, Mẹ, Con):")
                    new_age = st.number_input("Tuổi:", min_value=0, max_value=120)
                    new_preferences = st.text_area("Sở thích (mỗi sở thích một dòng):")
                    new_restrictions = st.text_area("Dị ứng/Hạn chế (mỗi hạn chế một dòng):")
                    new_notes = st.text_area("Ghi chú:")
                    
                    submit_button = st.form_submit_button("Thêm")
                    
                    if submit_button and new_name:
                        # Tạo ID mới cho thành viên
                        new_id = str(len(family_data["members"]) + 1)
                        
                        # Đảm bảo members là dictionary
                        if not isinstance(family_data["members"], dict):
                            family_data["members"] = {}
                            
                        # Thêm thành viên mới
                        family_data["members"][new_id] = {
                            "name": new_name,
                            "relationship": new_relationship,
                            "age": new_age,
                            "preferences": [p.strip() for p in new_preferences.split("\n") if p.strip()],
                            "restrictions": [r.strip() for r in new_restrictions.split("\n") if r.strip()],
                            "notes": new_notes
                        }
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã thêm {new_name} vào gia đình!")
                        st.rerun()
            
            # Form để chỉnh sửa thành viên
            if "edit_member" in st.session_state and st.session_state.edit_member:
                member_id = st.session_state.edit_member
                try:
                    member = family_data["members"][member_id]
                    
                    st.subheader(f"Chỉnh sửa thông tin của {member.get('name', 'Thành viên')}")
                    
                    with st.form("edit_member_form"):
                        edit_name = st.text_input("Tên:", value=member.get("name", ""))
                        edit_relationship = st.text_input("Quan hệ:", value=member.get("relationship", ""))
                        edit_age = st.number_input("Tuổi:", min_value=0, max_value=120, value=member.get("age", 0))
                        edit_preferences = st.text_area("Sở thích:", value="\n".join(member.get("preferences", [])))
                        edit_restrictions = st.text_area("Dị ứng/Hạn chế:", value="\n".join(member.get("restrictions", [])))
                        edit_notes = st.text_area("Ghi chú:", value=member.get("notes", ""))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            update_button = st.form_submit_button("Cập nhật")
                        with col2:
                            delete_button = st.form_submit_button("Xóa", type="primary")
                        
                        if update_button:
                            # Cập nhật thông tin
                            family_data["members"][member_id] = {
                                "name": edit_name,
                                "relationship": edit_relationship,
                                "age": edit_age,
                                "preferences": [p.strip() for p in edit_preferences.split("\n") if p.strip()],
                                "restrictions": [r.strip() for r in edit_restrictions.split("\n") if r.strip()],
                                "notes": edit_notes
                            }
                            
                            # Lưu dữ liệu
                            save_family_data(family_data)
                            st.success(f"Đã cập nhật thông tin của {edit_name}!")
                            st.session_state.edit_member = None
                            st.rerun()
                        
                        if delete_button:
                            # Xóa thành viên
                            name = family_data["members"][member_id].get("name", "")
                            del family_data["members"][member_id]
                            
                            # Lưu dữ liệu
                            save_family_data(family_data)
                            st.success(f"Đã xóa {name} khỏi gia đình!")
                            st.session_state.edit_member = None
                            st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi chỉnh sửa thành viên: {str(e)}")
                    st.session_state.edit_member = None
                    
                    if update_button:
                        # Cập nhật thông tin
                        family_data["members"][member_id] = {
                            "name": edit_name,
                            "relationship": edit_relationship,
                            "age": edit_age,
                            "preferences": [p.strip() for p in edit_preferences.split("\n") if p.strip()],
                            "restrictions": [r.strip() for r in edit_restrictions.split("\n") if r.strip()],
                            "notes": edit_notes
                        }
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã cập nhật thông tin của {edit_name}!")
                        st.session_state.edit_member = None
                        st.rerun()
                    
                    if delete_button:
                        # Xóa thành viên
                        name = family_data["members"][member_id]["name"]
                        del family_data["members"][member_id]
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã xóa {name} khỏi gia đình!")
                        st.session_state.edit_member = None
                        st.rerun()
        
        with tab2:
            # Quản lý các sự kiện gia đình
            with st.expander("➕ Thêm sự kiện mới"):
                with st.form("add_event_form"):
                    event_title = st.text_input("Tiêu đề sự kiện:")
                    event_date = st.date_input("Ngày:")
                    event_description = st.text_area("Mô tả:")
                    
                    submit_event = st.form_submit_button("Thêm sự kiện")
                    
                    if submit_event and event_title:
                        # Thêm sự kiện mới
                        family_data["events"].append({
                            "title": event_title,
                            "date": event_date.strftime("%Y-%m-%d"),
                            "description": event_description
                        })
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã thêm sự kiện {event_title}!")
                        st.rerun()
            
            # Hiển thị các sự kiện sắp tới
            if family_data["events"]:
                st.subheader("Sự kiện sắp tới:")
                today = datetime.datetime.now().date()
                events = sorted(family_data["events"], key=lambda x: x["date"])
                
                for i, event in enumerate(events):
                    event_date = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
                    days_remaining = (event_date - today).days
                    
                    # Hiển thị ngày còn lại
                    status = ""
                    if days_remaining < 0:
                        status = "Đã qua"
                    elif days_remaining == 0:
                        status = "Hôm nay"
                    else:
                        status = f"Còn {days_remaining} ngày"
                    
                    st.write(f"**{event['title']}** ({event['date']}) - {status}")
                    st.write(f"{event['description']}")
                    
                    # Nút xóa sự kiện
                    if st.button(f"Xóa", key=f"delete_event_{i}"):
                        family_data["events"].pop(i)
                        save_family_data(family_data)
                        st.success("Đã xóa sự kiện!")
                        st.rerun()
                    
                    st.divider()
        
        with tab3:
            # Quản lý ghi chú gia đình
            with st.form("add_note_form"):
                note_content = st.text_area("Ghi chú mới:")
                submit_note = st.form_submit_button("Thêm ghi chú")
                
                if submit_note and note_content:
                    # Thêm ghi chú mới với thời gian hiện tại
                    family_data["notes"].append({
                        "content": note_content,
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # Lưu dữ liệu
                    save_family_data(family_data)
                    st.success("Đã thêm ghi chú mới!")
                    st.rerun()
            
            # Hiển thị ghi chú hiện có
            if family_data["notes"]:
                st.subheader("Ghi chú:")
                for i, note in enumerate(reversed(family_data["notes"])):
                    st.markdown(f"**{note['timestamp']}**")
                    st.markdown(note["content"])
                    
                    # Nút xóa ghi chú
                    if st.button(f"Xóa", key=f"delete_note_{i}"):
                        family_data["notes"].pop(len(family_data["notes"]) - 1 - i)
                        save_family_data(family_data)
                        st.success("Đã xóa ghi chú!")
                        st.rerun()
                    
                    st.divider()
        
        # Nút reset cuộc trò chuyện
        st.divider()
        def reset_conversation():
            if "messages" in st.session_state and len(st.session_state.messages) > 0:
                st.session_state.pop("messages", None)

        st.button(
            "🗑️ Làm mới cuộc trò chuyện", 
            on_click=reset_conversation,
        )

    # --- Kiểm tra API Key ---
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        st.write("#")
        st.warning("⬅️ Vui lòng nhập OpenAI API Key để tiếp tục...")
    else:
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Hiển thị tin nhắn trước đó nếu có
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                for content in message["content"]:
                    if content["type"] == "text":
                        st.write(content["text"])
                    elif content["type"] == "image_url":      
                        st.image(content["image_url"]["url"])

        # Khu vực tương tác chính
        col1, col2 = st.columns([3, 1])
        
        with col2:
            st.write("### 📸 Thêm hình ảnh:")
            
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
            
            cols_img = st.columns(2)
            with cols_img[0]:
                st.file_uploader(
                    "Tải ảnh lên:", 
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key="uploaded_img",
                    on_change=add_image_to_messages,
                )
            
            with cols_img[1]:
                st.camera_input(
                    "Chụp ảnh", 
                    key="camera_img",
                    on_change=add_image_to_messages,
                )
            
            st.write("### 🎤 Thu âm giọng nói:")
            speech_input = audio_recorder("Bấm để nói:", icon_size="2x", neutral_color="#6ca395")
            
            if speech_input and "prev_speech_hash" in st.session_state and st.session_state.prev_speech_hash != hash(speech_input):
                st.session_state.prev_speech_hash = hash(speech_input)
                
                client = OpenAI(api_key=openai_api_key)
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=("audio.wav", speech_input),
                )
                
                audio_prompt = transcript.text
                
                if audio_prompt:
                    st.session_state.messages.append(
                        {
                            "role": "user", 
                            "content": [{
                                "type": "text",
                                "text": audio_prompt,
                            }]
                        }
                    )
                    
                    # Hiển thị tin nhắn mới
                    with st.chat_message("user"):
                        st.markdown(audio_prompt)
                    
                    # Phản hồi từ AI
                    with st.chat_message("assistant"):
                        st.write_stream(stream_llm_response(api_key=openai_api_key))
        
        with col1:
            # Nhập tin nhắn
            if prompt := st.chat_input("Hỏi trợ lý gia đình..."):
                st.session_state.messages.append(
                    {
                        "role": "user", 
                        "content": [{
                            "type": "text",
                            "text": prompt,
                        }]
                    }
                )
                
                # Hiển thị tin nhắn mới
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Phản hồi từ AI
                with st.chat_message("assistant"):
                    st.write_stream(stream_llm_response(api_key=openai_api_key))


if __name__=="__main__":
    if "prev_speech_hash" not in st.session_state:
        st.session_state.prev_speech_hash = None
    if "edit_member" not in st.session_state:
        st.session_state.edit_member = None
    main()