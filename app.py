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
import re
from datetime import datetime, timedelta

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
        context += f"- {member.get('name', 'Không tên')} ({member.get('relationship', 'Không xác định')}, {member.get('age', 0)} tuổi)\n"
        context += f"  + Sở thích: {', '.join(member.get('preferences', []))}\n"
        context += f"  + Dị ứng/Hạn chế: {', '.join(member.get('restrictions', []))}\n"
        context += f"  + Ghi chú: {member.get('notes', '')}\n\n"
    
    # Thêm các sự kiện sắp tới
    context += "Các sự kiện sắp tới:\n"
    today = datetime.now().date()
    upcoming_events = [e for e in data["events"] 
                      if datetime.strptime(e["date"], "%Y-%m-%d").date() >= today]
    
    for event in sorted(upcoming_events, key=lambda x: x["date"]):
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        days_remaining = (event_date - today).days
        context += f"- {event['title']} ({event['date']}): {event['description']} - {days_remaining} ngày nữa\n"
    
    return context

# Hàm để phân tích tin nhắn và thêm/sửa/xóa sự kiện từ trò chuyện
def parse_event_from_message(message):
    """
    Phân tích tin nhắn từ người dùng để trích xuất thông tin sự kiện nếu có
    Trả về dict với các trường event_action, title, date, description, search_term
    """
    result = {
        "event_action": "none",  # none, add, edit, delete
        "title": "",
        "date": None,
        "description": "",
        "search_term": ""  # Dùng để tìm kiếm sự kiện cần sửa/xóa
    }
    
    # Các pattern để nhận diện khi người dùng muốn thêm sự kiện
    add_patterns = [
        "thêm sự kiện", "tạo sự kiện", "lưu sự kiện", "ghi nhớ sự kiện", 
        "đặt lịch", "tạo lịch", "nhắc nhở", "ghi nhớ", "thêm lịch",
        "hẹn", "hẹn lịch", "đặt hẹn"
    ]
    
    # Các pattern để nhận diện khi người dùng muốn sửa sự kiện
    edit_patterns = [
        "sửa sự kiện", "chỉnh sự kiện", "cập nhật sự kiện", "thay đổi sự kiện",
        "sửa lịch", "cập nhật lịch", "chỉnh lịch", "thay đổi lịch", 
        "sửa ngày", "đổi ngày", "thay đổi ngày"
    ]
    
    # Các pattern để nhận diện khi người dùng muốn xóa sự kiện
    delete_patterns = [
        "xóa sự kiện", "hủy sự kiện", "loại bỏ sự kiện", "bỏ sự kiện",
        "xóa lịch", "hủy lịch", "loại bỏ lịch", "bỏ lịch"
    ]
    
    message = message.lower()
    
    # Kiểm tra xem tin nhắn có chứa pattern nào không
    if any(pattern in message for pattern in add_patterns):
        result["event_action"] = "add"
    elif any(pattern in message for pattern in edit_patterns):
        result["event_action"] = "edit"
    elif any(pattern in message for pattern in delete_patterns):
        result["event_action"] = "delete"
    else:
        return result
    
    # Nếu là sửa hoặc xóa, cần tìm từ khóa để xác định sự kiện cần thao tác
    if result["event_action"] in ["edit", "delete"]:
        # Tìm kiếm các từ khóa sau các pattern
        search_patterns = ["sự kiện", "lịch", "ngày"]
        for pattern in (edit_patterns if result["event_action"] == "edit" else delete_patterns):
            if pattern in message:
                after_pattern = message.split(pattern, 1)[1].strip()
                # Lấy cụm từ sau pattern
                potential_search = after_pattern.split(".")[0].split(",")[0].split("\n")[0]
                result["search_term"] = potential_search.strip()
                break
    
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
    
    # Nếu không tìm thấy tiêu đề và đây là thêm mới, thử lấy phần đầu tin nhắn
    if not title and result["event_action"] == "add":
        first_sentence = message.split(".")[0].split("!")[0].split("?")[0]
        for pattern in add_patterns:
            if pattern in first_sentence:
                title = first_sentence.split(pattern, 1)[1].strip()
                break
    
    result["title"] = title.strip()
    
    # Trích xuất ngày - tìm các pattern ngày tháng
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
    
    # Mặc định là hôm nay nếu không tìm thấy ngày và đây là thêm mới
    if not result["date"] and result["event_action"] == "add":
        result["date"] = today
    
    # Trích xuất mô tả - lấy phần còn lại của tin nhắn sau khi đã xác định tiêu đề và ngày
    description = message
    # Loại bỏ phần tiêu đề nếu đã tìm thấy
    if result["title"] and result["title"] in description:
        description = description.replace(result["title"], "", 1)
    
    # Loại bỏ các từ khóa sự kiện
    for pattern in add_patterns + edit_patterns + delete_patterns:
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

# Hàm tìm kiếm sự kiện theo từ khóa
def find_event_by_keyword(family_data, keyword):
    """
    Tìm kiếm sự kiện dựa trên từ khóa, có thể là một phần của tiêu đề
    hoặc ngày tháng. Trả về index và sự kiện tìm thấy
    """
    if not keyword or not family_data["events"]:
        return -1, None
    
    keyword = keyword.lower().strip()
    
    # Tìm theo tiêu đề trước
    for i, event in enumerate(family_data["events"]):
        if keyword in event["title"].lower():
            return i, event
    
    # Tìm theo mô tả
    for i, event in enumerate(family_data["events"]):
        if keyword in event["description"].lower():
            return i, event
            
    # Tìm theo ngày
    for i, event in enumerate(family_data["events"]):
        if keyword in event["date"]:
            return i, event
    
    return -1, None

# Hàm để xử lý sự kiện từ thông tin đã phân tích
def process_event_from_chat(event_info, family_data):
    """
    Xử lý sự kiện dựa trên action (thêm/sửa/xóa)
    Trả về thông báo xác nhận
    """
    if event_info["event_action"] == "none":
        return None
    
    # Thêm sự kiện mới
    if event_info["event_action"] == "add":
        # Tạo tiêu đề mặc định nếu không phân tích được
        title = event_info["title"]
        if not title.strip():
            title = "Sự kiện mới"
        
        # Đảm bảo ngày được định dạng đúng
        if event_info["date"]:
            date_str = event_info["date"].strftime("%Y-%m-%d")
        else:
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
    
    # Xử lý sửa/xóa sự kiện
    elif event_info["event_action"] in ["edit", "delete"]:
        # Tìm sự kiện cần sửa/xóa
        event_index, found_event = find_event_by_keyword(family_data, event_info["search_term"])
        
        if event_index == -1:
            return f"❌ Không tìm thấy sự kiện phù hợp với từ khóa '{event_info['search_term']}'."
        
        # Xóa sự kiện
        if event_info["event_action"] == "delete":
            title = found_event["title"]
            date = found_event["date"]
            family_data["events"].pop(event_index)
            save_family_data(family_data)
            return f"✅ Đã xóa sự kiện: {title} (ngày {date})."
        
        # Sửa sự kiện
        elif event_info["event_action"] == "edit":
            # Lưu giữ thông tin cũ để so sánh
            old_title = found_event["title"]
            old_date = found_event["date"]
            
            # Cập nhật tiêu đề nếu có
            if event_info["title"]:
                found_event["title"] = event_info["title"]
            
            # Cập nhật ngày nếu có
            if event_info["date"]:
                found_event["date"] = event_info["date"].strftime("%Y-%m-%d")
            
            # Cập nhật mô tả nếu có
            if event_info["description"]:
                found_event["description"] = event_info["description"]
            
            # Lưu dữ liệu
            save_family_data(family_data)
            
            # Tạo thông báo xác nhận
            changes = []
            if old_title != found_event["title"]:
                changes.append(f"tiêu đề từ '{old_title}' thành '{found_event['title']}'")
            if old_date != found_event["date"]:
                changes.append(f"ngày từ '{old_date}' thành '{found_event['date']}'")
            if not changes:
                changes.append("thông tin")
                
            return f"✅ Đã cập nhật {', '.join(changes)} cho sự kiện."
    
    return None

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
        
        Người dùng có thể thêm, sửa hoặc xóa sự kiện bằng cách chat với bạn:
        - Khi họ nhắc đến việc thêm sự kiện, tạo lịch, đặt hẹn, hay ghi nhớ một điều gì đó vào một ngày cụ thể, hãy hiểu rằng họ muốn thêm sự kiện mới.
        - Khi họ nhắc đến việc sửa, chỉnh, cập nhật hoặc thay đổi một sự kiện, hãy hiểu rằng họ muốn sửa sự kiện.
        - Khi họ nhắc đến việc xóa, hủy hoặc bỏ một sự kiện, hãy hiểu rằng họ muốn xóa sự kiện.
        
        Hãy sử dụng thông tin này để cá nhân hóa câu trả lời của bạn. Khi người dùng hỏi về một thành viên cụ thể, 
        hãy đưa ra gợi ý phù hợp với sở thích và hạn chế của họ. Nếu họ hỏi về kế hoạch, hãy nhắc họ về các sự kiện sắp tới."""
    }
    
    # Thêm tin nhắn hệ thống vào đầu danh sách
    messages = [system_message] + st.session_state.messages
    
    # Trước khi gọi AI, kiểm tra xem tin nhắn cuối cùng có phải là yêu cầu thao tác sự kiện không
    if len(st.session_state.messages) > 0:
        last_user_message = None
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "user" and msg["content"][0]["type"] == "text":
                last_user_message = msg["content"][0]["text"]
                break
        
        if last_user_message:
            # Phân tích tin nhắn xem có phải là thao tác sự kiện không
            family_data = load_family_data()
            event_info = parse_event_from_message(last_user_message)
            if event_info["event_action"] != "none":
                # Xử lý sự kiện (thêm/sửa/xóa)
                confirmation = process_event_from_chat(event_info, family_data)
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
    # Khởi tạo biến session state
    if "prev_speech_hash" not in st.session_state:
        st.session_state.prev_speech_hash = None
    if "edit_member" not in st.session_state:
        st.session_state.edit_member = None
        
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